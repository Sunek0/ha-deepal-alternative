"""Unit tests for Deepal Client and models."""

import httpx
import pytest
from deepal import DeepalClient, DeepalRateLimitError
from deepal.models import VehicleCondition, Vehicle


@pytest.mark.asyncio
async def test_client_initialization():
    client = DeepalClient(access_token="test_token_123")
    assert client.access_token == "test_token_123"
    assert "Authorization" in client._get_headers()
    assert client._get_headers()["Authorization"] == "Bearer test_token_123"
    assert client._get_headers()["Version"] == "1.12.0"
    assert "MyChangan/1.12.0" in client._get_headers()["User-Agent"]
    await client.close()


def test_vehicle_model():
    v = Vehicle(car_id="12345", vin="LS5AXXXXX123456", series_name="Deepal S05 Max")
    assert v.car_id == "12345"
    assert v.vin == "LS5AXXXXX123456"
    assert v.series_name == "Deepal S05 Max"


def test_vehicle_condition_parsing():
    raw = {
        "vin": "LS5AXXXXX123456",
        "CdcTotMilg": 12450.5,
        "BatterySoc": 82,
        "RemainingRange": 410,
        "DoorsLocked": True,
        "AcPowerOn": False,
    }

    cond = VehicleCondition(
        car_id="12345",
        vin=raw["vin"],
        total_odometer_km=raw["CdcTotMilg"],
        battery={"soc_percentage": raw["BatterySoc"], "remaining_range_km": raw["RemainingRange"]},
        doors={"locked": raw["DoorsLocked"]},
        climate={"power_on": raw["AcPowerOn"]},
    )

    assert cond.car_id == "12345"
    assert cond.total_odometer_km == 12450.5
    assert cond.battery.soc_percentage == 82
    assert cond.battery.remaining_range_km == 410
    assert cond.doors.locked is True
    assert cond.climate.power_on is False


def test_rate_limit_error_carries_retry_after():
    assert DeepalRateLimitError("limit").retry_after is None
    assert DeepalRateLimitError("limit", retry_after=30).retry_after == 30


@pytest.mark.asyncio
async def test_http_429_is_a_rate_limit_with_retry_after():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "30"}, text="<html>")

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = DeepalClient(access_token="test_token_123", httpx_client=http_client)
    try:
        with pytest.raises(DeepalRateLimitError) as err:
            await client.get_vehicles()
    finally:
        await client.close()
        await http_client.aclose()

    assert err.value.status_code == 429
    assert err.value.retry_after == 30


class _RecordingHttpxClient:
    """HTTP client double capturing the request arguments."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def request(self, **kwargs) -> httpx.Response:
        self.calls.append(kwargs)
        return httpx.Response(200, json={"code": 200, "data": []})


@pytest.mark.asyncio
async def test_requests_pass_the_client_timeout():
    http_client = _RecordingHttpxClient()
    client = DeepalClient(access_token="test_token_123", httpx_client=http_client)
    try:
        await client.get_vehicles()
    finally:
        await client.close()

    assert http_client.calls
    assert http_client.calls[0]["timeout"] == client.timeout
