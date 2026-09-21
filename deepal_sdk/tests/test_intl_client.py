"""Unit tests for the international (email login) client."""

import asyncio
import base64
import json
import logging
import ssl
import time
from typing import Any, Optional

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from deepal import (
    CommandResultStatus,
    DeepalAPIError,
    DeepalAuthError,
    DeepalCommandAuthError,
    DeepalCommandNotReady,
    DeepalConnectionError,
    DeepalIntlClient,
    DeepalRateLimitError,
    FLASH_HONK_BEE,
    FLASH_HONK_FLASH,
    FLASH_HONK_FLASH_BEE,
    FLASH_HONK_OFF,
)
from deepal.mqtt import aes_cbc_encrypt, build_publish_packet, parse_publish
from deepal.intl import (
    CAR_CONTROL_REFRESH_THROTTLE_SECONDS,
    INTL_REFRESH_THROTTLE_SECONDS,
)
from deepal.endpoints import (
    INTL_CA_APP_APIGW_GET_AUTH_TOKEN,
    INTL_CA_GET_CAR_CONF_FUNC,
    INTL_CHARGE_ADD_PLAN,
    INTL_CHARGE_DELETE_PLAN,
    INTL_CHARGE_VALIDITY,
    INTL_CHECK_CONTROL_CODE,
    INTL_CONDITION_INQUIRY,
    INTL_CONTROL_AIR_CONDITIONER,
    INTL_CONTROL_DEFROST,
    INTL_CONTROL_FOTA_PLAN,
    INTL_CONTROL_RESULT,
    INTL_CONTROL_SEATS_HEAT,
    INTL_CONTROL_SEATS_WIND,
    INTL_CONTROL_STEERING_WHEEL_HEAT,
    INTL_DEPARTURE_ADD_PLAN,
    INTL_DEPARTURE_DELETE,
    INTL_DEPARTURE_ENABLED,
    INTL_DEPARTURE_MODIFY_PLAN,
    INTL_DEPARTURE_VALIDITY,
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
    INTL_LOGIN_BY_EMAIL_PASSWORD,
    INTL_LOGIN_BY_MOBILE_PASSWORD,
    INTL_LOGOUT,
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


def _split_mqtt_packet(data: bytes) -> tuple[int, bytes]:
    first = data[0]
    multiplier = 1
    remaining = 0
    pos = 1
    while True:
        byte = data[pos]
        pos += 1
        remaining += (byte & 0x7F) * multiplier
        if not byte & 0x80:
            break
        multiplier *= 128
    return first, data[pos : pos + remaining]


class _FakeMqttBroker:
    """In-process MQTT 5.0 broker for the one-shot S05 exchange."""

    def __init__(
        self,
        params: dict[str, Any],
        *,
        secret_key: str = "secret-key-12345",
        reply_condition_after_pings: int = 0,
        connack_reason_code: int = 0,
    ) -> None:
        self.reader = asyncio.StreamReader()
        self.writes: list[bytes] = []
        self.close_count = 0
        self.writes_before_close: Optional[int] = None
        self.connect_packet: Optional[bytes] = None
        self.subscribe_packet: Optional[bytes] = None
        self.login_topic: Optional[str] = None
        self.login_payload: Optional[dict[str, Any]] = None
        self.condition_topic: Optional[str] = None
        self.condition_payload: Optional[dict[str, Any]] = None
        self.pings = 0
        self.params = params
        self.secret_key = secret_key
        self.reply_condition_after_pings = reply_condition_after_pings
        self.connack_reason_code = connack_reason_code
        self._condition_sent = False

    def write(self, data: bytes) -> None:
        self.writes.append(data)
        first, body = _split_mqtt_packet(data)
        if first == 0x10:
            self.connect_packet = data
            self.reader.feed_data(
                bytes([0x20, 0x03, 0x00, self.connack_reason_code & 0xFF, 0x00])
            )
        elif first == 0x82:
            self.subscribe_packet = data
            self.reader.feed_data(b"\x90\x05\x00\x01\x00\x00\x00")
        elif first == 0x30:
            self._on_publish(first, body)
        elif first == 0xC0:
            self.pings += 1
            if (
                not self._condition_sent
                and self.condition_payload is not None
                and self.pings >= self.reply_condition_after_pings
            ):
                self._feed_condition_response()

    def _on_publish(self, first: int, body: bytes) -> None:
        topic, payload, _packet_id = parse_publish(first, body)
        if "loginout" in topic:
            self.login_topic = topic
            self.login_payload = payload
            self.reader.feed_data(
                build_publish_packet(
                    "$vdp/login-did/server/loginout",
                    {
                        "r": payload["r"],
                        "rs": [{"params": {"secretKey": self.secret_key}}],
                    },
                )
            )
            return
        self.condition_topic = topic
        self.condition_payload = payload
        if self.reply_condition_after_pings == 0:
            self._feed_condition_response()

    def _feed_condition_response(self) -> None:
        payload = self.condition_payload
        if payload is None:
            return
        self._condition_sent = True
        req_id = payload["r"]
        encrypted = aes_cbc_encrypt(
            [{"service_code": "car_condition", "params": self.params}],
            self.secret_key,
            req_id,
        )
        self.reader.feed_data(
            build_publish_packet(
                "$vdp/device-did/properties/get/res",
                {"r": req_id, "rs": encrypted},
            )
        )

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        self.writes_before_close = len(self.writes)
        self.close_count += 1

    async def wait_closed(self) -> None:
        pass


def _install_fake_broker(monkeypatch, broker: _FakeMqttBroker) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    async def fake_open_connection(host, port, *, ssl=None, server_hostname=None):
        captured["host"] = host
        captured["port"] = port
        captured["ssl"] = ssl
        captured["server_hostname"] = server_hostname
        return broker.reader, broker

    monkeypatch.setattr(asyncio, "open_connection", fake_open_connection)
    return captured


S05_BROKER_PARAMS: dict[str, Any] = {
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
    "lfTyrePressure": 240,
}


def _mqtt_config(**overrides: Any) -> dict[str, Any]:
    info: dict[str, Any] = {
        "clusterInfos": [{"brokerUrl": "ssl://broker.example", "brokerPort": 8883}],
        "topicInfos": [
            {
                "msgType": "loginout",
                "pubTopics": ["$vdp/login-did/client/loginout"],
                "subTopics": ["$vdp/login-did/server/loginout"],
            },
            {
                "msgType": "properties",
                "pubTopics": ["$vdp/device-did/properties/get/req"],
                "subTopics": ["$vdp/device-did/properties/get/res"],
            },
            {
                "msgType": "event",
                "subTopics": ["$vdp/device-did/device-did/server/event"],
            },
            {
                "msgType": "command",
                "subTopics": ["$vdp/device-did/device-did/client/action"],
            },
        ],
        "vin": "VIN-PLACEHOLDER-1",
        "carId": "car-1",
    }
    info.update(overrides)
    return {"mqttConnectionInfos": [info]}


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
    assert captured["headers"]["x-os-version"] == "9"
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


def test_public_key_body_from_private_matches_generate_login_keypair():
    private_pem, pub_body = DeepalIntlClient.generate_login_keypair()

    derived = DeepalIntlClient.public_key_body_from_private(private_pem)

    assert derived == pub_body


def test_set_login_keypair_derives_public_key_when_missing():
    private_pem, pub_body = DeepalIntlClient.generate_login_keypair()
    client = _client(lambda request: httpx.Response(200, json={}))

    resolved = client.set_login_keypair(private_pem)

    assert resolved == pub_body
    assert client.private_key_pem == private_pem
    assert client.public_key == pub_body


def test_set_login_keypair_keeps_provided_public_key():
    private_pem, _ = DeepalIntlClient.generate_login_keypair()
    client = _client(lambda request: httpx.Response(200, json={}))

    resolved = client.set_login_keypair(private_pem, public_key="test_pub_key")

    assert resolved == "test_pub_key"
    assert client.public_key == "test_pub_key"


@pytest.mark.asyncio
async def test_constructor_restores_keypair_and_device_id():
    private_pem, pub_body = DeepalIntlClient.generate_login_keypair()
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        captured["deviceid"] = request.headers.get("deviceid")
        return httpx.Response(
            200, json={"success": True, "code": "0", "data": {"token": "test_token_123"}}
        )

    transport = httpx.MockTransport(handler)
    client = DeepalIntlClient(
        country="GB",
        device_id="test-device-id",
        private_key_pem=private_pem,
        public_key=pub_body,
        httpx_client=httpx.AsyncClient(transport=transport),
    )
    await client.login_with_email_code(EMAIL, CODE)
    await client.close()

    assert captured["deviceid"] == "test-device-id"
    assert captured["body"]["pubKey"] == pub_body
    assert client.device_id == "test-device-id"
    assert client.private_key_pem == private_pem
    assert client.public_key == pub_body


def test_constructor_generates_device_id_only_when_absent():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    client = DeepalIntlClient(
        country="GB", httpx_client=httpx.AsyncClient(transport=transport)
    )

    assert len(client.device_id) == 32
    assert client.device_id == client.device_id.lower()
    assert all(char in "0123456789abcdef" for char in client.device_id)
    assert client.private_key_pem is None
    assert client.public_key is None


def test_ensure_pub_key_reuses_stored_pair():
    private_pem, pub_body = DeepalIntlClient.generate_login_keypair()
    client = _client(lambda request: httpx.Response(200, json={}))
    client.private_key_pem = private_pem
    client.public_key = pub_body

    assert client._ensure_pub_key() == pub_body
    assert client.private_key_pem == private_pem
    assert client.public_key == pub_body


def test_ensure_pub_key_derives_public_from_private_only():
    private_pem, pub_body = DeepalIntlClient.generate_login_keypair()
    client = _client(lambda request: httpx.Response(200, json={}))
    client.private_key_pem = private_pem

    assert client._ensure_pub_key() == pub_body
    assert client.private_key_pem == private_pem
    assert client.public_key == pub_body


def test_ensure_pub_key_generates_only_when_absent():
    client = _client(lambda request: httpx.Response(200, json={}))

    resolved = client._ensure_pub_key()

    assert client.public_key == resolved
    assert client.private_key_pem
    assert DeepalIntlClient.public_key_body_from_private(
        client.private_key_pem
    ) == resolved


def test_ensure_pub_key_caller_key_does_not_replace_stored_material():
    private_pem, pub_body = DeepalIntlClient.generate_login_keypair()
    client = _client(lambda request: httpx.Response(200, json={}))
    client.private_key_pem = private_pem
    client.public_key = pub_body

    assert client._ensure_pub_key("caller_key") == "caller_key"
    assert client.private_key_pem == private_pem
    assert client.public_key == pub_body


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
async def test_login_with_email_password_encrypts_body_and_stores_tokens():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "success": True,
                "code": "0",
                "data": {"token": "test_token_123", "refreshToken": "test_refresh_123"},
            },
        )

    client = _client(handler)
    token = await client.login_with_email_password(EMAIL, "secret-password")
    await client.close()

    assert captured["path"] == INTL_LOGIN_BY_EMAIL_PASSWORD
    assert captured["body"]["salesCountry"] == "GB"
    assert captured["body"]["pubKey"]
    assert EMAIL not in captured["body"]["email"]
    assert "secret-password" not in captured["body"]["password"]
    assert token.access_token == "test_token_123"
    assert client.access_token == "test_token_123"


@pytest.mark.asyncio
async def test_login_with_email_password_rejection_raises_auth_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"success": False, "code": "APP_1_1_02_003", "msg": "bad password"},
        )

    client = _client(handler)
    with pytest.raises(DeepalAuthError):
        await client.login_with_email_password(EMAIL, "wrong-password")
    await client.close()

    assert client.access_token is None


@pytest.mark.asyncio
async def test_login_with_password_sends_mobile_payload():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"success": True, "code": "0", "data": {"token": "test_token_456"}},
        )

    client = _client(handler)
    token = await client.login_with_password("600000000", "secret-password", "+34")
    await client.close()

    assert captured["path"] == INTL_LOGIN_BY_MOBILE_PASSWORD
    assert captured["body"]["countryCode"] == "34"
    assert "600000000" not in captured["body"]["mobile"]
    assert "secret-password" not in captured["body"]["password"]
    assert captured["body"]["salesCountry"] == "GB"
    assert captured["body"]["pubKey"]
    assert token.access_token == "test_token_456"


@pytest.mark.asyncio
async def test_login_with_password_invalid_input_makes_no_request():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"success": True, "code": "0", "data": {}})

    client = _client(handler)
    with pytest.raises(ValueError):
        await client.login_with_password("+34600000000", "secret-password", "34")
    with pytest.raises(ValueError):
        await client.login_with_password("600000000", "secret-password", "")
    await client.close()

    assert calls == []


@pytest.mark.asyncio
async def test_logout_posts_with_session_and_clears_tokens():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["auth"] = request.headers.get("authorization")
        captured["tsp"] = request.headers.get("X-Tsp-User-Token")
        return httpx.Response(200, json={"success": True, "code": "0", "data": {}})

    client = _client(handler)
    client.access_token = "test_token_123"
    client.refresh_token = "test_refresh_123"
    client.cac_token = "test_cac_123"
    client.rc_token = "test_rc_123"
    client.access_token_expires_at = 1700000000
    await client.logout()
    await client.close()

    assert captured["path"] == INTL_LOGOUT
    assert captured["auth"] == "test_token_123|test_cac_123"
    assert captured["tsp"] == "test_token_123"
    assert client.access_token is None
    assert client.refresh_token is None
    assert client.cac_token is None
    assert client.rc_token is None
    assert client.access_token_expires_at is None


@pytest.mark.asyncio
async def test_logout_without_session_makes_no_request():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"success": True, "code": "0", "data": {}})

    client = _client(handler)
    await client.logout()
    await client.close()

    assert calls == []
    assert client.access_token is None


@pytest.mark.asyncio
async def test_logout_clears_tokens_when_remote_fails():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = _client(handler)
    client.access_token = "test_token_123"
    client.refresh_token = "test_refresh_123"
    client.cac_token = "test_cac_123"
    client.rc_token = "test_rc_123"
    await client.logout()
    await client.close()

    assert client.access_token is None
    assert client.refresh_token is None
    assert client.cac_token is None
    assert client.rc_token is None


@pytest.mark.asyncio
async def test_logout_clears_tokens_when_gateway_rejects():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"success": False, "code": "APP_1_1_02_007", "msg": "nope"},
        )

    client = _client(handler)
    client.access_token = "test_token_123"
    client.refresh_token = "test_refresh_123"
    client.cac_token = "test_cac_123"
    client.rc_token = "test_rc_123"
    await client.logout()
    await client.close()

    assert client.access_token is None
    assert client.refresh_token is None
    assert client.cac_token is None
    assert client.rc_token is None


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
        "lastUpdatedAt": "2023-11-14T22:13:20Z",
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
    condition = await client.get_vehicle_condition(
        "test-car-1", vin="LS5AXXXXX123456"
    )
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
async def test_get_vehicle_condition_uses_vehicle_status_timestamp_fallback():
    payload = {"vehicleStatus": {"lastUpdatedAt": 1700000000000}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "code": "0", "data": payload})

    client = _client(handler)
    client.access_token = "test_token_123"
    condition = await client.get_vehicle_condition("test-car-1")
    await client.close()

    assert condition.last_updated_timestamp == 1700000000


@pytest.mark.asyncio
async def test_get_vehicle_condition_accepts_epoch_seconds_timestamp():
    payload = {"lastUpdatedAt": 1700000000}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "code": "0", "data": payload})

    client = _client(handler)
    client.access_token = "test_token_123"
    condition = await client.get_vehicle_condition("test-car-1")
    await client.close()

    assert condition.last_updated_timestamp == 1700000000


@pytest.mark.asyncio
async def test_get_vehicle_condition_without_raw_vin_uses_parameter():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "code": "0", "data": {}})

    client = _client(handler)
    client.access_token = "test_token_123"
    condition = await client.get_vehicle_condition(
        "test-car-1", vin="LS5AXXXXX123456"
    )
    await client.close()

    assert condition.vin == "LS5AXXXXX123456"


@pytest.mark.asyncio
async def test_get_vehicle_condition_maps_mqtt_mileage_fields():
    payload = {
        "vehicleStatus": {
            "totalMeterYesterday": 42.5,
            "igniteCumulativeMileage": 12.25,
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "code": "0", "data": payload})

    client = _client(handler)
    client.access_token = "test_token_123"
    condition = await client.get_vehicle_condition("test-car-1")
    await client.close()

    assert condition.mileage_yesterday_km == 42.5
    assert condition.trip_mileage_km == 12.25


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
    assert condition.mileage_yesterday_km is None
    assert condition.trip_mileage_km is None


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


def test_refresh_throttle_constants_match_app():
    assert INTL_REFRESH_THROTTLE_SECONDS == 1800.0
    assert CAR_CONTROL_REFRESH_THROTTLE_SECONDS == 3300.0


def _refresh_request_counter(counter: dict, token: str = "test_token_new"):
    def handler(request: httpx.Request) -> httpx.Response:
        counter["requests"] = counter.get("requests", 0) + 1
        return httpx.Response(
            200,
            json={
                "success": True,
                "code": "0",
                "data": {"token": token, "refreshToken": "test_refresh_new"},
            },
        )

    return handler


@pytest.mark.asyncio
async def test_refresh_reactive_attempts_are_throttled_inside_window():
    counter: dict = {}
    client = _client(_refresh_request_counter(counter))
    client.access_token = "test_token_old"
    client.refresh_token = "test_refresh_old"

    first = await client.refresh_tokens()
    second = await client.refresh_tokens()
    await client.close()

    assert counter["requests"] == 1
    assert first.access_token == "test_token_new"
    assert second.access_token == "test_token_new"
    assert second.refresh_token == "test_refresh_new"


@pytest.mark.asyncio
async def test_refresh_throttle_window_elapsing_allows_next_attempt():
    counter: dict = {}
    client = _client(_refresh_request_counter(counter))
    client.access_token = "test_token_old"
    client.refresh_token = "test_refresh_old"

    await client.refresh_tokens()
    assert counter["requests"] == 1

    client._last_refresh_attempt_at -= INTL_REFRESH_THROTTLE_SECONDS + 1
    await client.refresh_tokens()
    await client.close()

    assert counter["requests"] == 2


@pytest.mark.asyncio
async def test_refresh_throttle_is_per_client():
    counter_a: dict = {}
    counter_b: dict = {}
    client_a = _client(_refresh_request_counter(counter_a))
    client_b = _client(_refresh_request_counter(counter_b))
    for client in (client_a, client_b):
        client.access_token = "test_token_old"
        client.refresh_token = "test_refresh_old"

    await client_a.refresh_tokens()
    await client_a.refresh_tokens()
    await client_b.refresh_tokens()
    await client_a.close()
    await client_b.close()

    assert counter_a["requests"] == 1
    assert counter_b["requests"] == 1


@pytest.mark.asyncio
async def test_refresh_proactive_bypasses_throttle_near_expiry():
    counter: dict = {}
    client = _client(_refresh_request_counter(counter))
    client.refresh_token = "test_refresh_old"
    expires = int(time.time()) + 60
    client.access_token = _jwt_with_exp(expires)
    client.access_token_expires_at = expires
    client._last_refresh_attempt_at = time.monotonic()

    token = await client.refresh_tokens()
    await client.close()

    assert counter["requests"] == 1
    assert token.access_token == "test_token_new"


@pytest.mark.asyncio
async def test_refresh_opaque_token_stays_throttled():
    counter: dict = {}
    client = _client(_refresh_request_counter(counter))
    client.access_token = "test_token_old"
    client.refresh_token = "test_refresh_old"
    client._last_refresh_attempt_at = time.monotonic()

    token = await client.refresh_tokens()
    await client.close()

    assert counter.get("requests", 0) == 0
    assert token.access_token == "test_token_old"


@pytest.mark.asyncio
async def test_refresh_single_flight_shares_result():
    counter: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        counter["requests"] = counter.get("requests", 0) + 1
        await asyncio.sleep(0)
        return httpx.Response(
            200,
            json={
                "success": True,
                "code": "0",
                "data": {"token": "test_token_new", "refreshToken": "test_refresh_new"},
            },
        )

    client = _client(handler)
    client.access_token = "test_token_old"
    client.refresh_token = "test_refresh_old"

    first, second = await asyncio.gather(
        client.refresh_tokens(), client.refresh_tokens()
    )
    await client.close()

    assert counter["requests"] == 1
    assert first.access_token == "test_token_new"
    assert second.access_token == "test_token_new"


@pytest.mark.asyncio
async def test_refresh_single_flight_shares_failure():
    counter: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        counter["requests"] = counter.get("requests", 0) + 1
        await asyncio.sleep(0)
        raise httpx.ConnectError("boom", request=request)

    client = _client(handler)
    client.access_token = "test_token_old"
    client.refresh_token = "test_refresh_old"

    results = await asyncio.gather(
        client.refresh_tokens(), client.refresh_tokens(), return_exceptions=True
    )
    await client.close()

    assert counter["requests"] == 1
    assert len(results) == 2
    assert all(isinstance(result, DeepalConnectionError) for result in results)


@pytest.mark.asyncio
async def test_refresh_keeps_previous_user_id_when_response_omits_it():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"success": True, "code": "0", "data": {"token": "test_token_new"}},
        )

    client = _client(handler)
    client.access_token = "test_token_old"
    client.refresh_token = "test_refresh_old"
    client.user_id = "test-user-1"

    token = await client.refresh_tokens()
    await client.close()

    assert client.user_id == "test-user-1"
    assert token.user_id == "test-user-1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code",
    ["APP_1_1_02_003", "APP_1_1_02_006", "CAC_1_1_01_045", "46000", 46000],
)
async def test_kick_out_codes_raise_auth_error(code):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"success": False, "code": code, "msg": "session kicked out"},
        )

    client = _client(handler)
    with pytest.raises(DeepalAuthError):
        await client.request_email_code(EMAIL)
    await client.close()


@pytest.mark.asyncio
async def test_unrelated_gateway_code_stays_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"success": False, "code": "APP_1_1_02_007", "msg": "other failure"},
        )

    client = _client(handler)
    with pytest.raises(DeepalAPIError) as err:
        await client.request_email_code(EMAIL)
    await client.close()

    assert not isinstance(err.value, DeepalAuthError)
    assert err.value.code == "APP_1_1_02_007"


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
    assert "rcToken" not in body

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


def test_mqtt_constructor_defaults_and_overrides():
    client = _client(lambda request: httpx.Response(200, json={}))
    assert client.mqtt_client_id is None
    assert client.mqtt_username is None
    assert client.mqtt_keepalive == 60
    assert client.mqtt_clean_start is True
    assert client.mqtt_tls_insecure is False

    overridden = DeepalIntlClient(
        country="GB",
        language="en_GB",
        device_id="test-device-id",
        mqtt_client_id="client-1",
        mqtt_username="user-1",
        mqtt_keepalive=30,
        mqtt_clean_start=False,
        mqtt_tls_insecure=True,
    )
    assert overridden.mqtt_client_id == "client-1"
    assert overridden.mqtt_username == "user-1"
    assert overridden.mqtt_keepalive == 30
    assert overridden.mqtt_clean_start is False
    assert overridden.mqtt_tls_insecure is True


@pytest.mark.asyncio
async def test_read_s05_params_runs_mqtt5_exchange(monkeypatch):
    broker = _FakeMqttBroker(S05_BROKER_PARAMS)
    captured = _install_fake_broker(monkeypatch, broker)
    client = _client(lambda request: httpx.Response(200, json={}))
    client.user_id = "test-user-1"

    params = await client._read_s05_params(_mqtt_config(), "test-mqtt-token")
    await client.close()

    assert params["soc"] == 71
    assert captured["host"] == "broker.example"
    assert captured["port"] == 8883
    assert captured["server_hostname"] == "broker.example"
    assert captured["ssl"].verify_mode == ssl.CERT_REQUIRED
    assert captured["ssl"].check_hostname is True

    assert broker.connect_packet is not None
    assert broker.connect_packet[8] == 5
    assert b"login-did" in broker.connect_packet

    assert broker.subscribe_packet is not None
    assert b"$vdp/login-did/server/loginout" in broker.subscribe_packet
    assert b"$vdp/device-did/properties/get/res" in broker.subscribe_packet
    assert b"client/action" not in broker.subscribe_packet

    assert broker.login_topic == "$vdp/login-did/client/loginout"
    assert broker.login_payload is not None
    assert "a" not in broker.login_payload and "pl" not in broker.login_payload
    assert broker.login_payload["b"] == {
        "vin": "VIN-PLACEHOLDER-1",
        "uid": "test-user-1",
        "cid": "car-1",
        "ruid": "login-did",
    }

    assert broker.condition_topic == "$vdp/device-did/properties/get/req"
    assert broker.condition_payload is not None
    assert "a" not in broker.condition_payload
    assert "pl" not in broker.condition_payload
    assert broker.condition_payload["b"] == {
        "vin": "VIN-PLACEHOLDER-1",
        "uid": "test-user-1",
        "cid": "car-1",
        "ruid": "login-did",
    }

    assert broker.writes[-1] == b"\xe0\x02\x00\x00"
    assert broker.writes_before_close == len(broker.writes)
    assert broker.close_count == 1


@pytest.mark.asyncio
async def test_read_s05_params_rejects_connack_reason_code(monkeypatch):
    broker = _FakeMqttBroker(S05_BROKER_PARAMS, connack_reason_code=0x86)
    _install_fake_broker(monkeypatch, broker)
    client = _client(lambda request: httpx.Response(200, json={}))
    client.user_id = "test-user-1"

    with pytest.raises(DeepalAPIError) as err:
        await client._read_s05_params(_mqtt_config(), "test-mqtt-token")
    await client.close()

    assert "134" in str(err.value)
    assert "bad user name or password" in str(err.value)
    assert broker.close_count == 1


@pytest.mark.asyncio
async def test_read_s05_params_sends_pingreq_when_keepalive_elapses(monkeypatch):
    broker = _FakeMqttBroker(S05_BROKER_PARAMS, reply_condition_after_pings=2)
    _install_fake_broker(monkeypatch, broker)
    client = _client(lambda request: httpx.Response(200, json={}))
    client.user_id = "test-user-1"
    client.mqtt_keepalive = 0.01

    params = await client._read_s05_params(_mqtt_config(), "test-mqtt-token")
    await client.close()

    assert params["soc"] == 71
    assert broker.pings >= 2
    assert broker.writes[-1] == b"\xe0\x02\x00\x00"
    assert broker.writes_before_close == len(broker.writes)
    assert broker.close_count == 1


@pytest.mark.asyncio
async def test_read_s05_params_resolves_template_topics(monkeypatch):
    config = {
        "mqttConnectionInfos": [
            {
                "clusterInfos": [{"brokerUrl": "ssl://broker.example:8883"}],
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
    broker = _FakeMqttBroker(S05_BROKER_PARAMS)
    _install_fake_broker(monkeypatch, broker)
    client = _client(lambda request: httpx.Response(200, json={}))
    client.user_id = "test-user-1"

    params = await client._read_s05_params(config, "test-mqtt-token")
    await client.close()

    assert params["soc"] == 71
    assert broker.login_topic == "$vdp/did-9/client/loginout"
    assert broker.condition_topic == "$vdp/did-9/properties/get/req"
    assert broker.subscribe_packet is not None
    assert b"$vdp/did-9/server/loginout" in broker.subscribe_packet
    assert b"$vdp/did-9/did-9/server/event" in broker.subscribe_packet


@pytest.mark.asyncio
async def test_read_s05_params_uses_configured_identity(monkeypatch):
    broker = _FakeMqttBroker(S05_BROKER_PARAMS)
    _install_fake_broker(monkeypatch, broker)
    client = _client(lambda request: httpx.Response(200, json={}))
    client.user_id = "test-user-1"
    client.mqtt_client_id = "client-1"
    client.mqtt_username = "user-1"

    await client._read_s05_params(_mqtt_config(), "test-mqtt-token")
    await client.close()

    assert broker.connect_packet is not None
    assert b"\x00\x08client-1" in broker.connect_packet
    assert b"\x00\x06user-1" in broker.connect_packet


@pytest.mark.asyncio
async def test_read_s05_params_prefers_config_identity(monkeypatch):
    broker = _FakeMqttBroker(S05_BROKER_PARAMS)
    _install_fake_broker(monkeypatch, broker)
    client = _client(lambda request: httpx.Response(200, json={}))
    client.user_id = "test-user-1"

    await client._read_s05_params(
        _mqtt_config(clientId="config-client", userName="config-user"),
        "test-mqtt-token",
    )
    await client.close()

    assert broker.connect_packet is not None
    assert b"config-client" in broker.connect_packet
    assert b"config-user" in broker.connect_packet


@pytest.mark.asyncio
async def test_read_s05_params_insecure_tls_override(monkeypatch, caplog):
    broker = _FakeMqttBroker(S05_BROKER_PARAMS)
    captured = _install_fake_broker(monkeypatch, broker)
    client = _client(lambda request: httpx.Response(200, json={}))
    client.user_id = "test-user-1"
    client.mqtt_tls_insecure = True

    with caplog.at_level(logging.WARNING, logger="deepal_sdk"):
        params = await client._read_s05_params(_mqtt_config(), "test-mqtt-token")
    await client.close()

    assert params["soc"] == 71
    assert captured["ssl"].verify_mode == ssl.CERT_NONE
    assert captured["ssl"].check_hostname is False
    assert "mqtt_tls_insecure" in caplog.text


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
            "driverLock": 0,
            "passengerLock": 1,
        },
        "lamp": {
            "highBeam": 1,
            "lowBeam": 0,
            "positionLamp": 1,
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
    assert condition.climate.fan_level is None
    assert condition.doors.hood_open is False
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
    assert condition.lamps.front_fog is False
    assert condition.lamps.rear_fog is False


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
    assert body["command"] == "lock"
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
    assert "rcToken" not in body
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

    await client.control_flashing_honking("car-1", FLASH_HONK_FLASH_BEE)
    await client.close()

    assert "check_calls" not in captured
    assert captured["path"] == INTL_CONTROL_FLASHING_HONKING
    body = captured["body"]
    assert body["command"] == "flash_bee"
    assert body["type"] == 3
    assert "rcToken" not in body
    _verify_signature(
        body,
        "seriralNo=SN123&type=3&vehicleId=car-1",
        public_key,
    )


def test_flash_honk_action_codes_match_app_constants():
    assert FLASH_HONK_OFF == 0
    assert FLASH_HONK_FLASH == 1
    assert FLASH_HONK_BEE == 2
    assert FLASH_HONK_FLASH_BEE == 3


@pytest.mark.asyncio
async def test_control_flashing_honking_bee_and_flash_bee_types():
    private_pem, public_key = _login_keypair()
    captured: dict = {}
    client = _client(_command_handler(public_key, captured))
    client.access_token = "test_token_123"
    client.private_key_pem = private_pem

    await client.control_flashing_honking("car-1", FLASH_HONK_BEE)
    assert captured["body"]["type"] == 2

    await client.control_flashing_honking("car-1", FLASH_HONK_FLASH_BEE)
    assert captured["body"]["type"] == 3
    await client.close()


def test_sign_payload_app_policy_excludes_sign_class_command():
    client = _client(lambda request: httpx.Response(200, json={}))
    client.private_key_pem, public_key = _login_keypair()

    signature = client.sign_payload(
        {
            "sign": "old",
            "class": "CarControlRequest.Air",
            "command": "air",
            "a": True,
            "rcToken": "",
        }
    )

    public_key.verify(
        base64.b64decode(signature),
        b"a=true&rcToken=",
        padding.PKCS1v15(),
        hashes.SHA256(),
    )


def test_sign_payload_unknown_policy_raises():
    with pytest.raises(ValueError):
        DeepalIntlClient(signing_policy="does_not_exist")


@pytest.mark.asyncio
async def test_app_signing_policy_canonical_strings_for_control_family():
    private_pem, public_key = _login_keypair()
    captured: dict = {}
    client = _client(_command_handler(public_key, captured))
    client.access_token = "test_token_123"
    client.private_key_pem = private_pem
    client.control_pin = "1234"

    await client.control_doors("car-1", True)
    _verify_signature(
        captured["body"],
        "open=true&rcToken=rc-1&seriralNo=SN123&vehicleId=car-1",
        public_key,
    )

    await client.control_windows("car-1", False)
    _verify_signature(
        captured["body"],
        "open=false&openType=10&rcToken=rc-1&seriralNo=SN123&vehicleId=car-1",
        public_key,
    )

    await client.control_trunk("car-1", True)
    _verify_signature(
        captured["body"],
        "open=true&rcToken=rc-1&seriralNo=SN123&vehicleId=car-1",
        public_key,
    )

    await client.control_charge_limit("car-1", 80)
    _verify_signature(
        captured["body"],
        "chargePercentageMax=80&rcToken=rc-1&seriralNo=SN123&vehicleId=car-1",
        public_key,
    )

    await client.control_charge_schedule("car-1", "p1", "2300", "0700", True)
    _verify_signature(
        captured["body"],
        (
            "endSwitch=1&endTime=0700&planId=p1&planType=1&rcToken=rc-1&seriralNo=SN123"
            "&startTime=2300&timeFormat=1&timeZone=GMT+08:00&vehicleId=car-1"
        ),
        public_key,
    )
    await client.close()


@pytest.mark.asyncio
async def test_legacy_signing_policy_keeps_previous_canonical_strings():
    private_pem, public_key = _login_keypair()
    captured: dict = {}
    transport = httpx.MockTransport(_command_handler(public_key, captured))
    client = DeepalIntlClient(
        country="GB",
        device_id="test-device-id",
        signing_policy="legacy",
        httpx_client=httpx.AsyncClient(transport=transport),
    )
    client.access_token = "test_token_123"
    client.private_key_pem = private_pem

    await client.control_air_conditioner("car-1", True, 22.0)
    _verify_signature(
        captured["body"],
        (
            "enabled=true&runTime=30&seriralNo=SN123&targetTemp=220"
            "&vehicleId=car-1&windMode=1"
        ),
        public_key,
    )

    await client.control_charge_limit("car-1", 80)
    _verify_signature(
        captured["body"],
        "chargePercentageMax=80&seriralNo=SN123&vehicleId=car-1",
        public_key,
    )

    await client.control_flashing_honking("car-1", FLASH_HONK_BEE)
    _verify_signature(
        captured["body"],
        "seriralNo=SN123&type=2&vehicleId=car-1",
        public_key,
    )
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("result_code", "expected_status"),
    [
        (None, CommandResultStatus.PENDING),
        (-100, CommandResultStatus.PENDING),
        (0, CommandResultStatus.SUCCESS),
        (1201, CommandResultStatus.SUCCESS),
        (1015, CommandResultStatus.ALREADY_DONE),
        (-1, CommandResultStatus.FAILED),
        (-2, CommandResultStatus.FAILED),
        (9999, CommandResultStatus.FAILED),
    ],
)
async def test_control_result_status_classifies_result_codes(
    result_code, expected_status
):
    data: dict = {"errorMsg": "boom"}
    if result_code is not None:
        data["resultCode"] = result_code

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "code": "0", "data": data})

    client = _client(handler)
    client.access_token = "test_token_123"
    result = await client.control_result_status("car-1", "cmd-1")
    await client.close()

    assert result.status is expected_status
    assert result.raw == data
    if expected_status is CommandResultStatus.FAILED:
        assert result.error_message == "boom"


OPTIONAL_COMMAND_CASES = [
    (
        "control_defrost",
        ("car-1", True),
        INTL_CONTROL_DEFROST,
        "defrost",
        {"enabled": True},
    ),
    (
        "control_seats_heat",
        ("car-1", 2, 3, 1, 0),
        INTL_CONTROL_SEATS_HEAT,
        "seats_heat",
        {
            "masterSwitch": 2,
            "masterLevel": 3,
            "copilotSwitch": 1,
        },
    ),
    (
        "control_seats_wind",
        ("car-1", 1, 2, None, None),
        INTL_CONTROL_SEATS_WIND,
        "seats_wind",
        {"masterSwitch": 1, "masterLevel": 2},
    ),
    (
        "control_steering_wheel_heat",
        ("car-1", False),
        INTL_CONTROL_STEERING_WHEEL_HEAT,
        "steering_wheel_heating",
        {"open": False},
    ),
    (
        "control_charge_plan_add",
        ("car-1", "2300", "0700", 1),
        INTL_CHARGE_ADD_PLAN,
        "add_charge_plan",
        {
            "startTime": "2300",
            "endTime": "0700",
            "endSwitch": 1,
            "planType": 1,
            "timeFormat": 1,
            "timeZone": "GMT+08:00",
        },
    ),
    (
        "control_charge_plan_delete",
        ("car-1", "plan-1"),
        INTL_CHARGE_DELETE_PLAN,
        "delete_charge_plan",
        {"planId": "plan-1"},
    ),
    (
        "control_charge_plan_validity",
        ("car-1", "plan-1", True),
        INTL_CHARGE_VALIDITY,
        "COMMAND_VALID_CHARGE_PLAN",
        {"enabled": True, "planId": "plan-1"},
    ),
    (
        "control_departure_plan_add",
        ("car-1", "0700", "1,2,3,4,5,6,7"),
        INTL_DEPARTURE_ADD_PLAN,
        "COMMAND_TRAVELPLAN_ADD",
        {
            "planType": 1,
            "startTime": "0700",
            "type": 1,
            "weeks": "1,2,3,4,5,6,7",
            "isValid": 1,
        },
    ),
    (
        "control_departure_plan_modify",
        ("car-1", 123, "0700", "1,2,3,4,5"),
        INTL_DEPARTURE_MODIFY_PLAN,
        "COMMAND_TRAVELPLAN_MODIFY_PLAN",
        {"planId": 123, "startTime": "0700", "weeks": "1,2,3,4,5"},
    ),
    (
        "control_departure_plan_delete",
        ("car-1", 123),
        INTL_DEPARTURE_DELETE,
        "COMMAND_TRAVELPLAN_DELETE",
        {"planId": 123},
    ),
    (
        "control_departure_plan_validity",
        ("car-1", 123, False),
        INTL_DEPARTURE_VALIDITY,
        "COMMAND_TRAVELPLAN_MODIFY_VALIDITY",
        {"planId": 123, "enabled": False},
    ),
    (
        "control_departure_plan_enabled",
        ("car-1", 123, True),
        INTL_DEPARTURE_ENABLED,
        "COMMAND_TRAVELPLAN_STARTSTOPPINGPLANNOW",
        {"planId": 123, "enabled": True},
    ),
    (
        "control_fota_plan",
        ("car-1", True, "1700000000000"),
        INTL_CONTROL_FOTA_PLAN,
        "COMMAND_APPOINT_UPGRADE",
        {"appointment": True, "timestamp": "1700000000000"},
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "args", "path", "command", "fields"),
    OPTIONAL_COMMAND_CASES,
)
async def test_optional_signed_commands_send_app_payload(
    method_name, args, path, command, fields
):
    private_pem, public_key = _login_keypair()
    captured: dict = {}
    client = _client(_command_handler(public_key, captured))
    client.access_token = "test_token_123"
    client.private_key_pem = private_pem

    command_id = await getattr(client, method_name)(*args)
    await client.close()

    assert command_id == "cmd-1"
    assert captured["path"] == path
    body = captured["body"]
    assert body["command"] == command
    for key, value in fields.items():
        assert body[key] == value
    assert body["seriralNo"] == "SN123"
    assert body["vehicleId"] == "car-1"
    assert body["sign"]


@pytest.mark.asyncio
async def test_charge_plan_family_uses_serial_type_2():
    private_pem, public_key = _login_keypair()
    captured: dict = {}
    client = _client(_command_handler(public_key, captured))
    client.access_token = "test_token_123"
    client.private_key_pem = private_pem

    await client.control_charge_plan_add("car-1", "2300", "0700", 1)
    await client.control_charge_plan_delete("car-1", "plan-1")
    await client.control_charge_plan_validity("car-1", "plan-1", True)
    await client.close()

    assert captured["serial_bodies"] == [{"type": "2"}, {"type": "2"}, {"type": "2"}]


@pytest.mark.asyncio
async def test_seats_heat_omits_unused_positions():
    private_pem, public_key = _login_keypair()
    captured: dict = {}
    client = _client(_command_handler(public_key, captured))
    client.access_token = "test_token_123"
    client.private_key_pem = private_pem

    await client.control_seats_heat("car-1", master_switch=1, master_level=2)
    await client.close()

    body = captured["body"]
    assert body["command"] == "seats_heat"
    assert body["masterSwitch"] == 1
    assert body["masterLevel"] == 2
    assert "copilotSwitch" not in body
    assert "copilotLevel" not in body


@pytest.mark.asyncio
async def test_seat_off_omits_the_level():
    private_pem, public_key = _login_keypair()
    captured: dict = {}
    client = _client(_command_handler(public_key, captured))
    client.access_token = "test_token_123"
    client.private_key_pem = private_pem

    await client.control_seats_wind("car-1", master_switch=0)
    await client.close()

    body = captured["body"]
    assert body["command"] == "seats_wind"
    assert body["masterSwitch"] == 0
    assert "masterLevel" not in body
    assert "copilotSwitch" not in body


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
async def test_diagnostic_app_type_and_device_type_overrides():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["apptype"] = request.headers.get("apptype")
        captured["devicetype"] = request.headers.get("devicetype")
        return httpx.Response(200, json={"success": True, "code": "0", "data": []})

    transport = httpx.MockTransport(handler)
    client = DeepalIntlClient(
        country="ES",
        device_id="test-device-id",
        app_type="iPhone",
        device_type="pixel",
        httpx_client=httpx.AsyncClient(transport=transport),
    )
    client.access_token = "test_token_123"
    await client.get_vehicles()
    await client.close()

    assert captured["apptype"] == "iPhone"
    assert captured["devicetype"] == "pixel"


@pytest.mark.asyncio
async def test_identity_header_set_on_every_request():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        return httpx.Response(200, json={"success": True, "code": "0", "data": []})

    client = _client(handler)
    client.access_token = "test_token_123"
    await client.get_vehicles()
    await client.close()

    headers = captured["headers"]
    assert headers["appid"] == "ca"
    assert headers["apptype"] == "Android"
    assert headers["appversion"] == "V1.12.0"
    assert headers["deviceid"] == "test-device-id"
    assert headers["devicetype"] == "samsung"
    assert headers["selectcountry"] == "GB"
    assert headers["language"] == "en_GB"
    assert headers["accept-language"] == "en_GB"
    assert headers["x-os-version"] == "9"
    assert "X-VCS-Nonce" not in headers
    assert "X-VCS-Hu-Token" not in headers
    assert "X-Pkg-Id" not in headers


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
        country="MX",
        environment="release_znm",
        device_id="test-device-id",
        httpx_client=httpx.AsyncClient(transport=transport),
    )
    client.access_token = "test_token_123"

    assert client.ca_base_url == "https://m.mx.changanauto.link"
    await client.get_vehicles()
    await client.close()

    assert captured["url"].host == "m.mx.changanauto.link"
    assert captured["url"].path == "/intl-app-gw/intl-app-user/api/car/vehicles"
    assert captured["appid"] == "ca"


def test_supported_environments_use_the_ca_app_id():
    from deepal.endpoints import INTL_ENVIRONMENTS

    assert all(environment.app_id == "ca" for environment in INTL_ENVIRONMENTS.values())


def test_unknown_environment_raises():
    with pytest.raises(ValueError):
        DeepalIntlClient(environment="does_not_exist")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "legacy",
    [
        "release_eu_mix",
        "preprod_eu",
        "release_ase",
        "release_ase_connect",
        "release_dlt",
        "release_st",
        "release_alq",
    ],
)
async def test_removed_environments_fall_back_to_eu(legacy):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"success": True, "code": "0", "data": {}})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = DeepalIntlClient(environment=legacy, httpx_client=http_client)
    try:
        client.access_token = "test_token_123"
        await client.get_vehicles()
    finally:
        await client.close()
        await http_client.aclose()

    assert client.environment == "release_eu"
    assert captured["url"].startswith("https://m.iov.changanauto.com.de/intl-app-gw/")


def test_environment_labels_have_no_production_suffix():
    from deepal.endpoints import INTL_ENVIRONMENTS

    assert sorted(INTL_ENVIRONMENTS) == [
        "release_eu",
        "release_znm",
    ]
    assert all("(" not in env.label for env in INTL_ENVIRONMENTS.values())


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
    assert captured["vcs"] is None


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


@pytest.mark.asyncio
async def test_managed_http_client_is_created_lazily():
    client = DeepalIntlClient(country="GB", device_id="test-device-id")
    assert client._client is None

    http_client = await client._http_client()
    assert isinstance(http_client, httpx.AsyncClient)
    assert await client._http_client() is http_client

    await client.close()
    assert http_client.is_closed


@pytest.mark.asyncio
async def test_first_request_creates_the_managed_client(monkeypatch):
    import deepal.intl as intl_module

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"success": True, "code": "0", "data": []})

    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        created = real_client(*args, **kwargs)
        captured["client"] = created
        return created

    monkeypatch.setattr(intl_module.httpx, "AsyncClient", factory)
    client = DeepalIntlClient(device_id="test-device-id")
    assert client._client is None
    try:
        client.access_token = "test_token_123"
        await client.get_vehicles()
        assert client._client is captured["client"]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_close_without_requests_is_a_noop():
    client = DeepalIntlClient(country="GB", device_id="test-device-id")
    await client.close()
    assert client._client is None


@pytest.mark.asyncio
async def test_injected_client_is_never_closed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "code": "0", "data": []})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = DeepalIntlClient(httpx_client=http_client)
    client.access_token = "test_token_123"
    try:
        await client.get_vehicles()
        await client.close()
        assert not http_client.is_closed
    finally:
        await http_client.aclose()


def test_access_token_expiry_is_computed_lazily():
    client = DeepalIntlClient(country="GB", device_id="test-device-id")
    client.access_token = _jwt_with_exp(int(time.time()) - 10)
    assert client.access_token_expires_soon() is True

    valid = DeepalIntlClient(country="GB", device_id="test-device-id")
    valid.access_token = _jwt_with_exp(int(time.time()) + 3600)
    assert valid.access_token_expires_soon() is False

    opaque = DeepalIntlClient(country="GB", device_id="test-device-id")
    opaque.access_token = "opaque-token"
    assert opaque.access_token_expires_soon() is False
    assert opaque.access_token_expires_at is None


@pytest.mark.asyncio
async def test_forced_refresh_bypasses_the_throttle_window():
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "success": True,
                "code": "0",
                "data": {"token": "test_token_new", "refreshToken": "test_refresh_new"},
            },
        )

    client = _client(handler)
    client.access_token = "test_token_old"
    client.refresh_token = "test_refresh_old"
    client._last_refresh_attempt_at = time.monotonic()
    try:
        token = await client.refresh_tokens(force=True)
    finally:
        await client.close()

    assert captured == [INTL_REFRESH_TOKEN]
    assert token.access_token == "test_token_new"
    assert client.access_token == "test_token_new"


@pytest.mark.asyncio
async def test_periodic_refresh_respects_the_throttle_window():
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "success": True,
                "code": "0",
                "data": {"token": "test_token_new", "refreshToken": "test_refresh_new"},
            },
        )

    client = _client(handler)
    client.access_token = _jwt_with_exp(int(time.time()) + 3600)
    client.refresh_token = "test_refresh_old"
    client._last_refresh_attempt_at = time.monotonic()
    try:
        token = await client.refresh_tokens()
    finally:
        await client.close()

    assert captured == []
    assert token.access_token == client.access_token


@pytest.mark.asyncio
async def test_check_control_code_refuses_when_no_attempts_remain():
    captured = {"paths": []}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["paths"].append(request.url.path)
        return httpx.Response(
            200,
            json={"success": True, "code": "0", "data": {"retryQuantity": 0}},
        )

    client = _client(handler)
    client.access_token = "test_token_123"
    try:
        with pytest.raises(DeepalRateLimitError):
            await client.check_control_code("1234")
    finally:
        await client.close()

    assert captured["paths"] == [INTL_GET_SECURITY_CODE_STATUS]


@pytest.mark.asyncio
async def test_control_code_lockout_code_maps_to_rate_limit():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": False,
                "code": "HW_1_1_01_047",
                "msg": "Too many attempts. Please try again later.",
            },
        )

    client = _client(handler)
    client.access_token = "test_token_123"
    try:
        with pytest.raises(DeepalRateLimitError) as err:
            await client.check_control_code("1234")
    finally:
        await client.close()

    assert "wait" in str(err.value).lower()
    assert "HW_1_1_01_047" in str(err.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["HW_1_1_01_073", "HW_1_1_01_074"])
async def test_control_code_state_codes_map_to_command_auth(code):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": False, "code": code, "msg": "state"})

    client = _client(handler)
    client.access_token = "test_token_123"
    try:
        with pytest.raises(DeepalCommandAuthError):
            await client.check_control_code("1234")
    finally:
        await client.close()
