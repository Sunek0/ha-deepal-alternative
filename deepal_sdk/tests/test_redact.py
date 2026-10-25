"""Unit tests for the log redaction helpers."""

import logging

import httpx
import pytest

from deepal import DeepalIntlClient
from deepal.redact import is_sensitive_key, redact_for_log, safe_headers


def test_sensitive_keys_masked():
    payload = {
        "email": "user@example.com",
        "vin": "LS5AXXXXX123456",
        "seriralNo": "SN123",
        "soc": 50,
        "nested": {"access_token": "test_token_123"},
    }

    out = redact_for_log(payload)

    assert out["email"] == "[redacted]"
    assert out["vin"] == "[redacted]"
    assert out["seriralNo"] == "[redacted]"
    assert out["soc"] == 50
    assert out["nested"]["access_token"] == "[redacted]"


def test_plate_and_location_masked():
    payload = {
        "plateNumber": "TEST-PLATE-1",
        "licensePlate": "TEST-PLATE-1",
        "Lat": 38.9,
        "Lng": -0.37,
        "latitude": 38.9,
        "longitude": -0.37,
        "carLatitude": 38.9,
        "carLongitude": -0.37,
        "latestDate": "2026-09-30T10:00:00Z",
        "soc": 50,
    }

    out = redact_for_log(payload)

    for key in (
        "plateNumber",
        "licensePlate",
        "Lat",
        "Lng",
        "latitude",
        "longitude",
        "carLatitude",
        "carLongitude",
    ):
        assert out[key] == "[redacted]", key
    assert out["latestDate"] == "2026-09-30T10:00:00Z"
    assert out["soc"] == 50


def test_long_strings_truncated():
    out = redact_for_log({"note": "x" * 600})

    assert "truncated 100 chars" in out["note"]


def test_safe_headers_keeps_region_only():
    out = safe_headers(
        {
            "selectcountry": "ES",
            "appversion": "V1.12.0",
            "language": "es_ES",
            "x-os-version": "9",
            "authorization": "secret",
        }
    )

    assert out == {
        "selectcountry": "ES",
        "appversion": "V1.12.0",
        "language": "es_ES",
        "x-os-version": "9",
    }


def test_vin_variants_redacted_but_innocent_keys_visible():
    payload = {
        "vin": "LS5AXXXXX123456",
        "vinCode": "LS5AXXXXX123456",
        "vehicle_vin": "LS5AXXXXX123456",
        "unlockKeyDrivingStatus": 1,
        "drivingMode": "eco",
        "latestDate": "2026-09-30T10:00:00Z",
    }

    out = redact_for_log(payload)

    assert out["vin"] == "[redacted]"
    assert out["vinCode"] == "[redacted]"
    assert out["vehicle_vin"] == "[redacted]"
    assert out["unlockKeyDrivingStatus"] == 1
    assert out["drivingMode"] == "eco"
    assert out["latestDate"] == "2026-09-30T10:00:00Z"


def test_is_sensitive_key():
    assert is_sensitive_key("X-Tsp-User-Token")
    assert is_sensitive_key("seriralNo")
    assert is_sensitive_key("secretKey")
    assert is_sensitive_key("plateNumber")
    assert is_sensitive_key("Lat")
    assert is_sensitive_key("carLatitude")
    assert is_sensitive_key("vin")
    assert is_sensitive_key("vinCode")
    assert is_sensitive_key("vehicle_vin")
    assert is_sensitive_key("pubKey")
    assert is_sensitive_key("publicKey")
    assert is_sensitive_key("privateKey")
    assert is_sensitive_key("sign")
    assert is_sensitive_key("smsCode")
    assert is_sensitive_key("credential")
    assert is_sensitive_key("passwd")
    assert is_sensitive_key("otp")
    assert is_sensitive_key("clientId")
    assert is_sensitive_key("username")
    assert is_sensitive_key("did")
    assert is_sensitive_key("brokerUrl")
    assert not is_sensitive_key("soc")
    assert not is_sensitive_key("latestDate")
    assert not is_sensitive_key("unlockKeyDrivingStatus")
    # A request parameter whose name merely starts with "sign" stays visible.
    assert not is_sensitive_key("SignalList")


@pytest.mark.parametrize(
    "key",
    [
        "publicKey",
        "public_key",
        "privateKey",
        "secretKey",
        "sign",
        "smsCode",
        "credential",
        "passwd",
        "otp",
        "clientId",
        "username",
        "did",
        "brokerUrl",
        "cacToken",
        "rcToken",
        "serialNo",
    ],
)
def test_audited_redaction_gaps_are_covered(key):
    """The audited lists gaps stay covered by the shared key model."""
    assert is_sensitive_key(key), key


def test_audited_gap_payload_is_masked():
    payload = {
        "publicKey": "PUBKEY-BODY",
        "secretKey": "secret-mqtt-token",
        "smsCode": "sms-123456",
        "sign": "signature",
        "credential": "cred",
        "passwd": "pass",
        "otp": "123456",
        "brokerUrl": "https://broker.example.invalid",
        "clientId": "client-1",
        "did": "device-did",
        "username": "user",
    }

    out = redact_for_log(payload)

    assert all(value == "[redacted]" for value in out.values())


@pytest.mark.asyncio
async def test_api_logging_redacts_payloads(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": True,
                "code": "0",
                "data": {"token": "secret_token", "vin": "LS5AXXXXX123456"},
            },
        )

    transport = httpx.MockTransport(handler)
    client = DeepalIntlClient(
        country="GB",
        language="en_GB",
        device_id="test-device-id",
        enable_api_logging=True,
        httpx_client=httpx.AsyncClient(transport=transport),
    )
    client.access_token = "test_token_123"

    with caplog.at_level(logging.WARNING, logger="deepal_sdk"):
        await client.get_vehicles()
    await client.close()

    assert "[redacted]" in caplog.text
    assert "secret_token" not in caplog.text
    assert "test_token_123" not in caplog.text


def test_safe_headers_keeps_timestamps():
    out = safe_headers(
        {
            "X-Tsp-Timestamp": "1700000000000",
            "X-VCS-Timestamp": "1700000000000",
            "X-Tsp-User-Token": "secret",
        }
    )

    assert out == {
        "x-tsp-timestamp": "1700000000000",
        "x-vcs-timestamp": "1700000000000",
    }


def test_identifier_keys_are_sensitive():
    payload = {
        "uid": "user-1",
        "cid": "car-1",
        "ruid": "device-1",
        "carId": "car-1",
        "car_id": "car-1",
        "soc": 50,
    }

    out = redact_for_log(payload)

    for key in ("uid", "cid", "ruid", "carId", "car_id"):
        assert out[key] == "[redacted]", key
    assert out["soc"] == 50


def test_redact_topic_masks_the_device_segment():
    from deepal.redact import redact_topic

    assert redact_topic("$vdp/device-did/properties/get/res") == (
        "$vdp/[redacted]/properties/get/res"
    )
    assert redact_topic("$vdp/device-did") == "$vdp/[redacted]"
    assert redact_topic("not-a-vdp-topic") == "not-a-vdp-topic"


def test_redact_mqtt_request_id_masks_the_device_prefix():
    from deepal.redact import redact_mqtt_request_id

    assert redact_mqtt_request_id("device-did_1720000000000000") == (
        "[redacted]_1720000000000000"
    )
    assert redact_mqtt_request_id("plain-request-id") == "plain-request-id"


def test_jwt_like_values_are_masked_under_innocent_keys():
    token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.signature"
    out = redact_for_log({"note": token})

    assert out["note"] == "[redacted]"


def test_redact_for_log_accepts_a_larger_string_limit():
    out = redact_for_log({"note": "x" * 600}, max_string_length=1000)

    assert out["note"] == "x" * 600
