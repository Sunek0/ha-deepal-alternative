"""Unit tests for the international (email login) client."""

import json

import httpx
import pytest

from deepal import (
    DeepalAPIError,
    DeepalAuthError,
    DeepalConnectionError,
    DeepalIntlClient,
)
from deepal.endpoints import (
    INTL_GET_MY_CARS,
    INTL_GET_VEHICLE_CONDITION,
    INTL_LOGIN_BY_EMAIL_CODE,
    INTL_REFRESH_TOKEN,
    INTL_SEND_EMAIL_CODE,
    INTL_SEND_SMS_CODE,
)

EMAIL = "test.user@example.com"
CODE = "123456"


def _client(handler) -> DeepalIntlClient:
    transport = httpx.MockTransport(handler)
    return DeepalIntlClient(
        country="GB",
        language="en_GB",
        device_id="test-device-id",
        httpx_client=httpx.AsyncClient(transport=transport),
    )


@pytest.mark.asyncio
async def test_request_email_code_encrypts_email_and_sends_app_headers():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = request.url
        captured["method"] = request.method
        captured["headers"] = request.headers
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"success": True, "code": "0", "data": {}})

    client = _client(handler)
    await client.request_email_code(EMAIL)
    await client.close()

    assert captured["method"] == "POST"
    assert captured["url"].path == INTL_SEND_EMAIL_CODE
    assert captured["headers"]["appid"] == "ca"
    assert captured["headers"]["selectcountry"] == "GB"
    assert captured["headers"]["deviceid"] == "test-device-id"
    assert captured["body"]["type"] == "0"
    assert EMAIL not in captured["body"]["email"]


@pytest.mark.asyncio
async def test_login_with_email_code_returns_tokens():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "success": True,
                "code": "0",
                "data": {
                    "token": "test_token_123",
                    "refreshToken": "test_refresh_123",
                    "cacToken": "test_cac_123",
                    "userId": "test-user-1",
                },
            },
        )

    client = _client(handler)
    token = await client.login_with_email_code(EMAIL, CODE)
    await client.close()

    assert captured["body"]["authCode"] == CODE
    assert captured["body"]["salesCountry"] == "GB"
    assert captured["body"]["pubKey"]
    assert EMAIL not in captured["body"]["email"]
    assert token.access_token == "test_token_123"
    assert token.refresh_token == "test_refresh_123"
    assert token.user_id == "test-user-1"
    assert client.access_token == "test_token_123"
    assert client.cac_token == "test_cac_123"
    assert client.private_key_pem
    assert client.public_key


@pytest.mark.asyncio
async def test_login_uses_provided_pub_key_and_sales_country():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"success": True, "code": "0", "data": {"token": "test_token_123"}}
        )

    client = _client(handler)
    await client.login_with_email_code(EMAIL, CODE, sales_country="PT", pub_key="test_pub_key")
    await client.close()

    assert captured["body"]["pubKey"] == "test_pub_key"
    assert captured["body"]["salesCountry"] == "PT"
    assert client.private_key_pem is None


@pytest.mark.asyncio
async def test_invalid_code_raises_api_error_without_tokens():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"success": False, "code": "APP_1_1_07_002", "msg": "invalid code"},
        )

    client = _client(handler)
    with pytest.raises(DeepalAPIError) as err:
        await client.login_with_email_code(EMAIL, CODE)
    await client.close()

    assert err.value.code == "APP_1_1_07_002"
    assert client.access_token is None


@pytest.mark.asyncio
async def test_http_401_raises_auth_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"success": False, "code": "401"})

    client = _client(handler)
    with pytest.raises(DeepalAuthError):
        await client.request_email_code(EMAIL)
    await client.close()


@pytest.mark.asyncio
async def test_transport_error_raises_connection_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = _client(handler)
    with pytest.raises(DeepalConnectionError):
        await client.request_email_code(EMAIL)
    await client.close()


@pytest.mark.asyncio
async def test_request_sms_code_encrypts_mobile_and_sends_country_code():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = request.url
        captured["headers"] = request.headers
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"success": True, "code": "0", "data": {}})

    client = _client(handler)
    await client.request_sms_code("600000000", "34")
    await client.close()

    assert captured["url"].path == INTL_SEND_SMS_CODE
    assert captured["headers"]["selectcountry"] == "GB"
    assert captured["body"]["countryCode"] == "34"
    assert "600000000" not in captured["body"]["mobile"]
    assert "authorization" not in captured["headers"]


@pytest.mark.asyncio
async def test_login_with_sms_code_returns_tokens():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "success": True,
                "code": "0",
                "data": {"token": "test_token_456", "refreshToken": "test_refresh_456"},
            },
        )

    client = _client(handler)
    token = await client.login_with_sms_code("600000000", CODE, "34")
    await client.close()

    assert captured["body"]["authCode"] == CODE
    assert captured["body"]["countryCode"] == "34"
    assert "600000000" not in captured["body"]["mobile"]
    assert captured["body"]["salesCountry"] == "GB"
    assert captured["body"]["pubKey"]
    assert token.access_token == "test_token_456"
    assert token.refresh_token == "test_refresh_456"


@pytest.mark.asyncio
async def test_sms_invalid_code_raises_api_error_without_tokens():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"success": False, "code": "APP_1_1_07_002", "msg": "invalid code"},
        )

    client = _client(handler)
    with pytest.raises(DeepalAPIError) as err:
        await client.login_with_sms_code("600000000", CODE, "34")
    await client.close()

    assert err.value.code == "APP_1_1_07_002"
    assert client.access_token is None


@pytest.mark.asyncio
async def test_sms_login_reuses_generated_keypair():
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(
            200, json={"success": True, "code": "0", "data": {"token": "test_token_789"}}
        )

    client = _client(handler)
    await client.login_with_sms_code("600000000", CODE, "34")
    private_key_pem = client.private_key_pem
    await client.login_with_sms_code("600000000", CODE, "34")
    await client.close()

    assert captured[1]["pubKey"] == captured[0]["pubKey"]
    assert client.private_key_pem == private_key_pem


@pytest.mark.asyncio
async def test_sms_transport_error_raises_connection_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = _client(handler)
    with pytest.raises(DeepalConnectionError):
        await client.request_sms_code("600000000", "34")
    await client.close()


@pytest.mark.asyncio
async def test_sms_invalid_inputs_raise_value_error_without_request():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"success": True, "code": "0", "data": {}})

    client = _client(handler)
    with pytest.raises(ValueError):
        await client.request_sms_code("600000000", "")
    with pytest.raises(ValueError):
        await client.request_sms_code("600000000", "abc")
    with pytest.raises(ValueError):
        await client.request_sms_code("", "34")
    with pytest.raises(ValueError):
        await client.request_sms_code("+34600000000", "34")
    with pytest.raises(ValueError):
        await client.login_with_sms_code("+34600000000", CODE, "34")
    await client.close()

    assert calls == []


@pytest.mark.asyncio
async def test_sms_dial_code_with_plus_is_normalized():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"success": True, "code": "0", "data": {}})

    client = _client(handler)
    await client.request_sms_code("600000000", "+34")
    await client.close()

    assert captured["body"]["countryCode"] == "34"


@pytest.mark.asyncio
async def test_authorization_includes_cac_token():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        captured["path"] = request.url.path
        return httpx.Response(200, json={"success": True, "code": "0", "data": []})

    client = _client(handler)
    client.access_token = "test_token_123"
    client.cac_token = "test_cac_123"
    await client.get_vehicles()
    await client.close()

    assert captured["path"] == INTL_GET_MY_CARS
    assert captured["auth"] == "test_token_123|test_cac_123"


@pytest.mark.asyncio
async def test_get_vehicles_maps_international_fields():
    payload = [
        {
            "carId": "test-car-1",
            "vin": "LS5AXXXXX123456",
            "seriesName": "Deepal S07",
            "nickName": "Mi coche",
            "licensePlate": "1234ABC",
            "imgUrl": "https://img.example/test.png",
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content) == {}
        return httpx.Response(200, json={"success": True, "code": "0", "data": payload})

    client = _client(handler)
    client.access_token = "test_token_123"
    vehicles = await client.get_vehicles()
    await client.close()

    assert len(vehicles) == 1
    vehicle = vehicles[0]
    assert vehicle.car_id == "test-car-1"
    assert vehicle.vin == "LS5AXXXXX123456"
    assert vehicle.series_name == "Deepal S07"
    assert vehicle.car_name == "Mi coche"
    assert vehicle.license_plate == "1234ABC"
    assert vehicle.thumbnail_url == "https://img.example/test.png"


@pytest.mark.asyncio
async def test_get_vehicle_condition_maps_international_payload():
    captured = {}
    payload = {
        "vin": "LS5AXXXXX123456",
        "lastUpdatedAt": 1700000000000,
        "vehicleStatus": {"soc": 82, "drvMileage": 410, "totalMileage": 12450},
        "door": {
            "doors": [1, 0, 0, 1],
            "trunk": 1,
            "driverLock": 0,
        },
        "hvac": {"acStatus": 1, "remoteTemp": 225},
        "charge": {"chargeStatus": 2, "chargeConStatus": 3},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"success": True, "code": "0", "data": payload})

    client = _client(handler)
    client.access_token = "test_token_123"
    condition = await client.get_vehicle_condition("test-car-1")
    await client.close()

    assert captured["path"] == INTL_GET_VEHICLE_CONDITION
    assert captured["body"]["vehicleId"] == "test-car-1"
    assert captured["body"]["vechileCriteria"]["door"] == "1"
    assert condition.car_id == "test-car-1"
    assert condition.vin == "LS5AXXXXX123456"
    assert condition.total_odometer_km == 12450
    assert condition.battery.soc_percentage == 82
    assert condition.battery.remaining_range_km == 410
    assert condition.battery.charging_status == "2"
    assert condition.battery.charger_connected is True
    assert condition.doors.locked is True
    assert condition.doors.driver_door_open is True
    assert condition.doors.passenger_door_open is False
    assert condition.doors.rear_left_door_open is False
    assert condition.doors.rear_right_door_open is True
    assert condition.doors.trunk_open is True
    assert condition.climate.power_on is True
    assert condition.climate.target_temperature_c == 22.5
    assert condition.last_updated_timestamp == 1700000000
    assert condition.raw_data == payload


@pytest.mark.asyncio
async def test_get_vehicle_condition_defaults_for_missing_groups():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "code": "0", "data": {}})

    client = _client(handler)
    client.access_token = "test_token_123"
    condition = await client.get_vehicle_condition("test-car-1")
    await client.close()

    assert condition.battery.soc_percentage is None
    assert condition.doors.locked is True
    assert condition.doors.driver_door_open is False
    assert condition.climate.power_on is False


@pytest.mark.asyncio
async def test_refresh_tokens_updates_session():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "success": True,
                "code": "0",
                "data": {
                    "token": "test_token_new",
                    "refreshToken": "test_refresh_new",
                    "cacToken": "test_cac_new",
                },
            },
        )

    client = _client(handler)
    client.access_token = "test_token_old"
    client.refresh_token = "test_refresh_old"
    token = await client.refresh_tokens()
    await client.close()

    assert captured["path"] == INTL_REFRESH_TOKEN
    assert captured["body"]["refreshToken"] == "test_refresh_old"
    assert token.access_token == "test_token_new"
    assert token.refresh_token == "test_refresh_new"
    assert token.cac_token == "test_cac_new"
    assert client.cac_token == "test_cac_new"


@pytest.mark.asyncio
async def test_refresh_tokens_without_refresh_token_raises():
    client = _client(lambda request: httpx.Response(200, json={}))
    with pytest.raises(DeepalAuthError):
        await client.refresh_tokens()
    await client.close()
