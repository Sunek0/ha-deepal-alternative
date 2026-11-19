"""Unit tests for Deepal Client and models."""

import inspect
import json
import time
from email.utils import formatdate
from urllib.parse import parse_qs

import httpx
import pytest
from deepal import (
    DeepalAPIError,
    DeepalAuthError,
    DeepalClient,
    DeepalIntlClient,
    DeepalRateLimitError,
)
from deepal.exceptions import parse_retry_after
from deepal.models import VehicleCondition, Vehicle


@pytest.mark.asyncio
async def test_client_initialization():
    client = DeepalClient(access_token="test_token_123")
    assert client.access_token == "test_token_123"
    headers = client._get_headers()
    assert headers["X-VCS-User-Token"] == "test_token_123"
    assert "Authorization" not in headers
    assert "token" not in headers
    assert headers["Version"] == "1.12.0"
    assert "MyChangan/1.12.0" in headers["User-Agent"]
    await client.close()


@pytest.mark.asyncio
async def test_sda_client_timeout_defaults_to_30_seconds():
    client = DeepalClient(access_token="test_token_123")

    assert client.timeout == 30.0
    await client.close()


@pytest.mark.asyncio
async def test_sda_get_vehicles_skips_entries_without_an_id():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": 200,
                "data": [
                    {"carId": "car-1", "vin": "VIN-1"},
                    {"vin": "VIN-2"},
                ],
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = DeepalClient(
        access_token="test_token_123", httpx_client=http_client
    )
    try:
        vehicles = await client.get_vehicles()
    finally:
        await client.close()
        await http_client.aclose()

    assert [vehicle.car_id for vehicle in vehicles] == ["car-1"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"code": 200, "data": None},
        {"code": 200, "data": "oops"},
        {"code": 200, "data": {"unexpected": []}},
        {"code": 200, "data": {"list": None}},
        {"code": 200, "data": [1, "x", None]},
        {"code": 200, "data": [{"vin": "VIN-ONLY"}]},
        {"code": 200},
        [],
    ],
)
async def test_sda_get_vehicles_tolerates_an_unusable_payload(payload):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = DeepalClient(
        access_token="test_token_123", httpx_client=http_client
    )
    try:
        assert await client.get_vehicles() == []
    finally:
        await client.close()
        await http_client.aclose()


@pytest.mark.asyncio
async def test_sda_get_vehicles_normalizes_scalar_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": 200,
                "data": [
                    {
                        "carId": 123,
                        "vin": 456,
                        "series_name": 789,
                        "nickName": 321,
                    }
                ],
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = DeepalClient(
        access_token="test_token_123", httpx_client=http_client
    )
    try:
        vehicles = await client.get_vehicles()
    finally:
        await client.close()
        await http_client.aclose()

    assert len(vehicles) == 1
    assert vehicles[0].car_id == "123"
    assert vehicles[0].vin == "456"
    assert vehicles[0].series_name == "789"
    assert vehicles[0].car_name == "321"


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


def test_parse_retry_after_accepts_an_http_date():
    header = formatdate(time.time() + 90, usegmt=True)

    parsed = parse_retry_after(header)

    assert parsed is not None
    assert 0 < parsed <= 90


def test_parse_retry_after_ignores_a_past_http_date():
    header = formatdate(time.time() - 60, usegmt=True)

    assert parse_retry_after(header) is None


@pytest.mark.asyncio
async def test_http_429_retry_after_accepts_an_http_date():
    header = formatdate(time.time() + 90, usegmt=True)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": header}, text="<html>")

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = DeepalClient(access_token="test_token_123", httpx_client=http_client)
    try:
        with pytest.raises(DeepalRateLimitError) as err:
            await client.get_vehicles()
    finally:
        await client.close()
        await http_client.aclose()

    assert err.value.retry_after is not None
    assert 0 < err.value.retry_after <= 90


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


@pytest.mark.asyncio
async def test_sda_condition_accepts_the_coordinator_vin_argument():
    """The coordinator passes vin= to get_vehicle_condition for every platform."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"code": 200, "data": {"BatterySoc": 82}})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = DeepalClient(access_token="test_token_123", httpx_client=http_client)
    try:
        condition = await client.get_vehicle_condition("car-1", vin="LS5AXXXXX123456")
    finally:
        await client.close()
        await http_client.aclose()

    assert condition.car_id == "car-1"
    assert condition.battery.soc_percentage == 82
    assert seen[0].url.params["carId"] == "car-1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("soc", "range_km", "expected_soc", "expected_range"),
    [
        (255, 410, None, 410),
        (-1, 410, None, 410),
        ("abc", 410, None, 410),
        (None, 410, None, 410),
        (float("inf"), 410, None, 410),
        (float("nan"), 410, None, 410),
        (82, "abc", 82, None),
        (82, None, 82, None),
        (82, float("inf"), 82, None),
        (82, "12.7", 82, 12),
    ],
)
async def test_sda_condition_sanitizes_impossible_readings(
    soc, range_km, expected_soc, expected_range
):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=json.dumps(
                {
                    "code": 200,
                    "data": {
                        "BatterySoc": soc,
                        "RemainingRange": range_km,
                        "ChargingState": 1,
                    },
                }
            ).encode(),
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = DeepalClient(access_token="test_token_123", httpx_client=http_client)
    try:
        condition = await client.get_vehicle_condition("car-1")
    finally:
        await client.close()
        await http_client.aclose()

    assert condition.battery.soc_percentage == expected_soc
    assert condition.battery.remaining_range_km == expected_range
    assert condition.battery.charging_status == "1"


def test_condition_accessors_share_the_coordinator_call_convention():
    """Both clients accept vin; only the international one accepts model_code."""
    sda = inspect.signature(DeepalClient.get_vehicle_condition).parameters
    intl = inspect.signature(DeepalIntlClient.get_vehicle_condition).parameters
    assert "vin" in sda
    assert "vin" in intl
    assert "model_code" not in sda
    assert "model_code" in intl


@pytest.mark.asyncio
async def test_sda_exchange_callback_reports_request_and_response():
    events: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 200, "data": []})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = DeepalClient(
        access_token="test_token_123",
        httpx_client=http_client,
        on_exchange=events.append,
    )
    try:
        await client.get_vehicles()
    finally:
        await client.close()
        await http_client.aclose()

    assert len(events) == 1
    event = events[0]
    assert event["kind"] == "rest"
    assert event["client"] == "sda"
    assert event["method"] == "GET"
    assert event["status"] == 200
    assert event["request"] is None
    assert event["response"] == {"code": 200, "data": []}
    assert "X-VCS-User-Token" in event["headers"]
    assert isinstance(event["duration_ms"], float)


@pytest.mark.asyncio
async def test_sda_exchange_callback_reports_rate_limit_status():
    events: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="slow down")

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = DeepalClient(
        access_token="test_token_123",
        httpx_client=http_client,
        on_exchange=events.append,
    )
    try:
        with pytest.raises(DeepalRateLimitError):
            await client.get_vehicles()
    finally:
        await client.close()
        await http_client.aclose()

    assert events[-1]["status"] == 429
    assert events[-1]["response"] == "slow down"


@pytest.mark.asyncio
async def test_sda_exchange_callback_error_does_not_change_the_result(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 200, "data": []})

    def broken_callback(event: dict) -> None:
        raise RuntimeError("callback boom")

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = DeepalClient(
        access_token="test_token_123",
        httpx_client=http_client,
        on_exchange=broken_callback,
    )
    try:
        vehicles = await client.get_vehicles()
    finally:
        await client.close()
        await http_client.aclose()

    assert vehicles == []
    assert "Deepal exchange callback failed" in caplog.text


@pytest.mark.asyncio
async def test_sda_default_gateway_url_and_headers():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"code": 200, "data": []})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = DeepalClient(access_token="test_token_123", httpx_client=http_client)
    try:
        await client.get_vehicles()
    finally:
        await client.close()
        await http_client.aclose()

    assert (
        str(seen[0].url)
        == "https://m.sda.changan.com.cn/app-apigw/dae-terminal-mobile/api/v1/car/my-cars"
    )
    assert seen[0].headers["X-VCS-User-Token"] == "test_token_123"
    assert "Authorization" not in seen[0].headers
    assert "token" not in seen[0].headers


@pytest.mark.asyncio
async def test_sda_custom_base_url_keeps_the_gateway_prefix():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"code": 200, "data": {}})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = DeepalClient(
        access_token="test_token_123",
        base_url="https://acenter.sda.changan.com.cn/",
        httpx_client=http_client,
    )
    try:
        await client.get_vehicle_condition("car-1")
    finally:
        await client.close()
        await http_client.aclose()

    assert (
        seen[0].url.path
        == "/app-apigw/dae-terminal-mobile/api/v1/car/full-condition"
    )
    assert seen[0].url.host == "acenter.sda.changan.com.cn"
    assert seen[0].url.params["carId"] == "car-1"


@pytest.mark.asyncio
async def test_sda_control_paths_use_the_gateway_prefix():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"code": 200})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = DeepalClient(access_token="test_token_123", httpx_client=http_client)
    try:
        assert await client.set_climate_control("car-1", True, 22.5)
        assert await client.set_door_lock("car-1", True)
    finally:
        await client.close()
        await http_client.aclose()

    assert [request.url.path for request in seen] == [
        "/app-apigw/dae-terminal-mobile/api/v1/control/climate",
        "/app-apigw/dae-terminal-mobile/api/v1/control/lock",
    ]


@pytest.mark.asyncio
async def test_sda_json_requests_keep_the_json_content_type():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"code": 200})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = DeepalClient(access_token="test_token_123", httpx_client=http_client)
    try:
        assert await client.set_climate_control("car-1", True, 22.5)
    finally:
        await client.close()
        await http_client.aclose()

    request = seen[0]
    assert request.headers["Content-Type"] == "application/json;charset=utf-8"
    assert json.loads(request.content) == {
        "carId": "car-1",
        "acPower": 1,
        "targetTemp": 22.5,
    }


@pytest.mark.asyncio
async def test_sda_sms_code_request_is_form_encoded():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"code": 0})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = DeepalClient(httpx_client=http_client)
    try:
        assert await client.request_sms_code("13800000000")
    finally:
        await client.close()
        await http_client.aclose()

    request = seen[0]
    assert request.url.path == "/app-apigw/appauth/sda-app/api/user/login/code"
    assert request.headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert parse_qs(request.content.decode()) == {"phone": ["13800000000"]}
    assert "X-VCS-User-Token" not in request.headers


@pytest.mark.asyncio
async def test_sda_login_bind_is_form_encoded_on_v3():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {"token": "new_token_123", "expires_in": 3600, "user_id": "u-1"},
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = DeepalClient(httpx_client=http_client)
    try:
        token = await client.login_with_code("13800000000", "123456")
    finally:
        await client.close()
        await http_client.aclose()

    request = seen[0]
    assert (
        request.url.path
        == "/app-apigw/appauth/sda-app/api/v3/oauth2-login/token/bind"
    )
    assert request.headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert parse_qs(request.content.decode()) == {
        "phone": ["13800000000"],
        "code": ["123456"],
    }
    assert token.access_token == "new_token_123"
    assert client.access_token == "new_token_123"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected_error"),
    [
        ({"code": 46000, "msg": "token错误或过期"}, DeepalAuthError),
        ({"code": 40005, "msg": "参数【X-VCS-User-Token】不能为空"}, DeepalAuthError),
        ({"code": 40005, "msg": "X_VCS_USER_TOKEN is missing"}, DeepalAuthError),
        ({"code": 40005, "msg": "参数【X-VCS-Timestamp】不能为空"}, DeepalAPIError),
        ({"code": 40001, "msg": "系统繁忙，请稍后重试"}, DeepalAPIError),
        ({"code": "40005", "msg": "缺少参数[phone]"}, DeepalAPIError),
    ],
)
async def test_sda_business_code_mapping(payload, expected_error):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = DeepalClient(access_token="test_token_123", httpx_client=http_client)
    try:
        with pytest.raises(expected_error) as err:
            await client.get_vehicles()
    finally:
        await client.close()
        await http_client.aclose()

    if expected_error is DeepalAPIError:
        assert err.value.code == payload["code"]


@pytest.mark.asyncio
async def test_sda_unauthenticated_business_errors_stay_api_errors():
    """A login call has no session, so a 40005 must not become an auth error."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"code": 40005, "msg": "参数【X-VCS-User-Token】不能为空"}
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = DeepalClient(httpx_client=http_client)
    try:
        with pytest.raises(DeepalAPIError) as err:
            await client.request_sms_code("13800000000")
    finally:
        await client.close()
        await http_client.aclose()

    assert err.value.code == 40005
