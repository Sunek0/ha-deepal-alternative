"""Tests for the Home Assistant vehicle image platform.

These tests exercise the bundled per-model resolver and the bounded API image
fetch without starting a Home Assistant runtime. The last test drives
``homeassistant.components.image.async_get_image`` with a hanging API fetch to
prove the image proxy receives the bundled fallback before its deadline.
"""

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

pytest.importorskip("homeassistant")

from homeassistant.components.image import (
    DATA_COMPONENT,
    IMAGE_TIMEOUT,
    async_get_image,
)
from homeassistant.helpers.httpx_client import DATA_ASYNC_CLIENT
from homeassistant.util.ssl import SSL_ALPN_HTTP11

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from custom_components.deepal import image as image_platform
from custom_components.deepal.image import (
    API_IMAGE_TIMEOUT,
    SVG_CONTENT_TYPE,
    DeepalVehicleImage,
    vehicle_image_asset,
)

ASSETS_DIR = REPO_ROOT / "custom_components" / "deepal" / "assets"
GENERIC_ASSET = ASSETS_DIR / "vehicle_generic.svg"
API_IMAGE = b"\x89PNG\r\n\x1a\napi-image-bytes"
API_IMAGE_URL = "https://example.invalid/car.png"


class FakeResponse:
    """Stand-in for the parts of ``httpx.Response`` the entity uses."""

    def __init__(
        self,
        content: bytes = API_IMAGE,
        content_type: str | None = "image/png",
        status_code: int = 200,
    ) -> None:
        self.content = content
        self.headers = {} if content_type is None else {"content-type": content_type}
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("GET", API_IMAGE_URL),
                response=httpx.Response(self.status_code),
            )


class FakeHttpClient:
    """HTTP client double recording the fetch budget used by the entity."""

    def __init__(
        self,
        response: FakeResponse | None = None,
        error: Exception | None = None,
        delay: float = 0.0,
    ) -> None:
        self.response = response
        self.error = error
        self.delay = delay
        self.calls: list[tuple[str, float | None, bool]] = []

    async def get(
        self, url: str, *, timeout: float | None = None, follow_redirects: bool = False
    ) -> FakeResponse:
        self.calls.append((url, timeout, follow_redirects))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def _fake_hass(client: FakeHttpClient) -> SimpleNamespace:
    """Minimal hass double whose data contains the entity HTTP client."""

    async def async_add_executor_job(func, *args):
        return func(*args)

    return SimpleNamespace(
        data={DATA_ASYNC_CLIENT: {(False, SSL_ALPN_HTTP11): client}},
        async_add_executor_job=async_add_executor_job,
    )


def _vehicle(
    thumbnail_url: str | None = None,
    series_name: str = "Deepal S09",
    model_name: str | None = None,
    car_id: str = "car-1",
) -> SimpleNamespace:
    return SimpleNamespace(
        car_id=car_id,
        vin="test-vin",
        series_name=series_name,
        car_name=None,
        model_name=model_name,
        thumbnail_url=thumbnail_url,
    )


class FakeCoordinator:
    """Coordinator double with the attributes the image entity reads."""

    def __init__(self, hass: SimpleNamespace, data: dict | None = None) -> None:
        self.hass = hass
        self.data = data or {}


def _entity(
    client: FakeHttpClient,
    vehicle: SimpleNamespace,
    data: dict | None = None,
) -> DeepalVehicleImage:
    hass = _fake_hass(client)
    entity = DeepalVehicleImage(FakeCoordinator(hass, data), vehicle)
    entity.hass = hass
    return entity


@pytest.mark.parametrize(
    ("series", "model", "expected"),
    [
        ("Deepal S05 Max", None, "vehicle_s05.svg"),
        ("Deepal S07", None, "vehicle_s07.svg"),
        ("Deepal SL03", None, "vehicle_sl03.svg"),
        ("Deepal L07", None, "vehicle_l07.svg"),
        ("deepal sl03", None, "vehicle_sl03.svg"),
        ("Deepal S05 Max 2026", None, "vehicle_s05.svg"),
        (None, "CD701", "vehicle_generic.svg"),
        ("Deepal S09", None, "vehicle_generic.svg"),
        (None, None, "vehicle_generic.svg"),
    ],
)
def test_vehicle_image_asset_resolution(
    series: str | None, model: str | None, expected: str
) -> None:
    asset = vehicle_image_asset(series, None, model_name=model)
    assert asset.name == expected
    assert asset.exists()


@pytest.mark.asyncio
async def test_api_image_is_fetched_once_with_a_bounded_timeout() -> None:
    client = FakeHttpClient(response=FakeResponse())
    entity = _entity(client, _vehicle(thumbnail_url=API_IMAGE_URL))

    assert await entity.async_image() == API_IMAGE
    assert entity.content_type == "image/png"
    assert await entity.async_image() == API_IMAGE

    assert len(client.calls) == 1
    url, timeout, follow_redirects = client.calls[0]
    assert url == API_IMAGE_URL
    assert timeout == API_IMAGE_TIMEOUT
    assert follow_redirects is True
    assert API_IMAGE_TIMEOUT < IMAGE_TIMEOUT


@pytest.mark.asyncio
async def test_api_image_timeout_serves_the_bundled_asset_without_retry() -> None:
    client = FakeHttpClient(error=httpx.ReadTimeout("too slow"))
    entity = _entity(client, _vehicle(thumbnail_url=API_IMAGE_URL))

    assert await entity.async_image() == GENERIC_ASSET.read_bytes()
    assert entity.content_type == SVG_CONTENT_TYPE
    assert await entity.async_image() == GENERIC_ASSET.read_bytes()
    assert len(client.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(status_code=500),
        FakeResponse(content=b"<html>not an image</html>", content_type="text/html"),
        FakeResponse(content=b"", content_type=None),
        FakeResponse(content=b"", content_type="image/png"),
        FakeResponse(content=b"<html>error page</html>", content_type="image/png"),
    ],
)
async def test_api_image_failures_serve_the_bundled_asset(
    response: FakeResponse,
) -> None:
    client = FakeHttpClient(response=response)
    entity = _entity(client, _vehicle(thumbnail_url=API_IMAGE_URL))

    assert await entity.async_image() == GENERIC_ASSET.read_bytes()
    assert entity.content_type == SVG_CONTENT_TYPE


@pytest.mark.asyncio
async def test_api_image_with_charset_serves_a_clean_content_type() -> None:
    """The Changan CDN sends image/png;charset=utf-8 and aiohttp rejects it."""
    client = FakeHttpClient(
        response=FakeResponse(content_type="image/png;charset=utf-8")
    )
    entity = _entity(client, _vehicle(thumbnail_url=API_IMAGE_URL))

    assert await entity.async_image() == API_IMAGE
    assert entity.content_type == "image/png"


@pytest.mark.asyncio
async def test_proxy_serves_api_image_with_charset_content_type() -> None:
    client = FakeHttpClient(
        response=FakeResponse(content_type="image/png;charset=utf-8")
    )
    entity = _entity(client, _vehicle(thumbnail_url=API_IMAGE_URL))
    entity.entity_id = "image.test_vehicle"
    entity.hass.data[DATA_COMPONENT] = _FakeImageComponent(entity)

    image = await async_get_image(
        entity.hass, "image.test_vehicle", timeout=IMAGE_TIMEOUT
    )

    assert image.content == API_IMAGE
    assert image.content_type == "image/png"
    assert ";" not in image.content_type


@pytest.mark.asyncio
async def test_invalid_api_url_serves_the_bundled_asset() -> None:
    client = FakeHttpClient(error=httpx.InvalidURL("not a valid URL"))
    entity = _entity(client, _vehicle(thumbnail_url="not a url"))

    assert await entity.async_image() == GENERIC_ASSET.read_bytes()
    assert entity.content_type == SVG_CONTENT_TYPE


@pytest.mark.asyncio
async def test_vehicle_without_api_image_never_touches_the_network() -> None:
    client = FakeHttpClient(error=AssertionError("network must not be used"))
    entity = _entity(client, _vehicle(thumbnail_url=None))

    assert await entity.async_image() == GENERIC_ASSET.read_bytes()
    assert entity.content_type == SVG_CONTENT_TYPE
    assert client.calls == []


@pytest.mark.asyncio
async def test_fallback_uses_the_vehicle_model_render() -> None:
    s05 = _entity(
        FakeHttpClient(),
        _vehicle(thumbnail_url=None, series_name="Deepal S05 Max"),
    )
    l07 = _entity(
        FakeHttpClient(),
        _vehicle(thumbnail_url=None, series_name="Deepal L07"),
    )

    assert await s05.async_image() == (ASSETS_DIR / "vehicle_s05.svg").read_bytes()
    assert await l07.async_image() == (ASSETS_DIR / "vehicle_l07.svg").read_bytes()


@pytest.mark.asyncio
async def test_image_entity_contract_and_metadata() -> None:
    entity = _entity(FakeHttpClient(), _vehicle(thumbnail_url=None))

    assert entity.has_entity_name is True
    assert entity.translation_key == "vehicle_image"
    assert entity.unique_id == "deepal_car-1_vehicle_image"
    assert entity.image_last_updated is not None
    assert entity.state is not None


@pytest.mark.asyncio
async def test_image_last_updated_uses_the_vehicle_report_time() -> None:
    condition = SimpleNamespace(last_updated_timestamp=1_700_000_000)
    entity = _entity(
        FakeHttpClient(),
        _vehicle(thumbnail_url=None),
        data={"car-1": condition},
    )

    assert entity.image_last_updated == datetime.fromtimestamp(
        1_700_000_000, tz=UTC
    )


class _FakeImageComponent:
    """Image component double that resolves one entity id."""

    def __init__(self, entity: DeepalVehicleImage) -> None:
        self.entity = entity

    def get_entity(self, entity_id: str) -> DeepalVehicleImage | None:
        if entity_id == "image.test_vehicle":
            return self.entity
        return None


@pytest.mark.asyncio
async def test_async_setup_entry_adds_one_entity_per_vehicle() -> None:
    hass = _fake_hass(FakeHttpClient())
    coordinator = FakeCoordinator(hass)
    coordinator.vehicles = [
        _vehicle(car_id="car-1"),
        _vehicle(car_id="car-2", series_name="Deepal S07"),
    ]
    entry = SimpleNamespace(runtime_data=SimpleNamespace(coordinator=coordinator))
    added: list[DeepalVehicleImage] = []

    await image_platform.async_setup_entry(hass, entry, added.extend)

    assert len(added) == 2
    assert {entity.unique_id for entity in added} == {
        "deepal_car-1_vehicle_image",
        "deepal_car-2_vehicle_image",
    }


@pytest.mark.asyncio
async def test_async_setup_entry_without_vehicles_adds_nothing() -> None:
    hass = _fake_hass(FakeHttpClient())
    coordinator = FakeCoordinator(hass)
    coordinator.vehicles = []
    entry = SimpleNamespace(runtime_data=SimpleNamespace(coordinator=coordinator))
    added: list[DeepalVehicleImage] = []

    await image_platform.async_setup_entry(hass, entry, added.extend)

    assert added == []


@pytest.mark.asyncio
async def test_proxy_deadline_serves_the_fallback_with_a_hanging_api_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(image_platform, "API_IMAGE_TIMEOUT", 0.05)
    client = FakeHttpClient(delay=0.05, error=httpx.ReadTimeout("too slow"))
    entity = _entity(client, _vehicle(thumbnail_url=API_IMAGE_URL))
    entity.entity_id = "image.test_vehicle"
    entity.hass.data[DATA_COMPONENT] = _FakeImageComponent(entity)

    image = await async_get_image(entity.hass, "image.test_vehicle", timeout=IMAGE_TIMEOUT)

    assert image.content == GENERIC_ASSET.read_bytes()
    assert image.content_type == SVG_CONTENT_TYPE
    assert len(client.calls) == 1
