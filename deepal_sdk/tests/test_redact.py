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


def test_long_strings_truncated():
    out = redact_for_log({"note": "x" * 600})

    assert "truncated 100 chars" in out["note"]


def test_safe_headers_keeps_region_only():
    out = safe_headers(
        {
            "selectcountry": "ES",
            "appversion": "V1.12.0",
            "language": "es_ES",
            "authorization": "secret",
        }
    )

    assert out == {"selectcountry": "ES", "appversion": "V1.12.0", "language": "es_ES"}


def test_is_sensitive_key():
    assert is_sensitive_key("X-Tsp-User-Token")
    assert is_sensitive_key("seriralNo")
    assert not is_sensitive_key("soc")


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
