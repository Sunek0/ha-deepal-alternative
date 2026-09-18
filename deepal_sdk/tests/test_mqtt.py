"""Unit tests for the MQTT transport and S05 helpers."""

import json

from deepal.mqtt import (
    aes_cbc_decrypt,
    aes_cbc_encrypt,
    build_connect_packet,
    build_publish_packet,
    build_subscribe_packet,
    condition_request_payload,
    login_request_payload,
    mqtt_remaining_length,
    normalize_s05_params,
    parse_publish,
    secret_from_login_payload,
    topic_device_id,
)


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


def test_normalize_s05_params_maps_telemetry():
    params = {
        "latestDate": "2026-09-18T10:00:00Z",
        "soc": 63,
        "remainedPowerMile": 210,
        "totalOdometer": 18300,
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
        "dcChargeGunConnectionState": 0,
        "hoodStatus": 0,
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
        "driverSeatHeatStatus": 2,
        "driverSeatAirStatus": 1,
        "passengerSeatHeatStatus": 0,
        "passengerSeatAirStatus": 0,
    }
    condition = normalize_s05_params(params)
    assert condition["vehicleStatus"]["soc"] == 63
    assert condition["vehicleStatus"]["drvMileage"] == 210
    assert condition["vehicleStatus"]["totalMileage"] == 18300
    assert condition["vehicleStatus"]["steeringWheelHeater"] == 2
    assert condition["hvac"]["acStatus"] == 1
    assert condition["hvac"]["remoteTemp"] == 225
    assert condition["charge"]["chargeStatus"] == 2
    assert condition["door"]["doors"] == [1, 0, 0, 1]
    assert condition["door"]["trunk"] == 0
    assert condition["door"]["driverLock"] == 0
    assert condition["window"]["windows"] == [1, 0, 0, 0]
    assert condition["tire"]["leftFront"]["pressure"] == 240
    assert condition["tire"]["rightBack"]["alarm"] == 1
    assert condition["seat"]["rightFront"]["heatStatus"] == 2
    assert condition["seat"]["rightFront"]["ventStatus"] == 1
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
