"""Unit tests for the MQTT transport and S05 helpers."""

import asyncio
import json

import pytest

from deepal.mqtt import (
    aes_cbc_decrypt,
    aes_cbc_encrypt,
    build_connect_packet,
    build_disconnect_packet,
    build_pingreq_packet,
    build_puback_packet,
    build_publish_packet,
    build_subscribe_packet,
    condition_request_payload,
    login_request_payload,
    mqtt_remaining_length,
    normalize_s05_params,
    parse_connack,
    parse_publish,
    read_packet_with_keepalive,
    resolve_mqtt_topics,
    secret_from_login_payload,
    topic_device_id,
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
        b"\x00\x3c"
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
        "steeringWheelHeating": 2,
        "engineStatus": 1,
        "powerStatusFeedBack": 2,
        "electronichandbrakeStatus": 0,
        "airConditioningSetTemperature": 22.5,
        "airStatus": 1,
        "vehicleTemperature": 21.5,
        "innerHumidity": 44,
        "frontDefrostStatus": 1,
        "airPurifierStatus": 3,
        "airConditioningHairRatings": 4,
        "ChrgSts": 2,
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
        "driverSeatAirStatus": 1,
        "passengerSeatHeatStatus": 0,
        "passengerSeatAirStatus": 0,
        "leftBackSeatHeatStatus": 1,
        "leftBackSeatVentilateStatus": 2,
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
    assert condition["vehicleStatus"]["steeringWheelHeater"] == 2
    assert condition["hvac"]["acStatus"] == 1
    assert condition["hvac"]["remoteTemp"] == 225
    assert condition["charge"]["chargeStatus"] == 2
    assert condition["door"]["doors"] == [1, 0, 0, 1]
    assert condition["door"]["trunk"] == 0
    assert condition["door"]["driverLock"] == 0
    assert condition["window"]["windows"] == [1, 0, 0, 0]
    assert condition["tire"]["leftFront"]["pressure"] == 240
    assert condition["tire"]["leftFront"]["temperature"] == 31.5
    assert condition["tire"]["rightBack"]["alarm"] == 1
    assert condition["seat"]["rightFront"]["heatStatus"] == 2
    assert condition["seat"]["rightFront"]["ventStatus"] == 1
    assert condition["seat"]["leftBack"]["heatStatus"] == 1
    assert condition["seat"]["leftBack"]["ventStatus"] == 2
    assert condition["seat"]["rightBack"]["heatStatus"] == 0
    assert condition["vehicleStatus"]["engineSts"] == 1
    assert condition["vehicleStatus"]["powerStatus"] == 2
    assert condition["vehicleStatus"]["epbSts"] == 0
    assert condition["vehicleStatus"]["connectStatus"] == 1
    assert condition["hvac"]["insideTemp"] == 215
    assert condition["hvac"]["insideHumidity"] == 44
    assert condition["hvac"]["defrostStatus"] == 1
    assert condition["hvac"]["insideAirQualityLevel"] == 3
    assert condition["hvac"]["fanLevel"] == 4
    assert condition["charge"]["acChargeCurrent"] == 16.2
    assert condition["charge"]["chargeCurrent"] == 16.2
    assert condition["charge"]["remainChargeTime"] == 95
    assert condition["charge"]["dcChargeGunConnectStatus"] == 0
    assert condition["door"]["hood"] == 0
    assert condition["lamp"]["highBeam"] == 1
    assert condition["lamp"]["positionLamp"] == 1
    assert condition["lamp"]["rightTurn"] == 1
    assert condition["lamp"]["lowBeam"] == 0


def test_normalize_s05_params_accepts_legacy_spellings():
    condition = normalize_s05_params(
        {
            "lastUpdatedAt": "2026-09-18T10:00:00Z",
            "dcChargeGunConnectionState": 1,
            "hoodStatus": 1,
        }
    )
    assert condition["lastUpdatedAt"] == 1789725600000
    assert condition["charge"]["dcChargeGunConnectStatus"] == 1
    assert condition["charge"]["chargeConStatus"] == 1
    assert condition["door"]["hood"] == 1


def test_normalize_s05_params_ignores_unrelated_fields():
    condition = normalize_s05_params(
        {
            "latestDate": "2026-09-18T10:00:00Z",
            "chargeCoverStatus": 3,
        }
    )
    assert "chargeCoverStatus" not in condition["charge"]
    assert condition["lastUpdatedAt"] != 1789725600000
    assert condition["door"]["hood"] is None
