"""Unit tests for the MQTT transport and S05 helpers."""

import asyncio
import inspect
import json
import re

import pytest

from deepal.mqtt import (
    CHARGE_STATE_CHARGE_STOPPED,
    MAPPED_S05_KEYS,
    aes_cbc_decrypt,
    aes_cbc_encrypt,
    build_connect_packet,
    build_disconnect_packet,
    build_pingreq_packet,
    build_puback_packet,
    build_publish_packet,
    build_subscribe_packet,
    charge_currents,
    charge_is_active,
    charge_state,
    clean_charge_current,
    clean_charge_current_magnitude,
    condition_request_payload,
    device_id_candidates,
    is_phev_model,
    login_request_payload,
    mqtt_remaining_length,
    normalize_s05_params,
    normalize_sda_params,
    parse_connack,
    parse_publish,
    parse_sda_broker_config,
    parse_suback,
    read_packet_with_keepalive,
    resolve_mqtt_topics,
    sda_broker_session,
    sda_condition_plan,
    sda_condition_request_payload,
    sda_session_topics,
    secret_from_login_payload,
    topic_device_id,
    unmapped_s05_keys,
)


class _RecordingWriter:
    """Minimal StreamWriter stand-in that records every write."""

    def __init__(self) -> None:
        self.data = bytearray()
        self.closed = False

    def write(self, data: bytes) -> None:
        self.data.extend(data)

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        pass


def test_remaining_length_encoding():
    assert mqtt_remaining_length(0) == b"\x00"
    assert mqtt_remaining_length(127) == b"\x7f"
    assert mqtt_remaining_length(128) == b"\x80\x01"
    assert mqtt_remaining_length(321) == b"\xc1\x02"


def test_connect_and_subscribe_packets():
    connect = build_connect_packet("did-1", "did-1", "auth-token")
    assert connect[0] == 0x10
    assert b"MQTT" in connect
    assert b"did-1" in connect
    assert b"auth-token" in connect

    subscribe = build_subscribe_packet(1, ["$vdp/did-1/up"])
    assert subscribe[0] == 0x82
    assert b"$vdp/did-1/up" in subscribe


def test_connect_packet_is_mqtt5_with_exact_bytes():
    packet = build_connect_packet("did-1", "user-1", "secret")
    body = (
        b"\x00\x04MQTT"
        b"\x05"
        b"\xc2"
        b"\x00\x32"
        b"\x00"
        b"\x00\x05did-1"
        b"\x00\x06user-1"
        b"\x00\x06secret"
    )
    assert packet == b"\x10" + mqtt_remaining_length(len(body)) + body


def test_connect_packet_honours_clean_start_and_keepalive():
    packet = build_connect_packet(
        "did-1", "did-1", "secret", keepalive=30, clean_start=False
    )
    body = (
        b"\x00\x04MQTT"
        b"\x05"
        b"\xc0"
        b"\x00\x1e"
        b"\x00"
        b"\x00\x05did-1"
        b"\x00\x05did-1"
        b"\x00\x06secret"
    )
    assert packet == b"\x10" + mqtt_remaining_length(len(body)) + body


def test_v5_subscribe_publish_puback_and_lifecycle_packets():
    subscribe = build_subscribe_packet(1, ["$vdp/did-1/up"])
    assert subscribe[2:5] == b"\x00\x01\x00"

    publish = build_publish_packet("$vdp/did-1/up", {"n": 1})
    assert publish[0] == 0x30

    assert build_puback_packet(7) == b"\x40\x04\x00\x07\x00\x00"
    assert build_pingreq_packet() == b"\xc0\x00"
    assert build_disconnect_packet() == b"\xe0\x02\x00\x00"


def test_qos_one_publish_carries_the_packet_identifier():
    packet = build_publish_packet("$vdp/did-1/set/req", {"n": 1}, qos=1, packet_id=7)

    assert packet[0] == 0x32
    first, body = packet[0], packet[2:]
    topic, payload, packet_id = parse_publish(first, body)

    assert topic == "$vdp/did-1/set/req"
    assert payload == {"n": 1}
    assert packet_id == 7


def test_parse_connack_reason_codes():
    assert parse_connack(0x20, b"\x00\x00\x00") == (0, 0)
    assert parse_connack(0x20, b"\x01\x86\x00") == (1, 0x86)
    assert parse_connack(0x30, b"\x00\x00") == (None, None)
    assert parse_connack(0x20, b"\x00") == (None, None)


@pytest.mark.asyncio
async def test_read_packet_with_keepalive_sends_pingreq_until_timeout():
    reader = asyncio.StreamReader()
    writer = _RecordingWriter()
    with pytest.raises(asyncio.TimeoutError):
        await read_packet_with_keepalive(reader, writer, timeout=0.05, keepalive=0.01)
    assert writer.data.count(b"\xc0\x00") >= 1


@pytest.mark.asyncio
async def test_read_packet_with_keepalive_pings_then_returns_packet():
    reader = asyncio.StreamReader()
    writer = _RecordingWriter()

    async def feed_later() -> None:
        await asyncio.sleep(0.02)
        reader.feed_data(b"\x30\x00")

    feed_task = asyncio.ensure_future(feed_later())
    try:
        first, body = await read_packet_with_keepalive(
            reader, writer, timeout=1.0, keepalive=0.005
        )
    finally:
        await feed_task
    assert (first, body) == (0x30, b"")
    assert b"\xc0\x00" in writer.data


@pytest.mark.asyncio
async def test_read_packet_with_keepalive_returns_packet_without_pinging():
    reader = asyncio.StreamReader()
    reader.feed_data(b"\x20\x03\x00\x00\x00")
    writer = _RecordingWriter()
    first, body = await read_packet_with_keepalive(
        reader, writer, timeout=1.0, keepalive=60
    )
    assert (first, body) == (0x20, b"\x00\x00\x00")
    assert writer.data == b""


def test_resolve_mqtt_topics_from_topic_infos():
    config = {
        "mqttConnectionInfos": [
            {
                "clusterInfos": [
                    {"brokerUrl": "ssl://broker.example:8883", "brokerPort": 8883}
                ],
                "topicInfos": [
                    {
                        "msgType": "loginout",
                        "pubTopics": ["$vdp/login-did/loginout/req"],
                        "subTopics": ["$vdp/login-did/loginout/res"],
                    },
                    {
                        "msgType": "properties",
                        "pubTopics": ["$vdp/device-did/properties/get/req"],
                        "subTopics": [
                            "$vdp/device-did/properties/get/res",
                            "$vdp/device-did/shared/commands/horn",
                            "$vdp/device-did/did/set/ac",
                        ],
                    },
                    {
                        "msgType": "event",
                        "subTopics": ["$vdp/device-did/device-did/server/event"],
                    },
                ],
            }
        ]
    }
    resolved = resolve_mqtt_topics(config)
    assert resolved.login_publish == "$vdp/login-did/loginout/req"
    assert resolved.login_subscribe == "$vdp/login-did/loginout/res"
    assert resolved.properties_publish == "$vdp/device-did/properties/get/req"
    assert resolved.event_subscribe == "$vdp/device-did/device-did/server/event"
    assert resolved.login_did == "login-did"
    assert resolved.device_did == "device-did"
    assert resolved.did == "device-did"
    assert "$vdp/device-did/properties/get/res" in resolved.subscriptions
    assert all("/commands/" not in topic for topic in resolved.subscriptions)
    assert all("/set/" not in topic for topic in resolved.subscriptions)


def test_resolve_mqtt_topics_does_not_subscribe_to_publish_topics():
    """The broker's event subscription is ``events/up``, not ``events/down``.

    The live S05 connection configuration lists ``events/down`` as the client's
    publish topic and ``events/up`` as the subscription. Subscribing to the
    publish topic made the broker answer 0x87 (not authorized), and the SUBACK
    validation then aborted the whole telemetry session.
    """
    config = {
        "mqttConnectionInfos": [
            {
                "topicInfos": [
                    {
                        "msgType": "loginout",
                        "pubTopics": ["$vdp/device-did/loginout/req"],
                        "subTopics": ["$vdp/device-did/loginout/res"],
                    },
                    {
                        "msgType": "properties",
                        "pubTopics": [
                            "$vdp/device-did/properties/set/req",
                            "$vdp/device-did/properties/get/req",
                        ],
                        "subTopics": [
                            "$vdp/device-did/properties/set/res",
                            "$vdp/device-did/properties/get/res",
                            "$vdp/device-did/properties/report",
                        ],
                    },
                    {
                        "msgType": "commands",
                        "pubTopics": ["$vdp/device-did/commands/req"],
                        "subTopics": ["$vdp/device-did/commands/res"],
                    },
                    {
                        "msgType": "events",
                        "pubTopics": ["$vdp/device-did/events/down"],
                        "subTopics": ["$vdp/device-did/events/up"],
                    },
                    {
                        "msgType": "msg",
                        "pubTopics": ["$vdp/device-did/msg/down"],
                        "subTopics": ["$vdp/device-did/msg/up"],
                    },
                    {
                        "msgType": "strategy",
                        "pubTopics": ["$vdp/device-did/strategy/req"],
                        "subTopics": ["$vdp/device-did/strategy/res"],
                    },
                ],
            }
        ]
    }

    resolved = resolve_mqtt_topics(config)

    assert resolved.event_subscribe == "$vdp/device-did/events/up"
    assert "$vdp/device-did/events/down" not in resolved.subscriptions
    assert set(resolved.subscriptions) == {
        "$vdp/device-did/loginout/res",
        "$vdp/device-did/properties/set/res",
        "$vdp/device-did/properties/get/res",
        "$vdp/device-did/properties/report",
        "$vdp/device-did/events/up",
        "$vdp/device-did/msg/up",
        "$vdp/device-did/strategy/res",
    }


def test_resolve_mqtt_topics_derives_event_when_only_publish_topic_is_listed():
    config = {
        "mqttConnectionInfos": [
            {
                "topicInfos": [
                    {
                        "msgType": "loginout",
                        "pubTopics": ["$vdp/device-did/loginout/req"],
                        "subTopics": ["$vdp/device-did/loginout/res"],
                    },
                    {
                        "msgType": "events",
                        "pubTopics": ["$vdp/device-did/events/down"],
                    },
                ],
            }
        ]
    }

    resolved = resolve_mqtt_topics(config)

    assert resolved.event_subscribe == "$vdp/device-did/device-did/server/event"
    assert "$vdp/device-did/events/down" not in resolved.subscriptions
    assert "$vdp/device-did/device-did/server/event" in resolved.subscriptions


def test_resolve_mqtt_topics_uses_subscription_suffixes_without_direction():
    config = {
        "mqttConnectionInfos": [
            {
                "topicToMsgtype": {
                    "$vdp/device-did/loginout/req": "loginout",
                    "$vdp/device-did/loginout/res": "loginout",
                    "$vdp/device-did/properties/get/req": "properties",
                    "$vdp/device-did/properties/report": "properties",
                    "$vdp/device-did/events/down": "events",
                    "$vdp/device-did/events/up": "events",
                }
            }
        ]
    }

    resolved = resolve_mqtt_topics(config)

    assert resolved.login_publish == "$vdp/device-did/loginout/req"
    assert resolved.login_subscribe == "$vdp/device-did/loginout/res"
    assert resolved.properties_publish == "$vdp/device-did/properties/get/req"
    assert "$vdp/device-did/loginout/req" not in resolved.subscriptions
    assert "$vdp/device-did/properties/get/req" not in resolved.subscriptions
    assert "$vdp/device-did/properties/report" in resolved.subscriptions
    assert "$vdp/device-did/events/up" in resolved.subscriptions
    assert "$vdp/device-did/events/down" not in resolved.subscriptions


def test_resolve_mqtt_topics_distinguishes_properties_get_and_set():
    config = {
        "mqttConnectionInfos": [
            {
                "topicInfos": [
                    {
                        "msgType": "properties",
                        "pubTopics": [
                            "$vdp/device-did/properties/set/req",
                            "$vdp/device-did/properties/get/req",
                        ],
                        "subTopics": [
                            "$vdp/device-did/properties/get/res",
                            "$vdp/device-did/properties/report",
                        ],
                    }
                ],
            }
        ]
    }
    resolved = resolve_mqtt_topics(config)
    assert resolved.properties_publish == "$vdp/device-did/properties/get/req"
    assert resolved.properties_set_publish == "$vdp/device-did/properties/set/req"
    assert "$vdp/device-did/properties/set/req" not in resolved.subscriptions
    assert "$vdp/device-did/properties/set/res" not in resolved.subscriptions


def test_resolve_mqtt_topics_derives_properties_set_topic():
    config = {
        "mqttConnectionInfos": [
            {
                "clientId": "did-9",
                "topicInfos": [
                    {
                        "msgType": "properties",
                        "pubTopics": ["$vdp/did-9/properties/get/req"],
                    }
                ],
            }
        ]
    }
    resolved = resolve_mqtt_topics(config)
    assert resolved.properties_publish == "$vdp/did-9/properties/get/req"
    assert resolved.properties_set_publish == "$vdp/did-9/properties/set/req"


def test_resolve_mqtt_topics_from_app_maps_and_excludes_commands():
    config = {
        "mqttConnectionInfos": [
            {
                "pubTopicMap": {
                    "loginout": "$vdp/did-5/client/loginout",
                    "properties": ["$vdp/did-5/properties/get/req"],
                },
                "subTopicMap": {
                    "loginout": "$vdp/did-5/server/loginout",
                    "event": "$vdp/did-5/did-5/server/event",
                },
                "topicToMsgtype": {
                    "$vdp/did-5/properties/get/res": "properties",
                    "$vdp/did-5/did-5/client/action": "action",
                },
                "allSubTopics": [
                    "$vdp/did-5/properties/get/res",
                    "$vdp/did-5/did-5/client/action",
                ],
            }
        ]
    }
    resolved = resolve_mqtt_topics(config)
    assert resolved.login_publish == "$vdp/did-5/client/loginout"
    assert resolved.login_subscribe == "$vdp/did-5/server/loginout"
    assert resolved.properties_publish == "$vdp/did-5/properties/get/req"
    assert resolved.event_subscribe == "$vdp/did-5/did-5/server/event"
    assert "$vdp/did-5/did-5/client/action" not in resolved.subscriptions


def test_resolve_mqtt_topics_falls_back_to_templates():
    config = {
        "mqttConnectionInfos": [
            {
                "clientId": "did-9",
                "topicInfos": [
                    {
                        "msgType": "properties",
                        "subTopics": ["$vdp/did-9/properties/get/res"],
                    }
                ],
            }
        ]
    }
    resolved = resolve_mqtt_topics(config)
    assert resolved.login_publish == "$vdp/did-9/client/loginout"
    assert resolved.login_subscribe == "$vdp/did-9/server/loginout"
    assert resolved.event_subscribe == "$vdp/did-9/did-9/server/event"
    assert resolved.properties_publish == "$vdp/did-9/properties/get/req"
    assert resolved.login_did == "did-9"
    assert set(resolved.subscriptions) >= {
        "$vdp/did-9/properties/get/res",
        "$vdp/did-9/server/loginout",
        "$vdp/did-9/did-9/server/event",
    }


def test_resolve_mqtt_topics_without_config_returns_empty_roles():
    resolved = resolve_mqtt_topics({})
    assert resolved.login_publish is None
    assert resolved.properties_publish is None
    assert resolved.properties_set_publish is None
    assert resolved.subscriptions == ()


def test_publish_packet_roundtrip():
    payload = {"did": "did-1", "mt": "loginout", "n": 1}
    packet = build_publish_packet("$vdp/did-1/loginout/req", payload)
    assert packet[0] == 0x30
    first = packet[0]
    body = packet[2:]
    topic, parsed, packet_id = parse_publish(first, body)
    assert topic == "$vdp/did-1/loginout/req"
    assert parsed == payload
    assert packet_id is None


def test_aes_cbc_roundtrip():
    services = [{"service_code": "car_condition", "params": {"fetchPropertyType": 0}}]
    encrypted = aes_cbc_encrypt(services, "secret-key-12345", "req-1")
    assert json.loads(json.dumps(services)) == aes_cbc_decrypt(
        encrypted, "secret-key-12345", "req-1"
    )


def test_topic_device_id():
    assert topic_device_id("$vdp/did-1/properties/get/req") == "did-1"
    assert topic_device_id("not-a-device-topic") is None


def test_secret_from_login_payload():
    payload = {"rs": [{"params": {"secretKey": "abc123"}}]}
    assert secret_from_login_payload(payload) == "abc123"
    assert secret_from_login_payload({"rs": []}) is None


def test_condition_request_payload_is_encrypted():
    payload = condition_request_payload("car-did", "login-did", "secret-key-12345", "req-1")
    assert payload["did"] == "car-did"
    assert payload["mt"] == "properties"
    assert payload["b"] == {"ruid": "login-did"}
    services = aes_cbc_decrypt(payload["sers"], "secret-key-12345", "req-1")
    assert services[0]["service_code"] == "car_condition"


def test_sda_condition_request_payload_shape():
    payload = sda_condition_request_payload(
        "car-did",
        "login-did",
        "secret-key-12345",
        "req-1",
        basic_info={"vin": "VIN123"},
    )

    assert payload["did"] == "car-did"
    assert payload["mt"] == "properties"
    assert payload["b"] == {"ruid": "login-did", "vin": "VIN123"}
    services = aes_cbc_decrypt(payload["sers"], "secret-key-12345", "req-1")
    assert services == [
        {
            "service_code": "CarCondition",
            "command_code": "Get_CarCondition",
            "params": {"ConditionQueryType": 0},
        }
    ]


def test_sda_condition_request_payload_with_signal_list():
    payload = sda_condition_request_payload(
        "car-did",
        "login-did",
        "secret-key-12345",
        "req-1",
        signal_list=["door", "hvac"],
    )

    services = aes_cbc_decrypt(payload["sers"], "secret-key-12345", "req-1")
    assert services[0]["params"] == {
        "ConditionQueryType": 0,
        "SignalList": ["door", "hvac"],
    }


def test_sda_condition_request_payload_with_plan_overrides():
    payload = sda_condition_request_payload(
        "car-did",
        "login-did",
        "secret-key-12345",
        "req-1",
        service_code="TreeService",
        command_code="TreeCommand",
        strategy_code="strategy-1",
        strategy_id="strategy-id-1",
    )

    services = aes_cbc_decrypt(payload["sers"], "secret-key-12345", "req-1")
    assert services == [
        {
            "service_code": "TreeService",
            "command_code": "TreeCommand",
            "params": {"ConditionQueryType": 0},
            "strategy_code": "strategy-1",
            "strategy_id": "strategy-id-1",
        }
    ]


def test_sda_condition_plan_from_function_tree():
    tree = {
        "functionList": [
            {
                "id": "1",
                "deviceId": "did-other",
                "commandCode": "Cnr_AllAcON",
                "propertyCode": "ac",
            },
            {
                "id": "2",
                "deviceId": "did-condition",
                "commandCode": "Get_CarCondition",
                "serviceCode": "CarCondition",
                "strategyCode": "strategy-1",
                "strategyId": "strategy-id-1",
                "propertyCode": "carCondition",
            },
            {"id": "3", "parentId": "2", "propertyCode": "socLeft"},
            {"id": "4", "parentId": "2", "propertyCode": "battery"},
        ]
    }
    config = {
        "mqttConnectionInfos": [{"carConfigJson": json.dumps(tree)}]
    }

    plan = sda_condition_plan(config)

    assert plan.device_did == "did-condition"
    assert plan.service_code == "CarCondition"
    assert plan.command_code == "Get_CarCondition"
    assert plan.property_codes == ("carCondition", "socLeft", "battery")
    assert plan.strategy_codes == ("strategy-1",)
    assert plan.strategy_ids == ("strategy-id-1",)


def test_sda_condition_plan_without_condition_entry():
    tree = {
        "functionList": [
            {"id": "1", "deviceId": "did-only", "commandCode": "Cnr_AllAcON"}
        ]
    }
    config = {"mqttConnectionInfos": [{"carConfigJson": json.dumps(tree)}]}

    plan = sda_condition_plan(config)

    assert plan.device_did == "did-only"
    assert plan.service_code == "CarCondition"
    assert plan.command_code == "Get_CarCondition"
    assert plan.property_codes == ()


def test_sda_condition_plan_uses_application_func_codes():
    tree = {
        "data": [
            {"id": "10", "parentId": "0", "applicationFuncCode": "#carCondition"},
            {"id": "11", "parentId": "10", "applicationFuncCode": "#socLeft"},
            {"id": "12", "parentId": "10", "applicationFuncCode": "#chargingInfo"},
        ]
    }

    plan = sda_condition_plan(
        {"mqttConnectionInfos": [{"carConfigJson": json.dumps(tree)}]}
    )

    assert plan.property_codes == ("carCondition", "socLeft", "chargingInfo")


def test_sda_condition_plan_without_tree():
    plan = sda_condition_plan({"mqttConnectionInfos": [{}]})

    assert plan.device_did is None
    assert plan.service_code == "CarCondition"
    assert plan.command_code == "Get_CarCondition"
    assert plan.property_codes == ()


def test_login_request_payload_shape():
    payload = login_request_payload("login-did", "req-1")
    assert payload["did"] == "login-did"
    assert payload["mt"] == "loginout"
    assert payload["sers"][0]["service_code"] == "login"


def test_request_payloads_use_the_app_field_set():
    login = login_request_payload(
        "login-did",
        "req-1",
        basic_info={"ruid": "login-did", "vin": "VIN123", "uid": None, "mc": "mc-1"},
    )
    assert set(login) == {"did", "r", "v", "mt", "e", "z", "tf", "dt", "sers", "b"}
    assert "a" not in login and "pl" not in login
    assert login["b"] == {"vin": "VIN123", "mc": "mc-1", "ruid": "login-did"}

    condition = condition_request_payload(
        "car-did",
        "login-did",
        "secret-key-12345",
        "req-1",
        basic_info={"ruid": "login-did", "vin": "VIN123", "cid": "car-1"},
    )
    assert "a" not in condition and "pl" not in condition
    assert condition["b"] == {"vin": "VIN123", "cid": "car-1", "ruid": "login-did"}
    services = aes_cbc_decrypt(condition["sers"], "secret-key-12345", "req-1")
    assert services[0]["service_code"] == "car_condition"


def test_request_payloads_accept_optional_fields():
    payload = login_request_payload(
        "login-did", "req-1", {"ruid": "login-did"}, ms=1, st=2, time_type=3
    )
    assert payload["ms"] == 1
    assert payload["st"] == 2
    assert payload["timeType"] == 3

    condition = condition_request_payload(
        "car-did",
        "login-did",
        "secret-key-12345",
        "req-1",
        basic_info={"ruid": "login-did"},
        rt=None,
    )
    assert "rt" not in condition


def test_normalize_s05_params_maps_telemetry():
    params = {
        "lastUpdatedTime": "2026-09-18T10:00:00Z",
        "soc": 63,
        "remainedPowerMile": 210,
        "totalOdometer": 18300,
        "totalMeterYesterday": 42.5,
        "igniteCumulativeMileage": 12.25,
        "engineStatus": 1,
        "powerStatusFeedBack": 2,
        "electronichandbrakeStatus": 0,
        "airConditioningSetTemperature": 22.5,
        "airStatus": 1,
        "vehicleTemperature": 21.5,
        "innerHumidity": 444,
        "frontDefrostStatus": 1,
        "airPurifierStatus": 3,
        "airConditioningHairRatings": 4,
        "steeringWheelHeating": 1,
        "ChrgSts": 3,
        "acChargeGunConnectionState": 3,
        "BattACChrgInCurr": 16.2,
        "chargDeltMins": 95,
        "dcDhargeGunConnectionState": 0,
        "hood": 0,
        "highBeam": 1,
        "lowBeam": 0,
        "positionLamp": 1,
        "frontFoglamp": 0,
        "rearFoglamp": 0,
        "turnLndicatorLeft": 0,
        "turnLndicatorRight": 1,
        "driverDoor": 1,
        "passengerDoor": 0,
        "leftRearDoor": 0,
        "rightRearDoor": 1,
        "trunk": 0,
        "driverDoorLock": 0,
        "passengerDoorLock": 0,
        "diverWindow": 1,
        "passengerWindow": 0,
        "leftRearWindow": 0,
        "rightRearWindow": 0,
        "lfTyrePressure": 240,
        "rfTyrePressure": 239,
        "lrTyrePressure": 245,
        "rrTyrePressure": 241,
        "rrPressureWarning": 1,
        "leftFrontTireTemperature": 31.5,
        "rightFrontTireTemperature": 32.0,
        "leftRearTireTemperature": 30.5,
        "rightRearTireTemperature": 33.0,
        "driverSeatHeatStatus": 2,
        "driverSeatAirStatus": 2,
        "passengerSeatHeatStatus": 0,
        "passengerSeatAirStatus": 0,
        "leftBackSeatHeatStatus": 2,
        "leftBackSeatVentilateStatus": 4,
        "rightBackSeatHeatStatus": 0,
        "rightBackSeatVentilateStatus": 0,
    }
    condition = normalize_s05_params(params)
    assert condition["lastUpdatedAt"] == 1789725600000
    assert condition["vehicleStatus"]["soc"] == 63
    assert condition["vehicleStatus"]["drvMileage"] == 210
    assert condition["vehicleStatus"]["totalMileage"] == 18300
    assert condition["vehicleStatus"]["totalMeterYesterday"] == 42.5
    assert condition["vehicleStatus"]["igniteCumulativeMileage"] == 12.25
    assert condition["vehicleStatus"]["steeringWheelHeater"] == 1
    assert condition["hvac"]["acStatus"] == 1
    assert condition["hvac"]["remoteTemp"] == 225
    assert condition["charge"]["chargeStatus"] == 3
    assert condition["door"]["doors"] == [1, 0, 0, 1]
    assert condition["door"]["trunk"] == 0
    assert condition["door"]["driverLock"] == 0
    assert condition["window"]["windows"] == [1, 0, 0, 0]
    assert condition["tire"]["leftFront"]["pressure"] == 240
    assert condition["tire"]["leftFront"]["temperature"] == 31.5
    assert condition["tire"]["rightBack"]["alarm"] == 1
    assert condition["seat"]["leftFront"]["heatStatus"] == 2
    assert condition["seat"]["leftFront"]["ventStatus"] == 2
    assert condition["seat"]["leftBack"]["heatStatus"] == 2
    assert condition["seat"]["leftBack"]["ventStatus"] is None
    assert condition["seat"]["rightBack"]["heatStatus"] == 0
    assert condition["vehicleStatus"]["engineSts"] == 1
    assert condition["vehicleStatus"]["powerStatus"] == 2
    assert condition["vehicleStatus"]["epbSts"] == 0
    assert condition["vehicleStatus"]["connectStatus"] == 1
    assert condition["hvac"]["insideTemp"] == 215
    assert condition["hvac"]["insideHumidity"] == 444
    assert condition["hvac"]["defrostStatus"] == 1
    assert condition["hvac"]["insideAirQualityLevel"] == 3
    assert condition["hvac"]["fanLevel"] == 4
    assert condition["charge"]["acChargeCurrent"] == 16.2
    assert condition["charge"]["chargeCurrent"] == 16.2
    assert condition["charge"]["remainChargeTime"] == 95
    assert condition["charge"]["dcChargeGunConnectStatus"] is False
    assert condition["door"]["hood"] == 0
    assert condition["lamp"]["highBeam"] == 1
    assert condition["lamp"]["positionLamp"] == 1
    assert condition["lamp"]["rightTurn"] == 1
    assert condition["lamp"]["lowBeam"] == 0


def test_normalize_s05_params_picks_the_dc_current_while_dc_charging():
    condition = normalize_s05_params(
        {"ChrgSts": 4, "BattACChrgInCurr": 0, "BattDCChrgInCurr": 60.5}
    )

    assert condition["charge"]["chargeCurrent"] == 60.5
    assert condition["charge"]["dcChargeCurrent"] == 60.5
    assert condition["charge"]["acChargeCurrent"] == 0.0


def test_normalize_s05_params_picks_the_ac_current_while_ac_charging():
    condition = normalize_s05_params(
        {"ChrgSts": 3, "BattACChrgInCurr": 16.2, "BattDCChrgInCurr": 0}
    )

    assert condition["charge"]["chargeCurrent"] == 16.2
    assert condition["charge"]["acChargeCurrent"] == 16.2
    assert condition["charge"]["dcChargeCurrent"] == 0.0


def test_normalize_s05_params_zeroes_the_currents_while_only_connected():
    condition = normalize_s05_params(
        {"ChrgSts": 2, "BattACChrgInCurr": 0, "BattDCChrgInCurr": 60.5}
    )

    assert condition["charge"]["chargeCurrent"] == 0.0
    assert condition["charge"]["acChargeCurrent"] == 0.0
    assert condition["charge"]["dcChargeCurrent"] == 0.0


def test_normalize_s05_params_drops_the_post_session_sentinel():
    condition = normalize_s05_params({"ChrgSts": 0, "BattDCChrgInCurr": 2538})

    assert condition["charge"]["dcChargeCurrent"] == 0.0
    assert condition["charge"]["chargeCurrent"] == 0.0


def test_normalize_s05_params_drops_an_out_of_range_current_while_charging():
    condition = normalize_s05_params({"ChrgSts": 4, "BattDCChrgInCurr": 2538})

    assert condition["charge"]["dcChargeCurrent"] is None
    assert condition["charge"]["chargeCurrent"] is None


def test_clean_charge_current_magnitude_accepts_negative_readings():
    assert clean_charge_current(-60.5) is None
    assert clean_charge_current_magnitude(-60.5) == 60.5
    assert clean_charge_current_magnitude(60.5) == 60.5
    assert clean_charge_current_magnitude(-2538) is None
    assert clean_charge_current_magnitude(2538) is None


def test_charge_currents_keep_the_magnitude_of_a_negative_dc_current():
    assert charge_currents(0, -60.5, 4) == (0.0, 60.5, 60.5)


def test_normalize_s05_params_accepts_a_negative_dc_current():
    condition = normalize_s05_params({"ChrgSts": 4, "BattDCChrgInCurr": -60.5})

    assert condition["charge"]["chargeCurrent"] == 60.5
    assert condition["charge"]["dcChargeCurrent"] == 60.5
    assert condition["charge"]["acChargeCurrent"] is None


def test_normalize_s05_params_drops_a_negative_sentinel_while_charging():
    condition = normalize_s05_params({"ChrgSts": 4, "BattDCChrgInCurr": -2538})

    assert condition["charge"]["dcChargeCurrent"] is None
    assert condition["charge"]["chargeCurrent"] is None


def test_normalize_sda_params_keeps_the_generic_current_strict():
    condition = normalize_sda_params(
        {
            "BcuChrgSts": 1,
            "AcChrgCnctrSts": 1,
            "DcChrgCnctrSts": 0,
            "BcuBattI": "-8.4",
            "ObcChrgInpAcIL1": "28.3",
            "ObcChrgDcI": "8.5",
        }
    )

    assert condition["charge"]["chargeCurrent"] is None
    assert condition["charge"]["acChargeCurrent"] == 28.3
    assert condition["charge"]["dcChargeCurrent"] == 8.5


def test_normalize_s05_params_keeps_reported_currents_for_an_unknown_state():
    condition = normalize_s05_params(
        {"ChrgSts": 9, "BattACChrgInCurr": 0, "BattDCChrgInCurr": 60.5}
    )

    assert condition["charge"]["chargeCurrent"] == 60.5
    assert condition["charge"]["dcChargeCurrent"] == 60.5
    assert condition["charge"]["acChargeCurrent"] == 0.0


def test_normalize_s05_params_maps_the_dc_gun_from_the_state():
    condition = normalize_s05_params({"ChrgSts": 2})

    assert condition["charge"]["chargeConStatus"] is True
    assert condition["charge"]["dcChargeGunConnectStatus"] is True
    assert condition["charge"]["acChargeGunConnectStatus"] is False


def test_normalize_s05_params_maps_the_ac_gun_from_the_state():
    condition = normalize_s05_params({"ChrgSts": 1})

    assert condition["charge"]["chargeConStatus"] is True
    assert condition["charge"]["acChargeGunConnectStatus"] is True
    assert condition["charge"]["dcChargeGunConnectStatus"] is False


def test_normalize_s05_params_uses_the_gun_fields_when_not_charging():
    connected = normalize_s05_params(
        {
            "ChrgSts": 0,
            "acChargeGunConnectionState": 1,
            "dcChargeGunConnectionState": 0,
        }
    )

    assert connected["charge"]["chargeConStatus"] is True
    assert connected["charge"]["acChargeGunConnectStatus"] is True
    assert connected["charge"]["dcChargeGunConnectStatus"] is False

    unplugged = normalize_s05_params(
        {
            "ChrgSts": 0,
            "acChargeGunConnectionState": 0,
            "dcChargeGunConnectionState": 0,
        }
    )

    assert unplugged["charge"]["chargeConStatus"] is False
    assert unplugged["charge"]["acChargeGunConnectStatus"] is False
    assert unplugged["charge"]["dcChargeGunConnectStatus"] is False


def test_normalize_s05_params_maps_the_charging_stopped_state():
    condition = normalize_s05_params(
        {
            "ChrgSts": 5,
            "acChargeGunConnectionState": 1,
            "dcChargeGunConnectionState": 0,
            "BattACChrgInCurr": 0,
            "BattDCChrgInCurr": 0,
        }
    )

    assert condition["charge"]["chargeStatus"] == 5
    assert condition["charge"]["chargeConStatus"] is True
    assert condition["charge"]["acChargeGunConnectStatus"] is True
    assert condition["charge"]["dcChargeGunConnectStatus"] is False
    assert condition["charge"]["chargeCurrent"] == 0.0


def test_charge_state_recognizes_the_charging_stopped_state():
    assert charge_state(5) == CHARGE_STATE_CHARGE_STOPPED
    assert charge_is_active(5) is False
    assert charge_is_active("5") is False
    assert charge_state(9) is None
    assert charge_is_active(9) is None


def test_normalize_s05_params_falls_back_to_the_gun_fields_without_a_state():
    condition = normalize_s05_params(
        {"acChargeGunConnectionState": 0, "dcDhargeGunConnectionState": 3}
    )

    assert condition["charge"]["chargeConStatus"] is True
    assert condition["charge"]["dcChargeGunConnectStatus"] is True
    assert condition["charge"]["acChargeGunConnectStatus"] is False

    unrecognized = normalize_s05_params(
        {"ChrgSts": 9, "acChargeGunConnectionState": 3}
    )

    assert unrecognized["charge"]["chargeConStatus"] is True
    assert unrecognized["charge"]["acChargeGunConnectStatus"] is True
    assert unrecognized["charge"]["dcChargeGunConnectStatus"] is None


def test_normalize_s05_params_maps_outside_temperature():
    normalized = normalize_s05_params({"outsideTemperature": 18.5})

    assert normalized["hvac"]["outsideTemp"] == 185.0

    fallback = normalize_s05_params({"externalTemperature": 20.0})

    assert fallback["hvac"]["outsideTemp"] == 200.0
    assert normalize_s05_params({})["hvac"]["outsideTemp"] is None


def test_normalize_s05_params_maps_warnings_and_window_openings():
    params = {
        "batt12VLightStatus": 0,
        "tpmsLightStatus": 1,
        "absLightStatus": 0,
        "airBagLightStatus": 1,
        "brakeFluidLightStatus": 0,
        "brakeLightStatus": 0,
        "epsLightStatus": 0,
        "powerLimitLightStatus": 0,
        "powerSystemLightStatus": 0,
        "bcuBattSocLightStatus": 0,
        "coolanTemperatureLightStatus": 0,
        "keyLowPower": 1,
        "airRecycleStatus": 1,
        "leftAnteriorWindowDegree": 20,
        "rightAnteriorWindowDegree": 0,
        "leftRearWindowDegree": 97,
        "rightRearWindowDegree": 92,
    }

    normalized = normalize_s05_params(params)

    assert normalized["warningLights"]["tpms"] is True
    assert normalized["warningLights"]["battery12v"] is False
    assert normalized["warningLights"]["airbag"] is True
    assert normalized["warningLights"]["coolantTemperature"] is False
    assert normalized["keyBatteryLow"] is True
    assert normalized["airRecirculation"] is True
    assert normalized["windowOpenings"] == {
        "frontLeft": 20,
        "frontRight": 0,
        "rearLeft": 97,
        "rearRight": 92,
    }

    empty = normalize_s05_params({})

    assert set(empty["warningLights"]) == {
        "battery12v",
        "tpms",
        "abs",
        "airbag",
        "brakeFluid",
        "brake",
        "eps",
        "powerLimit",
        "powerSystem",
        "tractionBatteryLow",
        "coolantTemperature",
    }
    assert empty["warningLights"]["tpms"] is None
    assert empty["keyBatteryLow"] is None
    assert empty["airRecirculation"] is None
    assert empty["windowOpenings"]["frontLeft"] is None


def test_normalize_s05_params_blanks_warnings_while_the_vehicle_is_off():
    normalized = normalize_s05_params(
        {
            "absLightStatus": 1,
            "airBagLightStatus": 1,
            "brakeLightStatus": 1,
            "tpmsLightStatus": 1,
            "coolanTemperatureLightStatus": 1,
            "powerStatusFeedBack": 0,
        }
    )

    assert normalized["warningLights"]["abs"] is None
    assert normalized["warningLights"]["airbag"] is None
    assert normalized["warningLights"]["brake"] is None
    assert normalized["warningLights"]["tpms"] is None
    assert normalized["warningLights"]["coolantTemperature"] is None
    assert normalized["vehicleStatus"]["powerStatus"] == 0


def test_normalize_s05_params_keeps_warnings_while_the_vehicle_is_on():
    normalized = normalize_s05_params(
        {
            "absLightStatus": 1,
            "airBagLightStatus": 1,
            "brakeLightStatus": 0,
            "coolanTemperatureLightStatus": 0,
            "powerStatusFeedBack": 2,
        }
    )

    assert normalized["warningLights"]["abs"] is True
    assert normalized["warningLights"]["airbag"] is True
    assert normalized["warningLights"]["brake"] is False
    assert normalized["warningLights"]["coolantTemperature"] is False
    assert normalized["vehicleStatus"]["powerStatus"] == 2


def test_normalize_s05_params_keeps_warnings_without_a_power_state():
    normalized = normalize_s05_params({"absLightStatus": 1})

    assert normalized["warningLights"]["abs"] is True


def test_normalize_s05_params_maps_remain_charge_time_sentinel():
    sentinel = normalize_s05_params({"chargDeltMins": 8191})
    normal = normalize_s05_params({"chargDeltMins": 120})

    assert sentinel["charge"]["remainChargeTime"] is None
    assert normal["charge"]["remainChargeTime"] == 120


def test_normalize_s05_params_keeps_the_raw_inner_humidity():
    raw = normalize_s05_params({"innerHumidity": 453})
    boundary = normalize_s05_params({"innerHumidity": 1000})
    out_of_range = normalize_s05_params({"innerHumidity": 1200})
    absent = normalize_s05_params({})

    assert raw["hvac"]["insideHumidity"] == 453
    assert boundary["hvac"]["insideHumidity"] == 1000
    assert out_of_range["hvac"]["insideHumidity"] == 1200
    assert absent["hvac"]["insideHumidity"] is None


def test_normalize_s05_params_maps_seat_sides_and_scales():
    condition = normalize_s05_params(
        {
            "driverSeatHeatStatus": 2,
            "driverSeatAirStatus": 3,
            "passengerSeatHeatStatus": 6,
            "passengerSeatAirStatus": 1,
            "leftBackSeatHeatStatus": 0,
            "rightBackSeatVentilateStatus": 4,
        }
    )
    assert condition["seat"]["leftFront"]["heatStatus"] == 2
    assert condition["seat"]["leftFront"]["ventStatus"] == 3
    assert condition["seat"]["rightFront"]["heatStatus"] is None
    assert condition["seat"]["rightFront"]["ventStatus"] == 1
    assert condition["seat"]["leftBack"]["heatStatus"] == 0
    assert condition["seat"]["rightBack"]["heatStatus"] is None
    assert condition["seat"]["rightBack"]["ventStatus"] is None


def test_normalize_s05_params_accepts_legacy_spellings():
    condition = normalize_s05_params(
        {
            "lastUpdatedAt": "2026-09-18T10:00:00Z",
            "dcChargeGunConnectionState": 3,
            "hoodStatus": 1,
        }
    )
    assert condition["lastUpdatedAt"] == 1789725600000
    assert condition["charge"]["dcChargeGunConnectStatus"] is True
    assert condition["charge"]["chargeConStatus"] is True
    assert condition["door"]["hood"] == 1


def test_normalize_s05_params_uses_latest_date_as_report_time():
    condition = normalize_s05_params({"latestDate": "2026-09-18T10:00:00Z"})
    assert condition["lastUpdatedAt"] == 1789725600000


def test_normalize_s05_params_ignores_unknown_fields():
    condition = normalize_s05_params({"chargeCoverStatus": 3})
    assert "chargeCoverStatus" not in condition["charge"]
    assert condition["door"]["hood"] is None


def test_normalize_s05_params_maps_fuel_fields():
    condition = normalize_s05_params({"remainingFuel": 48, "remainedOilMile": 312.4})
    assert condition["fuel"]["leftPercent"] == 48
    assert condition["fuel"]["remainingRange"] == 312


def test_normalize_s05_params_without_fuel_fields():
    condition = normalize_s05_params({"soc": 71})
    assert condition["fuel"]["leftPercent"] is None
    assert condition["fuel"]["remainingRange"] is None


def test_mapped_s05_keys_cover_every_key_the_normalization_reads():
    source = inspect.getsource(normalize_s05_params)
    keys_read = set(re.findall(r'params\.get\("([A-Za-z0-9_]+)"', source))
    for call in re.findall(r"_first\(\s*params\s*,\s*([^)]*)\)", source):
        keys_read.update(re.findall(r'"([A-Za-z0-9_]+)"', call))
    assert keys_read
    assert keys_read <= MAPPED_S05_KEYS


def test_normalize_sda_params_maps_the_e07_condition():
    params = {
        "BcuSocDisp": "91.6",
        "VIUSocDisp": 92,
        "VcuResiMilg": 422,
        "CdcTotMilg": "18894.2",
        "EspVehSpd": 0,
        "BcuChrgSts": 1,
        "AcChrgCnctrSts": 1,
        "DcChrgCnctrSts": 0,
        "ObcChrgInpAcIL1": "28.3",
        "BcuChrgTiDisp": 66,
        "TboxSocChrgTarSet": 100,
        "DrvrDoorSts": 2,
        "PassDoorSts": 2,
        "LeReDoorSts": 2,
        "RiReDoorSts": 2,
        "ObjStTypePLGDoorSt": 2,
        "FrtGateSts": 2,
        "DrvrDoorLockLogicSts": 2,
        "PassDoorLockLogicSts": 2,
        "DrvrWinPos": 0,
        "PassWinPos": 0,
        "LeReWinPos": 0,
        "RiReWinPos": 0,
        "ITMSAcIntT": "18.0",
        "ITMSDrvrAutT": "24.0",
        "ITMSACOnOff": 0,
        "ITMSPm25InCarDens": 4,
        "DrHeatGear": "0",
        "DrVentGear": "0",
        "SteeringHeat": 0,
    }

    normalized = normalize_sda_params(params)

    assert normalized["vehicleStatus"]["soc"] == 92
    assert normalized["vehicleStatus"]["drvMileage"] == 422
    assert normalized["vehicleStatus"]["totalMileage"] == 18894.2
    assert normalized["charge"]["chargeStatus"] == 1
    assert normalized["charge"]["chargeConStatus"] == 1
    assert normalized["charge"]["acChargeCurrent"] == 28.3
    assert normalized["charge"]["remainChargeTime"] == 66
    assert normalized["charge"]["maxSocPercent"] == 100
    assert normalized["door"]["doors"] == [0, 0, 0, 0]
    assert normalized["door"]["trunk"] == 0
    assert normalized["door"]["hood"] == 0
    assert normalized["door"]["driverLock"] == 0
    assert normalized["window"]["windows"] == [0, 0, 0, 0]
    assert normalized["hvac"]["insideTemp"] == 180.0
    assert normalized["hvac"]["remoteTemp"] == 240.0
    assert normalized["hvac"]["acStatus"] == 0
    assert normalized["seat"]["leftFront"]["heatStatus"] == 0
    assert normalized["seat"]["leftFront"]["ventStatus"] == 0


def test_normalize_sda_params_marks_open_states():
    params = {
        "DrvrDoorSts": 1,
        "ObjStTypePLGDoorSt": 1,
        "DrvrDoorLockLogicSts": 2,
        "DrvrWinPos": 50,
    }

    normalized = normalize_sda_params(params)

    assert normalized["door"]["doors"][0] == 1
    assert normalized["door"]["trunk"] == 1
    assert normalized["door"]["driverLock"] == 0
    assert normalized["window"]["windows"][0] == 50


def test_normalize_sda_params_unlocked_and_charge_sentinel():
    params = {"DrvrDoorLockLogicSts": 1, "BcuChrgTiDisp": 8191}

    normalized = normalize_sda_params(params)

    assert normalized["door"]["driverLock"] == 1
    assert normalized["charge"]["remainChargeTime"] is None


def test_unmapped_s05_keys_returns_only_unknown_fields():
    assert unmapped_s05_keys(
        {"soc": 71, "chargeCoverStatus": 3, "skyWindowDegree": 0}
    ) == {"chargeCoverStatus", "skyWindowDegree"}


def test_unmapped_s05_keys_empty_for_mapped_payload():
    assert unmapped_s05_keys({key: 0 for key in MAPPED_S05_KEYS}) == set()


# SDA broker bootstrap and session (change add-sda-remote-controls).


class _WriteLog:
    """StreamWriter stand-in that keeps every write as its own packet."""

    def __init__(self) -> None:
        self.packets: list[bytes] = []
        self.closed = False

    def write(self, data: bytes) -> None:
        self.packets.append(bytes(data))

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        pass


class _ScriptedBroker:
    """Broker double whose pre-fed bytes are consumed in order."""

    def __init__(self, script: bytes = b"") -> None:
        self.reader = asyncio.StreamReader()
        self.writer = _WriteLog()
        if script:
            self.reader.feed_data(script)


def _install_broker(monkeypatch: Any, broker: _ScriptedBroker) -> None:
    async def fake_open_connection(host, port, *, ssl=None, server_hostname=None):
        return broker.reader, broker.writer

    monkeypatch.setattr(asyncio, "open_connection", fake_open_connection)


def _connack(reason: int) -> bytes:
    return bytes([0x20, 0x02, 0x00, reason])


def _suback(packet_id: int, reasons: list[int]) -> bytes:
    body = packet_id.to_bytes(2, "big") + b"\x00" + bytes(reasons)
    return bytes([0x90, len(body)]) + body


def _split_packet(data: bytes) -> tuple[int, bytes]:
    first = data[0]
    multiplier, remaining, pos = 1, 0, 1
    while True:
        byte = data[pos]
        pos += 1
        remaining += (byte & 0x7F) * multiplier
        if not byte & 0x80:
            break
        multiplier *= 128
    return first, data[pos : pos + remaining]


def test_parse_sda_broker_config_unwraps_and_normalizes_types():
    raw = {
        "code": "0",
        "data": {
            "mqttConnectionInfos": [
                {
                    "mqttHost": "prod-appmq.sda.changanauto.sg",
                    "mqttPort": "8883",
                    "clusterName": "APN1",
                    "authType": "2",
                }
            ]
        },
    }

    config = parse_sda_broker_config(raw)

    assert config.usable
    assert config.host == "prod-appmq.sda.changanauto.sg"
    assert config.port == 8883
    assert config.cluster_name == "APN1"
    assert config.auth_type == 2
    assert config.payload["mqttHost"] == "prod-appmq.sda.changanauto.sg"


def test_parse_sda_broker_config_tolerates_missing_fields():
    assert parse_sda_broker_config({}).usable is False
    assert parse_sda_broker_config(["not", "a", "mapping"]).usable is False
    assert parse_sda_broker_config({"host": "h"}).usable is False
    assert parse_sda_broker_config(
        {"host": "h", "port": "not-a-port"}
    ).port is None


def test_device_id_candidates_walks_nested_sources_in_order():
    ca_config = {
        "mqttConnectionInfos": [
            {"deviceId": "did-ca", "clusterInfos": [{"deviceId": "did-ca"}]}
        ]
    }
    tree = {
        "data": {
            "nodes": [
                {"deviceId": "did-tree"},
                {"child": {"deviceId": "did-tree"}},
                {"deviceId": 12345},
                {"deviceId": ""},
            ]
        }
    }

    assert device_id_candidates(ca_config, tree) == ("did-ca", "did-tree")
    assert device_id_candidates() == ()


def test_sda_session_topics_uses_the_car_id_event_topic():
    topics = sda_session_topics({}, "did-1", car_id="car-1")

    assert topics == (
        "$vdp/did-1/server/loginout",
        "$vdp/did-1/car-1/server/event",
        "$vdp/did-1/client/loginout",
        "$vdp/did-1/properties/set/req",
    )

    without_car = sda_session_topics({}, "did-1")

    assert "$vdp/did-1/did-1/server/event" in without_car
    assert "$vdp/did-1/car-1/server/event" not in without_car


def test_parse_suback_returns_packet_id_and_reason_codes():
    assert parse_suback(0x90, b"\x00\x01\x00\x01") == (1, [1])
    assert parse_suback(0x90, b"\x00\x01\x00\x87\x01") == (1, [0x87, 1])
    assert parse_suback(0x90, b"\x00\x01\x00") == (1, [])
    assert parse_suback(0x90, b"\x00\x01\x02\x11\x22\x01") == (1, [1])
    assert parse_suback(0x90, b"\x00") == (None, [])
    assert parse_suback(0x90, b"\x00\x01\x80") == (None, [])
    assert parse_suback(0x30, b"\x00\x01\x00") == (None, [])


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"\x00",
        b"\x00\x05ab",
        b"\x00\x01a\x80",
        b"\x00\x01a\x05",
        b"\x00\x01a\x00not-json",
        b"\x00\x01a\x00[1, 2]",
    ],
)
def test_parse_publish_rejects_malformed_bodies(body):
    with pytest.raises(ValueError):
        parse_publish(0x30, body)


def test_parse_publish_accepts_a_json_object_body():
    topic, payload, packet_id = parse_publish(0x30, b'\x00\x01a\x00{"x": 1}')

    assert topic == "a"
    assert payload == {"x": 1}
    assert packet_id is None


@pytest.mark.asyncio
async def test_sda_broker_session_tries_dids_subscribes_and_acks(monkeypatch):
    event = build_publish_packet(
        "$vdp/did-2/car-1/server/event",
        {
            "h": {"r": "ev-1", "sk": "Et_IT001", "m": "Et_IT001"},
            "d": {"p": {"DrvrDoorLockLogicSts": 2}},
        },
        qos=1,
        packet_id=7,
    )
    broker = _ScriptedBroker(
        _connack(0x87) + _connack(0x00) + _suback(1, [0x01, 0x00]) + event
    )
    _install_broker(monkeypatch, broker)

    result = await sda_broker_session(
        "prod-appmq.example",
        8883,
        device_ids=["did-1", "did-2", "did-2"],
        password="token-123",
        topics=["$vdp/did-2/car-1/server/event", "$vdp/did-2/client/loginout"],
        seconds=0.05,
        timeout=1.0,
    )

    assert result.connected is True
    assert result.device_id == "did-2"
    assert result.attempts == (
        {"device_id": "did-1", "connack_reason": 0x87},
        {"device_id": "did-2", "connack_reason": 0},
    )
    assert result.subscriptions == (
        {"topic": "$vdp/did-2/car-1/server/event", "reason": 0x01},
        {"topic": "$vdp/did-2/client/loginout", "reason": 0x00},
    )
    assert len(result.messages) == 1
    assert result.messages[0]["topic"] == "$vdp/did-2/car-1/server/event"
    assert result.messages[0]["qos"] == 1
    assert result.messages[0]["dup"] is False
    assert result.messages[0]["payload"]["d"]["p"]["DrvrDoorLockLogicSts"] == 2
    # The QoS 1 delivery is acknowledged and the session closes with DISCONNECT.
    assert broker.writer.packets[-2] == build_puback_packet(7)
    assert broker.writer.packets[-1] == build_disconnect_packet()
    assert broker.writer.closed
    # A read-only session never publishes (CONNECT/SUBSCRIBE/PUBACK only).
    assert not any(packet[0] >> 4 == 3 for packet in broker.writer.packets)


@pytest.mark.asyncio
async def test_sda_broker_session_reports_rejections_without_subscribing(monkeypatch):
    broker = _ScriptedBroker(_connack(0x87) + _connack(0x9E))
    _install_broker(monkeypatch, broker)

    result = await sda_broker_session(
        "prod-appmq.example",
        8883,
        device_ids=["did-1", "did-2"],
        password="token-123",
        topics=["$vdp/did-1/car-1/server/event"],
        seconds=0.02,
        timeout=1.0,
    )

    assert result.connected is False
    assert result.device_id is None
    assert result.connack_reason == 0x9E
    assert [attempt["connack_reason"] for attempt in result.attempts] == [0x87, 0x9E]
    assert result.messages == ()
    assert not any(packet[0] >> 4 in (3, 8) for packet in broker.writer.packets)


@pytest.mark.asyncio
async def test_sda_broker_session_login_publishes_the_loginout(monkeypatch):
    secret = "secret-key-12345"
    login_response = build_publish_packet(
        "$vdp/did-1/server/loginout",
        {"r": "login-1", "rs": [{"params": {"secretKey": secret}}]},
        qos=1,
        packet_id=3,
    )
    broker = _ScriptedBroker(_connack(0x00) + _suback(1, [0x01]) + login_response)
    _install_broker(monkeypatch, broker)

    result = await sda_broker_session(
        "prod-appmq.example",
        8883,
        device_ids=["did-1"],
        password="token-123",
        topics=["$vdp/did-1/server/loginout"],
        seconds=0.05,
        timeout=1.0,
        login=True,
    )

    publishes = [packet for packet in broker.writer.packets if packet[0] >> 4 == 3]
    assert len(publishes) == 1
    first, body = _split_packet(publishes[0])
    topic, payload, _ = parse_publish(first, body)
    assert topic == "$vdp/did-1/client/loginout"
    assert payload["did"] == "did-1"
    assert payload["mt"] == "loginout"
    assert result.secret_key == secret
    assert build_puback_packet(3) in broker.writer.packets


@pytest.mark.asyncio
async def test_sda_broker_session_skips_malformed_publishes(monkeypatch):
    malformed = bytes([0x30, 0x01, 0x00])
    event = build_publish_packet(
        "$vdp/did-1/car-1/server/event",
        {"d": {"p": {"DrvrDoorLockLogicSts": 2}}},
    )
    broker = _ScriptedBroker(_connack(0x00) + _suback(1, [0x01]) + malformed + event)
    _install_broker(monkeypatch, broker)

    result = await sda_broker_session(
        "prod-appmq.example",
        8883,
        device_ids=["did-1"],
        password="token-123",
        topics=["$vdp/did-1/car-1/server/event"],
        seconds=0.05,
        timeout=1.0,
    )

    assert result.connected is True
    assert len(result.messages) == 1
    assert result.messages[0]["payload"]["d"]["p"]["DrvrDoorLockLogicSts"] == 2


def test_is_phev_model_recognizes_the_s05_model_codes():
    assert is_phev_model("SC6460AAAA7HEV") is True
    assert is_phev_model("SC6464AAKPHEV") is True
    assert is_phev_model("SC6464AAKBEV") is False
    assert is_phev_model(None) is False
    assert is_phev_model("C857P1") is False


def test_normalize_s05_params_uses_the_phev_gun_rule():
    payload = {
        "ChrgSts": 0,
        "acChargeGunConnectionState": 1,
        "dcChargeGunConnectionState": 0,
    }

    phev = normalize_s05_params(payload, model_code="SC6460AAAA7HEV")
    assert phev["charge"]["chargeConStatus"] is False
    assert phev["charge"]["acChargeGunConnectStatus"] is False
    assert phev["charge"]["dcChargeGunConnectStatus"] is False

    bev = normalize_s05_params(payload, model_code="SC6464AAKBEV")
    assert bev["charge"]["chargeConStatus"] is True
    assert bev["charge"]["acChargeGunConnectStatus"] is True
    assert bev["charge"]["dcChargeGunConnectStatus"] is False

    generic = normalize_s05_params(payload)
    assert generic["charge"]["chargeConStatus"] is True
    assert generic["charge"]["acChargeGunConnectStatus"] is True


def test_normalize_s05_params_maps_the_phev_charge_states():
    connected = normalize_s05_params(
        {
            "ChrgSts": 1,
            "acChargeGunConnectionState": 1,
            "dcChargeGunConnectionState": 0,
        },
        model_code="SC6460AAAA7HEV",
    )
    assert connected["charge"]["chargeConStatus"] is True
    assert connected["charge"]["acChargeGunConnectStatus"] is True
    assert connected["charge"]["dcChargeGunConnectStatus"] is False

    charging = normalize_s05_params(
        {
            "ChrgSts": 3,
            "acChargeGunConnectionState": 1,
            "dcChargeGunConnectionState": 0,
            "BattACChrgInCurr": 45.1,
        },
        model_code="SC6460AAAA7HEV",
    )
    assert charging["charge"]["chargeConStatus"] is True
    assert charging["charge"]["acChargeGunConnectStatus"] is True
    assert charging["charge"]["chargeCurrent"] == 45.1

    stopped = normalize_s05_params(
        {
            "ChrgSts": 5,
            "acChargeGunConnectionState": 1,
            "dcChargeGunConnectionState": 0,
        },
        model_code="SC6460AAAA7HEV",
    )
    assert stopped["charge"]["chargeConStatus"] is True
    assert stopped["charge"]["acChargeGunConnectStatus"] is True
    assert stopped["charge"]["dcChargeGunConnectStatus"] is False

    stopped_dc = normalize_s05_params(
        {
            "ChrgSts": 5,
            "acChargeGunConnectionState": 1,
            "dcChargeGunConnectionState": 1,
        },
        model_code="SC6460AAAA7HEV",
    )
    assert stopped_dc["charge"]["chargeConStatus"] is True
    assert stopped_dc["charge"]["acChargeGunConnectStatus"] is False
    assert stopped_dc["charge"]["dcChargeGunConnectStatus"] is True


def test_normalize_s05_params_keeps_the_phev_ac_gun_unknown_when_the_state_is_absent():
    condition = normalize_s05_params(
        {
            "acChargeGunConnectionState": 1,
            "dcChargeGunConnectionState": 0,
        },
        model_code="SC6460AAAA7HEV",
    )

    assert condition["charge"]["chargeConStatus"] is False
    assert condition["charge"]["acChargeGunConnectStatus"] is None
    assert condition["charge"]["dcChargeGunConnectStatus"] is False
