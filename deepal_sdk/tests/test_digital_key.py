"""Unit tests for the read-only digital key checks."""

import json

import httpx
import pytest

from deepal import DeepalIntlClient
from deepal.endpoints import (
    INTL_CA_GET_CAR_AUTH_LIST,
    INTL_CA_GET_DIGITAL_KEY_SUPPORT,
    get_intl_environment,
)
from deepal.models.digital_key import (
    DIGITAL_KEY_FUNCTION_CODE,
    DigitalKeySupport,
    VehicleAuthorizations,
)

ACCESS_TOKEN = "test_token_123"
USER_ID = "test_user_123"
CAR_ID = "test_car_123"


def _client(handler) -> DeepalIntlClient:
    transport = httpx.MockTransport(handler)
    client = DeepalIntlClient(
        country="ES",
        language="es_ES",
        device_id="test-device-id",
        os_version="9",
        httpx_client=httpx.AsyncClient(transport=transport),
    )
    client.access_token = ACCESS_TOKEN
    client.user_id = USER_ID
    return client


def test_environment_exposes_sda_gateway():
    europe = get_intl_environment("release_eu")
    latin_america = get_intl_environment("release_znm")

    assert europe.sda_base_url == "https://sda-m.iov.changanauto.com.de"
    assert latin_america.sda_base_url == "https://sda-m.mx.changanauto.link"


def test_client_uses_environment_sda_url_and_override():
    environment_client = DeepalIntlClient(environment="release_eu")
    overridden = DeepalIntlClient(sda_base_url="https://sda.example.test")

    assert environment_client.sda_base_url == "https://sda-m.iov.changanauto.com.de"
    assert overridden.sda_base_url == "https://sda.example.test"


def test_support_flag_mapping():
    ca_key = DigitalKeySupport.from_flag(0)
    icce_key = DigitalKeySupport.from_flag(1)
    honor_key = DigitalKeySupport.from_flag(2)
    unknown = DigitalKeySupport.from_flag(9)

    assert ca_key.key_type == "ca" and ca_key.supported is True
    assert icce_key.key_type == "icce"
    assert honor_key.key_type == "honor"
    assert unknown.key_type == "unknown" and unknown.supported is False


@pytest.mark.asyncio
async def test_get_digital_key_support_posts_device_identity():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"success": True, "code": 0, "data": {"flag": 0}})

    client = _client(handler)
    result = await client.get_digital_key_support()

    assert result is not None
    assert result.supported is True
    assert result.flag == 0

    request = requests[0]
    assert str(request.url) == (
        "https://sda-m.iov.changanauto.com.de" + INTL_CA_GET_DIGITAL_KEY_SUPPORT
    )
    assert request.headers["X-Tsp-User-Token"] == ACCESS_TOKEN
    body = json.loads(request.content)
    assert body["userId"] == USER_ID
    assert body["deviceInfo"] == {
        "terminal": "samsung",
        "romVersion": "9",
        "clientVersion": "V1.12.0",
    }
    assert "carId" not in body


@pytest.mark.asyncio
async def test_get_digital_key_support_includes_vehicle_when_given():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"success": True, "data": {"flag": 0}})

    client = _client(handler)
    await client.get_digital_key_support(CAR_ID)

    assert json.loads(requests[0].content)["carId"] == CAR_ID


@pytest.mark.asyncio
async def test_get_digital_key_support_requires_user_id():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"success": True, "data": {"flag": 0}})

    client = _client(handler)
    client.user_id = None

    assert await client.get_digital_key_support() is None
    assert calls == 0


@pytest.mark.asyncio
async def test_get_digital_key_support_missing_flag_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "data": {}})

    client = _client(handler)

    assert await client.get_digital_key_support() is None


@pytest.mark.asyncio
async def test_get_digital_key_support_rate_limit_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"success": False, "code": "CAC_1_1_01_033", "msg": "slow down"},
        )

    client = _client(handler)

    assert await client.get_digital_key_support() is None


@pytest.mark.asyncio
async def test_get_digital_key_support_api_error_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"success": False, "code": "APP_1_1_02_003", "msg": "nope"}
        )

    client = _client(handler)

    assert await client.get_digital_key_support() is None


@pytest.mark.asyncio
async def test_get_vehicle_authorizations_reads_digital_key_flag():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "authList": [
                        {"functionCode": "RemoteControlLock"},
                        {"functionCode": DIGITAL_KEY_FUNCTION_CODE},
                    ]
                },
            },
        )

    client = _client(handler)
    result = await client.get_vehicle_authorizations(CAR_ID)

    assert result is not None
    assert result.digital_key is True
    assert result.has_code(DIGITAL_KEY_FUNCTION_CODE)
    assert result.has_code("RemoteControlLock")


@pytest.mark.asyncio
async def test_get_vehicle_authorizations_without_digital_key():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"success": True, "data": {"authList": ["RemoteControlLock"]}},
        )

    client = _client(handler)
    result = await client.get_vehicle_authorizations(CAR_ID)

    assert result is not None
    assert result.digital_key is False
    assert result.raw_codes == ["RemoteControlLock"]


@pytest.mark.asyncio
async def test_get_vehicle_authorizations_falls_back_between_bodies():
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if "carId" in body:
            return httpx.Response(
                200, json={"success": False, "code": "COMMON_1_1_01_099", "msg": "bad"}
            )
        return httpx.Response(
            200,
            json={"success": True, "data": {"functionCodes": ["DigitalKey"]}},
        )

    client = _client(handler)
    result = await client.get_vehicle_authorizations(CAR_ID)

    assert result is not None
    assert result.digital_key is True
    assert [sorted(body) for body in bodies] == [
        ["carId"],
        ["vehicleId"],
    ]


@pytest.mark.asyncio
async def test_get_vehicle_authorizations_unavailable_service_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="<html>404 Not Found</html>")

    client = _client(handler)

    assert await client.get_vehicle_authorizations(CAR_ID) is None


@pytest.mark.asyncio
async def test_get_vehicle_authorizations_empty_list_is_an_answer():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "data": {"authList": []}})

    client = _client(handler)
    result = await client.get_vehicle_authorizations(CAR_ID)

    assert result is not None
    assert result.raw_codes == []
    assert result.digital_key is False


@pytest.mark.asyncio
async def test_get_vehicle_authorizations_rate_limit_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"success": False, "code": "CAC_1_1_01_033", "msg": "slow down"},
        )

    client = _client(handler)

    assert await client.get_vehicle_authorizations(CAR_ID) is None


def test_vehicle_authorizations_tolerates_unknown_shapes():
    assert VehicleAuthorizations.from_payload(None).raw_codes == []
    assert VehicleAuthorizations.from_payload({"weird": 1}).raw_codes == []
    assert VehicleAuthorizations.from_payload(["A", {"code": "B"}]).raw_codes == [
        "A",
        "B",
    ]
