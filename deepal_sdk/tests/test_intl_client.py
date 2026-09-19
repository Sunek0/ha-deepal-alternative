"""Unit tests for the international (email login) client."""

import base64
import json
import logging
import time

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from deepal import (
    DeepalAPIError,
    DeepalAuthError,
    DeepalCommandAuthError,
    DeepalCommandNotReady,
    DeepalConnectionError,
    DeepalIntlClient,
    DeepalRateLimitError,
)
from deepal.endpoints import (
    INTL_CA_APP_APIGW_GET_AUTH_TOKEN,
    INTL_CA_GET_CAR_CONF_FUNC,
    INTL_CHECK_CONTROL_CODE,
    INTL_CONDITION_INQUIRY,
    INTL_CONTROL_AIR_CONDITIONER,
    INTL_CONTROL_RESULT,
    INTL_GET_MY_CARS,
    INTL_GET_SECURITY_CODE_STATUS,
    INTL_GET_SERIAL_NO,
    INTL_CHARGE_MODIFY_PLAN,
    INTL_CHARGE_PERCENTAGE,
    INTL_CONTROL_DOORS,
    INTL_CONTROL_FLASHING_HONKING,
    INTL_CONTROL_TRUNK,
    INTL_CONTROL_WINDOWS,
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
    assert captured["headers"]["appversion"] == "V1.12.0"
    assert captured["headers"]["x-os-version"] == "15"
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
    assert captured["body"]["pubKey"].endswith("\n")
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
        captured["tsp"] = request.headers.get("X-Tsp-User-Token")
        captured["vcs"] = request.headers.get("X-VCS-User-Token")
        captured["path"] = request.url.path
        return httpx.Response(200, json={"success": True, "code": "0", "data": []})

    client = _client(handler)
    client.access_token = "test_token_123"
    client.cac_token = "test_cac_123"
    await client.get_vehicles()
    await client.close()

    assert captured["path"] == INTL_GET_MY_CARS
    assert captured["auth"] == "test_token_123|test_cac_123"
    assert captured["tsp"] == "test_token_123"
    assert captured["vcs"] == "test_token_123"


@pytest.mark.asyncio
async def test_tsp_headers_use_access_token_without_cac():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["tsp"] = request.headers.get("X-Tsp-User-Token")
        captured["vcs"] = request.headers.get("X-VCS-User-Token")
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"success": True, "code": "0", "data": []})

    client = _client(handler)
    client.access_token = "test_token_123"
    await client.get_vehicles()
    await client.close()

    assert captured["tsp"] == "test_token_123"
    assert captured["vcs"] == "test_token_123"
    assert captured["auth"] == "test_token_123"


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
            "protocolType": "MQTT",
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
    assert vehicle.protocol_type == "MQTT"


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
    assert condition.climate.power_on is None
    assert condition.climate.steering_wheel_heater_on is False
    assert condition.climate.steering_wheel_heater_level == 0
    assert condition.windows.front_left_open is False
    assert condition.windows.rear_right_open is False
    assert condition.seats.front_left.heating_level == 0
    assert condition.seats.front_right.ventilation_level == 0
    assert condition.tires.front_left.pressure_bar is None
    assert condition.tires.rear_right.alarm is False


@pytest.mark.asyncio
async def test_get_vehicle_condition_maps_extended_telemetry():
    payload = {
        "tire": {
            "leftFront": {"pressure": 240, "temperature": 21},
            "rightFront": {"pressure": 239},
            "leftBack": {"pressure": 245},
            "rightBack": {"pressure": 180, "alarm": 1},
        },
        "window": {"windows": [1, 0, 0, 0]},
        "seat": {
            "leftFront": {"heatStatus": 2, "ventStatus": 1},
            "rightFront": {"heatStatus": 0, "ventStatus": 0},
            "leftBack": {"level": 1},
            "rightBack": {"level": 0},
        },
        "vehicleStatus": {"steeringWheelHeater": 1, "steeringWheelHeaterLevel": 3},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "code": "0", "data": payload})

    client = _client(handler)
    client.access_token = "test_token_123"
    condition = await client.get_vehicle_condition("test-car-1")
    await client.close()

    assert condition.tires.front_left.pressure_bar == 2.4
    assert condition.tires.front_left.temperature_c == 21
    assert condition.tires.front_right.pressure_bar == 2.39
    assert condition.tires.rear_right.pressure_bar == 1.8
    assert condition.tires.rear_right.alarm is True
    assert condition.tires.rear_left.alarm is False
    assert condition.windows.front_left_open is True
    assert condition.windows.front_right_open is False
    assert condition.seats.front_left.heating_level == 2
    assert condition.seats.front_left.ventilation_level == 1
    assert condition.seats.front_right.heating_level == 0
    assert condition.seats.rear_left.heating_level == 1
    assert condition.seats.rear_right.heating_level == 0
    assert condition.climate.steering_wheel_heater_on is True
    assert condition.climate.steering_wheel_heater_level == 3


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


def _login_keypair() -> tuple[str, object]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    return private_pem, key.public_key()


def _encrypted_serial(public_key, serial: str) -> str:
    return base64.b64encode(public_key.encrypt(serial.encode(), padding.PKCS1v15())).decode()


def test_sign_payload_sorts_keys_and_omits_requested_ones():
    client = _client(lambda request: httpx.Response(200, json={}))
    client.private_key_pem, public_key = _login_keypair()

    signature = client.sign_payload(
        {"b": 1, "a": True, "sign": "old", "command": "air"},
        omit_keys={"command"},
    )

    public_key.verify(
        base64.b64decode(signature),
        b"a=true&b=1",
        padding.PKCS1v15(),
        hashes.SHA256(),
    )


def test_sign_payload_without_private_key_raises():
    client = _client(lambda request: httpx.Response(200, json={}))
    with pytest.raises(DeepalAuthError):
        client.sign_payload({"a": 1})


@pytest.mark.asyncio
async def test_control_air_conditioner_signs_and_returns_command_id():
    captured = {}
    private_pem, public_key = _login_keypair()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == INTL_GET_SERIAL_NO:
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "code": "0",
                    "data": _encrypted_serial(public_key, "SN123"),
                },
            )
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"success": True, "code": "0", "data": {"commandId": "cmd-1"}}
        )

    client = _client(handler)
    client.access_token = "test_token_123"
    client.private_key_pem = private_pem
    command_id = await client.control_air_conditioner("car-1", True, 22.0)
    await client.close()

    assert command_id == "cmd-1"
    assert captured["path"] == INTL_CONTROL_AIR_CONDITIONER
    body = captured["body"]
    assert body["command"] == "air"
    assert body["enabled"] is True
    assert body["targetTemp"] == 220
    assert body["runTime"] == 30
    assert body["windMode"] == 1
    assert body["seriralNo"] == "SN123"
    assert body["vehicleId"] == "car-1"
    assert body["rcToken"] == ""

    public_key.verify(
        base64.b64decode(body["sign"]),
        (
            "enabled=true&runTime=30&seriralNo=SN123&targetTemp=220"
            "&vehicleId=car-1&windMode=1"
        ).encode(),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )


@pytest.mark.asyncio
async def test_control_air_conditioner_without_private_key_raises():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"success": True, "code": "0", "data": {}})

    client = _client(handler)
    client.access_token = "test_token_123"
    with pytest.raises(DeepalAuthError):
        await client.control_air_conditioner("car-1", True, 21.0)
    await client.close()

    assert calls == []


@pytest.mark.asyncio
async def test_control_air_conditioner_without_command_id_raises():
    private_pem, public_key = _login_keypair()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == INTL_GET_SERIAL_NO:
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "code": "0",
                    "data": _encrypted_serial(public_key, "SN123"),
                },
            )
        return httpx.Response(200, json={"success": True, "code": "0", "data": {}})

    client = _client(handler)
    client.access_token = "test_token_123"
    client.private_key_pem = private_pem
    with pytest.raises(DeepalAPIError):
        await client.control_air_conditioner("car-1", True, 21.0)
    await client.close()


@pytest.mark.asyncio
async def test_check_control_code_returns_and_caches_rc_token():
    captured = {"paths": []}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["paths"].append(request.url.path)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"success": True, "code": "0", "data": {"rcToken": "test_rc_123"}},
        )

    client = _client(handler)
    client.access_token = "test_token_123"
    token = await client.check_control_code("1234")
    await client.close()

    assert captured["paths"] == [INTL_GET_SECURITY_CODE_STATUS, INTL_CHECK_CONTROL_CODE]
    assert "1234" not in captured["body"]["safeCode"]
    assert token == "test_rc_123"
    assert client.rc_token == "test_rc_123"


@pytest.mark.asyncio
async def test_signed_command_requires_control_pin_for_token():
    private_pem, public_key = _login_keypair()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == INTL_GET_SERIAL_NO:
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "code": "0",
                    "data": _encrypted_serial(public_key, "SN123"),
                },
            )
        raise AssertionError("command must not be sent without a control PIN")

    client = _client(handler)
    client.access_token = "test_token_123"
    client.private_key_pem = private_pem
    with pytest.raises(DeepalAuthError):
        await client._signed_command(
            "/intl-app-gw/intl-app-car-control/api/control/doors",
            "car-1",
            {"command": "lock"},
            require_rc_token=True,
        )
    await client.close()


@pytest.mark.asyncio
async def test_control_condition_inquiry_sends_signed_command():
    captured = {}
    private_pem, public_key = _login_keypair()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == INTL_GET_SERIAL_NO:
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "code": "0",
                    "data": _encrypted_serial(public_key, "SN123"),
                },
            )
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"success": True, "code": "0", "data": {"commandId": "cmd-inq"}}
        )

    client = _client(handler)
    client.access_token = "test_token_123"
    client.private_key_pem = private_pem
    command_id = await client.control_condition_inquiry("car-1")
    await client.close()

    assert command_id == "cmd-inq"
    assert captured["path"] == INTL_CONDITION_INQUIRY
    assert captured["body"]["command"] == "COMMAND_GET_NEW_CONDITION"
    assert captured["body"]["vehicleId"] == "car-1"
    assert captured["body"]["sign"]


@pytest.mark.asyncio
async def test_control_result_returns_payload():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "success": True,
                "code": "0",
                "data": {"resultCode": 0, "errorMsg": ""},
            },
        )

    client = _client(handler)
    client.access_token = "test_token_123"
    result = await client.control_result("car-1", "cmd-1")
    await client.close()

    assert captured["path"] == INTL_CONTROL_RESULT
    assert captured["body"] == {"vehicleId": "car-1", "commandId": "cmd-1"}
    assert result["resultCode"] == 0


@pytest.mark.asyncio
async def test_control_result_without_data_returns_empty_dict():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "code": "0"})

    client = _client(handler)
    client.access_token = "test_token_123"
    result = await client.control_result("car-1", "cmd-1")
    await client.close()

    assert result == {}


@pytest.mark.asyncio
async def test_get_mqtt_config_and_token_use_ca_gateway():
    captured = {"urls": []}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["urls"].append(str(request.url))
        if request.url.path.endswith("/device/getConnConf"):
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "code": "0",
                    "data": {"mqttConnectionInfos": []},
                },
            )
        return httpx.Response(
            200, json={"success": True, "code": "0", "data": {"authToken": "tsp-token"}}
        )

    client = _client(handler)
    client.access_token = "test_token_123"
    client.user_id = "test-user-1"
    config = await client.get_mqtt_config("car-1")
    token = await client.get_mqtt_token()
    await client.close()

    assert config == {"mqttConnectionInfos": []}
    assert token == "tsp-token"
    assert all("ca-m.iov.changanauto.com.de" in url for url in captured["urls"])


@pytest.mark.asyncio
async def test_get_mqtt_token_without_user_id_raises():
    client = _client(lambda request: httpx.Response(200, json={}))
    client.access_token = "test_token_123"
    with pytest.raises(DeepalAPIError):
        await client.get_mqtt_token()
    await client.close()


@pytest.mark.asyncio
async def test_ca_gateway_error_exposes_code():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": False,
                "code": "APIGW_1_7_02_001",
                "msg": "X-Tsp-User-Token is empty",
            },
        )

    client = _client(handler)
    client.access_token = "test_token_123"
    with pytest.raises(DeepalAPIError) as err:
        await client.get_mqtt_config("car-1")
    await client.close()

    assert err.value.code == "APIGW_1_7_02_001"


@pytest.mark.asyncio
async def test_s05_mqtt_condition_uses_normalized_params():
    async def fake_config(vehicle_id: str) -> dict:
        return {}

    async def fake_token() -> str:
        return "tsp-token"

    async def fake_params(config: dict, token: str) -> dict:
        return {
            "soc": 71,
            "remainedPowerMile": 320,
            "totalOdometer": 12000,
            "driverDoor": 0,
            "passengerDoor": 0,
            "leftRearDoor": 0,
            "rightRearDoor": 0,
            "trunk": 0,
            "driverDoorLock": 0,
            "passengerDoorLock": 0,
            "diverWindow": 0,
            "passengerWindow": 0,
            "leftRearWindow": 0,
            "rightRearWindow": 0,
            "lfTyrePressure": 240,
            "rfTyrePressure": 241,
            "lrTyrePressure": 242,
            "rrTyrePressure": 243,
        }

    client = _client(lambda request: httpx.Response(200, json={}))
    client.access_token = "test_token_123"
    client.user_id = "test-user-1"
    client.get_mqtt_config = fake_config
    client.get_mqtt_token = fake_token
    client._read_s05_params = fake_params
    condition = await client.s05_mqtt_condition("car-1")
    await client.close()

    assert condition.car_id == "car-1"
    assert condition.battery.soc_percentage == 71
    assert condition.battery.remaining_range_km == 320
    assert condition.total_odometer_km == 12000
    assert condition.doors.locked is True
    assert condition.tires.front_left.pressure_bar == 2.4


def test_sign_payload_uses_mime_base64():
    client = _client(lambda request: httpx.Response(200, json={}))
    client.private_key_pem, public_key = _login_keypair()

    signature = client.sign_payload({"a": 1})

    assert "\n" in signature
    public_key.verify(
        base64.b64decode(signature),
        b"a=1",
        padding.PKCS1v15(),
        hashes.SHA256(),
    )


@pytest.mark.asyncio
async def test_serial_no_signing_rejected_raises_auth_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": False,
                "code": "COMMON_1_1_01_001",
                "msg": "sign verify failed",
            },
        )

    client = _client(handler)
    client.access_token = "test_token_123"
    client.private_key_pem, _ = _login_keypair()
    with pytest.raises(DeepalAuthError):
        await client.get_serial_data()
    await client.close()


def _stale_rc_token_handler(counts: dict):
    private_pem, public_key = _login_keypair()

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == INTL_GET_SERIAL_NO:
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "code": "0",
                    "data": _encrypted_serial(public_key, "SN123"),
                },
            )
        if path == INTL_GET_SECURITY_CODE_STATUS:
            counts["status"] = counts.get("status", 0) + 1
            return httpx.Response(200, json={"success": True, "code": "0", "data": {}})
        if path == INTL_CHECK_CONTROL_CODE:
            counts["check"] = counts.get("check", 0) + 1
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "code": "0",
                    "data": {"rcToken": "fresh-token"},
                },
            )
        counts["command"] = counts.get("command", 0) + 1
        if counts["command"] == 1:
            return httpx.Response(
                200,
                json={
                    "success": False,
                    "code": "COMMON_1_1_04_001",
                    "msg": "rcToken expired",
                },
            )
        return httpx.Response(
            200, json={"success": True, "code": "0", "data": {"commandId": "cmd-1"}}
        )

    return private_pem, handler


@pytest.mark.asyncio
async def test_stale_rc_token_is_re_exchanged_and_retried():
    counts: dict = {}
    private_pem, handler = _stale_rc_token_handler(counts)
    client = _client(handler)
    client.access_token = "test_token_123"
    client.private_key_pem = private_pem
    client.rc_token = "stale-token"
    client.control_pin = "1234"

    command_id = await client._signed_command(
        "/intl-app-gw/intl-app-car-control/api/control/doors",
        "car-1",
        {"command": "lock", "open": True},
        require_rc_token=True,
        sign_omit_keys={"command", "rcToken"},
    )
    await client.close()

    assert command_id == "cmd-1"
    assert counts["command"] == 2
    assert counts["check"] == 1
    assert counts["status"] == 1
    assert client.rc_token == "fresh-token"


@pytest.mark.asyncio
async def test_stale_rc_token_without_pin_propagates():
    counts: dict = {}
    private_pem, handler = _stale_rc_token_handler(counts)
    client = _client(handler)
    client.access_token = "test_token_123"
    client.private_key_pem = private_pem
    client.rc_token = "stale-token"

    with pytest.raises(DeepalAPIError):
        await client._signed_command(
            "/intl-app-gw/intl-app-car-control/api/control/doors",
            "car-1",
            {"command": "lock", "open": True},
            require_rc_token=True,
            sign_omit_keys={"command", "rcToken"},
        )
    await client.close()

    assert counts["command"] == 1
    assert "check" not in counts


@pytest.mark.asyncio
async def test_rate_limit_error_mapped():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"success": False, "code": "CAC_1_1_01_033", "msg": "too many requests"},
        )

    client = _client(handler)
    with pytest.raises(DeepalRateLimitError):
        await client.request_email_code(EMAIL)
    await client.close()


@pytest.mark.asyncio
async def test_serial_decrypt_mismatch_raises_command_auth_error():
    client = _client(lambda request: httpx.Response(200, json={}))
    _, other_public_key = _login_keypair()
    client.private_key_pem, _ = _login_keypair()
    serial = _encrypted_serial(other_public_key, "SN123")

    with pytest.raises(DeepalCommandAuthError):
        client.decrypt_serial_no(serial)
    await client.close()


@pytest.mark.asyncio
async def test_command_prerequisites_raise_command_not_ready():
    client = _client(lambda request: httpx.Response(200, json={}))

    with pytest.raises(DeepalCommandNotReady):
        await client._signed_command(
            "/intl-app-gw/intl-app-car-control/api/control/doors",
            "car-1",
            {"command": "lock"},
        )

    client.private_key_pem, _ = _login_keypair()
    with pytest.raises(DeepalCommandNotReady):
        await client._signed_command(
            "/intl-app-gw/intl-app-car-control/api/control/doors",
            "car-1",
            {"command": "lock"},
            require_rc_token=True,
        )
    await client.close()


@pytest.mark.asyncio
async def test_get_vehicle_condition_maps_extended_status_groups():
    payload = {
        "vehicleStatus": {
            "soc": 70,
            "drvMileage": 300,
            "totalMileage": 1000,
            "speed": 42.5,
            "gearSignal": "D",
            "epbSts": 0,
            "powerStatus": 2,
            "status": 1,
            "engineSts": 1,
            "connectStatus": 1,
        },
        "hvac": {
            "insideTemp": 215,
            "outsideTemp": 180,
            "insideHumidity": 44.5,
            "insidePm25": 12,
            "insideAirQualityLevel": 3,
            "defrostStatus": 1,
            "fanLevel": 4,
        },
        "charge": {
            "dcChargeGunConnectStatus": 0,
            "acChargeCurrent": 16.2,
            "dcChargeCurrent": 0,
            "chargeCurrent": 16.2,
            "remainChargeTime": 95,
            "maxSocPercent": 80,
            "chargePlanList": [
                {"startSwitch": 1, "endSwitch": 1, "startTime": "2300", "endTime": "0700"}
            ],
        },
        "door": {
            "doors": [0, 0, 0, 0],
            "trunk": 0,
            "hood": 0,
            "driverLock": 0,
            "passengerLock": 1,
        },
        "lamp": {
            "highBeam": 1,
            "lowBeam": 0,
            "positionLamp": 1,
            "frontFoglamp": 0,
            "rearFoglamp": 0,
            "leftTurn": 0,
            "rightTurn": 1,
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "code": "0", "data": payload})

    client = _client(handler)
    client.access_token = "test_token_123"
    condition = await client.get_vehicle_condition("car-1")
    await client.close()

    assert condition.speed_kmh == 42.5
    assert condition.gear == "D"
    assert condition.epb_status == 0
    assert condition.power_status == 2
    assert condition.vehicle_status == 1
    assert condition.engine_on is True
    assert condition.connected is True
    assert condition.climate.inside_temperature_c == 21.5
    assert condition.climate.outside_temperature_c == 18.0
    assert condition.climate.humidity == 44.5
    assert condition.climate.inside_pm25 == 12
    assert condition.climate.air_quality_level == 3
    assert condition.climate.defrost_on is True
    assert condition.climate.fan_level == 4
    assert condition.battery.dc_gun_connected is True
    assert condition.battery.ac_charge_current_a == 16.2
    assert condition.battery.charge_current_a == 16.2
    assert condition.battery.remaining_charge_time_min == 95
    assert condition.battery.charge_limit_percent == 80
    assert condition.battery.charge_schedule_enabled is True
    assert condition.battery.charge_schedule_start == "2300"
    assert condition.battery.charge_schedule_end == "0700"
    assert condition.doors.driver_locked is True
    assert condition.doors.passenger_locked is False
    assert condition.lamps.high_beam is True
    assert condition.lamps.position_lamp is True
    assert condition.lamps.right_turn is True
    assert condition.lamps.low_beam is False


def _command_handler(public_key, captured: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == INTL_GET_SERIAL_NO:
            captured.setdefault("serial_bodies", []).append(
                json.loads(request.content)
            )
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "code": "0",
                    "data": _encrypted_serial(public_key, "SN123"),
                },
            )
        if path == INTL_GET_SECURITY_CODE_STATUS:
            captured["status_calls"] = captured.get("status_calls", 0) + 1
            return httpx.Response(200, json={"success": True, "code": "0", "data": {}})
        if path == INTL_CHECK_CONTROL_CODE:
            captured["check_calls"] = captured.get("check_calls", 0) + 1
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "code": "0",
                    "data": {"rcToken": "rc-1"},
                },
            )
        captured["path"] = path
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"success": True, "code": "0", "data": {"commandId": "cmd-1"}}
        )

    return handler


def _verify_signature(body: dict, canonical: str, public_key) -> None:
    public_key.verify(
        base64.b64decode(body["sign"]),
        canonical.encode(),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )


@pytest.mark.asyncio
async def test_control_doors_payload_requires_rc_token():
    private_pem, public_key = _login_keypair()
    captured: dict = {}
    client = _client(_command_handler(public_key, captured))
    client.access_token = "test_token_123"
    client.private_key_pem = private_pem
    client.control_pin = "1234"

    command_id = await client.control_doors("car-1", True)
    await client.close()

    assert command_id == "cmd-1"
    assert captured["path"] == INTL_CONTROL_DOORS
    body = captured["body"]
    assert body["open"] is True
    assert body["rcToken"] == "rc-1"
    assert body["seriralNo"] == "SN123"
    _verify_signature(
        body,
        "open=true&rcToken=rc-1&seriralNo=SN123&vehicleId=car-1",
        public_key,
    )


@pytest.mark.asyncio
async def test_control_windows_payload_omits_command():
    private_pem, public_key = _login_keypair()
    captured: dict = {}
    client = _client(_command_handler(public_key, captured))
    client.access_token = "test_token_123"
    client.private_key_pem = private_pem
    client.rc_token = "rc-1"

    await client.control_windows("car-1", False)
    await client.close()

    assert captured["path"] == INTL_CONTROL_WINDOWS
    body = captured["body"]
    assert body["command"] == "window"
    assert body["open"] is False
    assert body["openType"] == 10
    _verify_signature(
        body,
        "open=false&openType=10&rcToken=rc-1&seriralNo=SN123&vehicleId=car-1",
        public_key,
    )


@pytest.mark.asyncio
async def test_control_trunk_payload_omits_command():
    private_pem, public_key = _login_keypair()
    captured: dict = {}
    client = _client(_command_handler(public_key, captured))
    client.access_token = "test_token_123"
    client.private_key_pem = private_pem
    client.rc_token = "rc-1"

    await client.control_trunk("car-1", True)
    await client.close()

    assert captured["path"] == INTL_CONTROL_TRUNK
    body = captured["body"]
    assert body["command"] == "trunk"
    assert body["open"] is True
    _verify_signature(
        body,
        "open=true&rcToken=rc-1&seriralNo=SN123&vehicleId=car-1",
        public_key,
    )


@pytest.mark.asyncio
async def test_control_charge_limit_uses_serial_type_2():
    private_pem, public_key = _login_keypair()
    captured: dict = {}
    client = _client(_command_handler(public_key, captured))
    client.access_token = "test_token_123"
    client.private_key_pem = private_pem

    await client.control_charge_limit("car-1", 80)
    await client.close()

    assert captured["serial_bodies"] == [{"type": "2"}]
    assert captured["path"] == INTL_CHARGE_PERCENTAGE
    body = captured["body"]
    assert body["chargePercentageMax"] == 80
    assert body["command"] == "charge_max"
    assert body["rcToken"] == ""
    _verify_signature(
        body,
        "chargePercentageMax=80&seriralNo=SN123&vehicleId=car-1",
        public_key,
    )


@pytest.mark.asyncio
async def test_control_charge_schedule_payload_uses_serial_type_2():
    private_pem, public_key = _login_keypair()
    captured: dict = {}
    client = _client(_command_handler(public_key, captured))
    client.access_token = "test_token_123"
    client.private_key_pem = private_pem

    await client.control_charge_schedule(
        "car-1", "p1", "2300", "0700", True
    )
    await client.close()

    assert captured["serial_bodies"] == [{"type": "2"}]
    assert captured["path"] == INTL_CHARGE_MODIFY_PLAN
    body = captured["body"]
    assert body["command"] == "modify-plan"
    assert body["planId"] == "p1"
    assert body["startTime"] == "2300"
    assert body["endTime"] == "0700"
    assert body["endSwitch"] == 1
    assert body["timeZone"] == "GMT+08:00"
    _verify_signature(
        body,
        (
            "endSwitch=1&endTime=0700&planId=p1&planType=1&seriralNo=SN123"
            "&startTime=2300&timeFormat=1&timeZone=GMT+08:00&vehicleId=car-1"
        ),
        public_key,
    )


@pytest.mark.asyncio
async def test_control_flashing_honking_does_not_require_rc_token():
    private_pem, public_key = _login_keypair()
    captured: dict = {}
    client = _client(_command_handler(public_key, captured))
    client.access_token = "test_token_123"
    client.private_key_pem = private_pem

    await client.control_flashing_honking("car-1", 3)
    await client.close()

    assert "check_calls" not in captured
    assert captured["path"] == INTL_CONTROL_FLASHING_HONKING
    body = captured["body"]
    assert body["command"] == "flash_bee"
    assert body["type"] == 3
    assert body["rcToken"] == ""
    _verify_signature(
        body,
        "seriralNo=SN123&type=3&vehicleId=car-1",
        public_key,
    )


@pytest.mark.asyncio
async def test_api_error_message_includes_gateway_code():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": False,
                "code": "HW_1_1_01_001",
                "msg": "Operation failed",
            },
        )

    client = _client(handler)
    client.access_token = "test_token_123"
    with pytest.raises(DeepalAPIError) as err:
        await client.get_vehicles()
    await client.close()

    assert "HW_1_1_01_001" in str(err.value)
    assert err.value.code == "HW_1_1_01_001"


@pytest.mark.asyncio
async def test_condition_without_ac_status_reports_unknown_power():
    payload = {"hvac": {"remoteTemp": 250, "insideTemp": 270}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "code": "0", "data": payload})

    client = _client(handler)
    client.access_token = "test_token_123"
    condition = await client.get_vehicle_condition("car-1")
    await client.close()

    assert condition.climate.power_on is None
    assert condition.climate.target_temperature_c == 25.0
    assert condition.climate.inside_temperature_c == 27.0


@pytest.mark.asyncio
async def test_negative_seat_levels_are_normalized():
    payload = {
        "seat": {
            "leftFront": {"heatStatus": -1, "ventStatus": -1},
            "rightFront": {"heatStatus": 0, "ventStatus": 1},
            "leftBack": {"level": -1},
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "code": "0", "data": payload})

    client = _client(handler)
    client.access_token = "test_token_123"
    condition = await client.get_vehicle_condition("car-1")
    await client.close()

    assert condition.seats.front_left.heating_level == 0
    assert condition.seats.front_left.ventilation_level == 0
    assert condition.seats.rear_left.heating_level == 0
    assert condition.seats.front_right.ventilation_level == 1


def _jwt_with_exp(exp: int) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"HS512"}').rstrip(b"=").decode()
    payload = (
        base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode())
        .rstrip(b"=")
        .decode()
    )
    return f"{header}.{payload}.signature"


@pytest.mark.asyncio
async def test_access_token_expiry_parsed_and_checked():
    client = _client(lambda request: httpx.Response(200, json={}))
    expires = int(time.time()) + 3600

    assert client._jwt_expiry("not-a-jwt") is None
    assert client._jwt_expiry(_jwt_with_exp(expires)) == expires

    client.access_token_expires_at = expires
    assert client.access_token_expires_soon(300) is False

    client.access_token_expires_at = int(time.time()) + 60
    assert client.access_token_expires_soon(300) is True

    client.access_token_expires_at = None
    assert client.access_token_expires_soon(300) is False
    await client.close()


@pytest.mark.asyncio
async def test_login_stores_access_token_expiry():
    expires = int(time.time()) + 3600

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": True,
                "code": "0",
                "data": {"token": _jwt_with_exp(expires), "refreshToken": "r"},
            },
        )

    client = _client(handler)
    await client.login_with_email_code(EMAIL, CODE)
    await client.close()

    assert client.access_token_expires_at == expires


@pytest.mark.asyncio
async def test_diagnostic_os_version_header_override():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["xos"] = request.headers.get("x-os-version")
        return httpx.Response(200, json={"success": True, "code": "0", "data": []})

    transport = httpx.MockTransport(handler)
    client = DeepalIntlClient(
        country="ES",
        device_id="test-device-id",
        os_version="9",
        httpx_client=httpx.AsyncClient(transport=transport),
    )
    client.access_token = "test_token_123"
    await client.get_vehicles()
    await client.close()

    assert captured["xos"] == "9"


@pytest.mark.asyncio
async def test_refresh_logs_when_cac_token_not_renewed(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"success": True, "code": "0", "data": {"token": "new_token"}},
        )

    client = _client(handler)
    client.access_token = "old_token"
    client.refresh_token = "old_refresh"

    with caplog.at_level(logging.WARNING, logger="deepal_sdk"):
        await client.refresh_tokens()
    await client.close()

    assert "did not return a new CAC token" in caplog.text


@pytest.mark.asyncio
async def test_refresh_logs_when_cac_token_renewed(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": True,
                "code": "0",
                "data": {"token": "new_token", "cacToken": "new_cac"},
            },
        )

    client = _client(handler)
    client.access_token = "old_token"
    client.refresh_token = "old_refresh"

    with caplog.at_level(logging.INFO, logger="deepal_sdk"):
        await client.refresh_tokens()
    await client.close()

    assert "returned a new CAC token" in caplog.text
    assert "new_cac" not in caplog.text


@pytest.mark.asyncio
async def test_tsp_token_source_override():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["tsp"] = request.headers.get("X-Tsp-User-Token")
        captured["vcs"] = request.headers.get("X-VCS-User-Token")
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"success": True, "code": "0", "data": []})

    transport = httpx.MockTransport(handler)
    client = DeepalIntlClient(
        country="ES",
        device_id="test-device-id",
        tsp_token_source="cac_user_id",
        httpx_client=httpx.AsyncClient(transport=transport),
    )
    client.access_token = "test_token_123"
    client.cac_token = "cac_value"
    client.cac_user_id = "cac_user_value"
    await client.get_vehicles()
    await client.close()

    assert captured["tsp"] == "cac_user_value"
    assert captured["vcs"] == "cac_user_value"
    assert captured["auth"] == "test_token_123|cac_value"


@pytest.mark.asyncio
async def test_login_logs_session_fields_without_values(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": True,
                "code": "0",
                "data": {
                    "token": "SECRET_TOKEN",
                    "refreshToken": "SECRET_REFRESH",
                    "cacToken": "SECRET_CAC",
                    "caUserId": "SECRET_CA_USER",
                    "cacUserId": "SECRET_CAC_USER",
                    "userId": "SECRET_USER",
                },
            },
        )

    client = _client(handler)
    with caplog.at_level(logging.INFO, logger="deepal_sdk"):
        await client.login_with_email_code(EMAIL, CODE)
    await client.close()

    assert "cacToken=True" in caplog.text
    assert "caUserId=True" in caplog.text
    assert "cacUserId=True" in caplog.text
    assert "SECRET_CAC" not in caplog.text
    assert "SECRET_CA_USER" not in caplog.text


@pytest.mark.asyncio
async def test_environment_selects_regional_gateways():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = request.url
        captured["appid"] = request.headers.get("appid")
        return httpx.Response(200, json={"success": True, "code": "0", "data": []})

    transport = httpx.MockTransport(handler)
    client = DeepalIntlClient(
        country="TH",
        environment="release_ase",
        device_id="test-device-id",
        httpx_client=httpx.AsyncClient(transport=transport),
    )
    client.access_token = "test_token_123"

    assert client.ca_base_url == "https://ca-m.iov.changanauto.sg"
    await client.get_vehicles()
    await client.close()

    assert captured["url"].host == "m.iov.changanauto.sg"
    assert captured["url"].path == "/appgw/intl-app-user/api/car/vehicles"
    assert captured["appid"] == "ca"


@pytest.mark.asyncio
async def test_asean_connect_environment_uses_changan_app_id():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["appid"] = request.headers.get("appid")
        return httpx.Response(200, json={"success": True, "code": "0", "data": []})

    transport = httpx.MockTransport(handler)
    client = DeepalIntlClient(
        environment="release_ase_connect",
        device_id="test-device-id",
        httpx_client=httpx.AsyncClient(transport=transport),
    )
    client.access_token = "test_token_123"
    await client.get_vehicles()
    await client.close()

    assert captured["appid"] == "changan"


def test_unknown_environment_raises():
    with pytest.raises(ValueError):
        DeepalIntlClient(environment="does_not_exist")


@pytest.mark.asyncio
async def test_timestamp_headers_are_opt_in():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["tsp"] = request.headers.get("X-Tsp-Timestamp")
        captured["vcs"] = request.headers.get("X-VCS-Timestamp")
        return httpx.Response(200, json={"success": True, "code": "0", "data": []})

    client = _client(handler)
    client.access_token = "test_token_123"
    await client.get_vehicles()
    await client.close()
    assert captured["tsp"] is None
    assert captured["vcs"] is None

    transport = httpx.MockTransport(handler)
    client = DeepalIntlClient(
        country="GB",
        device_id="test-device-id",
        send_timestamps=True,
        httpx_client=httpx.AsyncClient(transport=transport),
    )
    client.access_token = "test_token_123"
    await client.get_vehicles()
    await client.close()

    assert captured["tsp"] is not None and captured["tsp"].isdigit()
    assert captured["tsp"] == captured["vcs"]


@pytest.mark.asyncio
async def test_get_mqtt_config_falls_back_to_app_endpoint():
    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("getConnConf"):
            return httpx.Response(
                200,
                json={
                    "success": False,
                    "code": "APIGW_-1_7_01_004",
                    "msg": "invalided token",
                },
            )
        return httpx.Response(
            200,
            json={
                "success": True,
                "code": "0",
                "data": {"mqttConnectionInfos": []},
            },
        )

    client = _client(handler)
    client.access_token = "test_token_123"
    data = await client.get_mqtt_config("car-1")
    await client.close()

    assert data == {"mqttConnectionInfos": []}
    assert paths[0].endswith("getConnConf")
    assert paths[1] == INTL_CA_GET_CAR_CONF_FUNC


@pytest.mark.asyncio
async def test_mqtt_config_fallback_can_be_disabled():
    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(
            200,
            json={"success": False, "code": "APIGW_-1_7_01_004", "msg": "nope"},
        )

    transport = httpx.MockTransport(handler)
    client = DeepalIntlClient(
        country="GB",
        device_id="test-device-id",
        mqtt_config_fallback=False,
        httpx_client=httpx.AsyncClient(transport=transport),
    )
    client.access_token = "test_token_123"

    with pytest.raises(DeepalAPIError):
        await client.get_mqtt_config("car-1")
    await client.close()
    assert len(paths) == 1


@pytest.mark.asyncio
async def test_get_mqtt_token_falls_back_to_app_apigw():
    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.startswith("/user-apigw/vot-connect-auth-center"):
            return httpx.Response(
                200,
                json={"success": False, "code": "APIGW_-1_7_01_004", "msg": "nope"},
            )
        return httpx.Response(
            200, json={"success": True, "code": "0", "data": {"authToken": "tok-123"}}
        )

    client = _client(handler)
    client.access_token = "test_token_123"
    client.user_id = "user-1"

    token = await client.get_mqtt_token()
    await client.close()

    assert token == "tok-123"
    assert paths[1] == INTL_CA_APP_APIGW_GET_AUTH_TOKEN


@pytest.mark.asyncio
async def test_mqtt_fallbacks_skip_rate_limit():
    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(
            200,
            json={"success": False, "code": "CAC_1_1_01_033", "msg": "slow down"},
        )

    client = _client(handler)
    client.access_token = "test_token_123"

    with pytest.raises(DeepalRateLimitError):
        await client.get_mqtt_config("car-1")
    await client.close()
    assert len(paths) == 1


@pytest.mark.asyncio
async def test_mqtt_fallbacks_skip_auth_errors():
    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(
            200,
            json={"success": False, "code": "AUTH_1_1_01_001", "msg": "auth"},
        )

    client = _client(handler)
    client.access_token = "test_token_123"
    client.user_id = "user-1"

    with pytest.raises(DeepalAuthError):
        await client.get_mqtt_token()
    await client.close()
    assert len(paths) == 1


@pytest.mark.asyncio
async def test_tsp_headers_default_to_access_token():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["tsp"] = request.headers.get("X-Tsp-User-Token")
        captured["vcs"] = request.headers.get("X-VCS-User-Token")
        return httpx.Response(200, json={"success": True, "code": "0", "data": []})

    client = _client(handler)
    client.access_token = "test_token_123"
    client.cac_token = "test_cac_123"
    await client.get_vehicles()
    await client.close()

    assert captured["tsp"] == "test_token_123"
    assert captured["vcs"] == "test_token_123"


@pytest.mark.asyncio
async def test_tsp_headers_can_be_forced_to_cac_token():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["tsp"] = request.headers.get("X-Tsp-User-Token")
        return httpx.Response(200, json={"success": True, "code": "0", "data": []})

    transport = httpx.MockTransport(handler)
    client = DeepalIntlClient(
        country="ES",
        device_id="test-device-id",
        tsp_token_source="cac",
        httpx_client=httpx.AsyncClient(transport=transport),
    )
    client.access_token = "test_token_123"
    client.cac_token = "test_cac_123"
    await client.get_vehicles()
    await client.close()

    assert captured["tsp"] == "test_cac_123"
