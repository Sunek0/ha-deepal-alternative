"""Image platform for the Changan Deepal integration.

The API image is fetched inside the entity with a timeout shorter than the
Home Assistant image proxy deadline, so the bundled per-model asset can always
be served before the proxy gives up.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from homeassistant.components.image import (
    ImageContentTypeError,
    ImageEntity,
    infer_image_type,
    valid_image_content_type,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import DeepalDataUpdateCoordinator
from .entity import DeepalEntity
from .runtime_data import DeepalConfigEntry

_LOGGER = logging.getLogger(__name__)

ASSETS_DIR = Path(__file__).parent / "assets"
GENERIC_ASSET = ASSETS_DIR / "vehicle_generic.svg"
SVG_CONTENT_TYPE = "image/svg+xml"

# The Home Assistant image proxy cancels the fetch after 10 seconds
# (homeassistant.components.image.IMAGE_TIMEOUT). The base ImageEntity fetches
# a URL with the same 10 seconds, so a slow API image loses the race and the
# proxy answers "Unable to get image" before any fallback can run. The entity
# owns the fetch with a shorter budget instead; keep this below IMAGE_TIMEOUT.
API_IMAGE_TIMEOUT = 5.0

# Match the longest codes first so no model code is a prefix of another.
_MODEL_CODES = ("SL03", "S07", "L07", "S05")


def _normalize(value: str | None) -> str:
    """Upper-case alphanumerics of a vehicle name, for containment checks."""
    return "".join(
        character for character in (value or "").upper() if character.isalnum()
    )


def vehicle_image_asset(
    series_name: str | None = None,
    car_name: str | None = None,
    model_name: str | None = None,
) -> Path:
    """Return the bundled fallback asset for a vehicle model.

    The S05 Pro and Max share the same official render; per-trim art can be
    reintroduced here when available (the capability trim hint stays exposed in
    the diagnostics for that purpose). Unknown models fall back to the generic
    Deepal image, and models without a bundled render use a text placeholder.
    """
    normalized = " ".join(
        filter(
            None,
            (
                _normalize(series_name),
                _normalize(model_name),
                _normalize(car_name),
            ),
        )
    )

    model = next(
        (code for code in _MODEL_CODES if code in normalized),
        None,
    )
    if model is not None:
        return ASSETS_DIR / f"vehicle_{model.lower()}.svg"
    return GENERIC_ASSET


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeepalConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one vehicle image entity per configured vehicle."""
    coordinator: DeepalDataUpdateCoordinator = entry.runtime_data.coordinator

    if not coordinator.vehicles:
        _LOGGER.debug("Deepal vehicle image setup: no vehicles to add")
        return

    _LOGGER.debug(
        "Deepal vehicle image setup: adding %s entities", len(coordinator.vehicles)
    )
    async_add_entities(
        DeepalVehicleImage(coordinator, vehicle) for vehicle in coordinator.vehicles
    )


class DeepalVehicleImage(DeepalEntity, ImageEntity):
    """Vehicle photo with a bundled per-model fallback.

    The image URL returned by the API wins when it loads; otherwise the entity
    serves a bundled SVG selected from the model, so the picture on the device
    page always exists and the image proxy never ends in "Unable to get image".
    """

    _attr_has_entity_name = True
    _attr_translation_key = "vehicle_image"

    def __init__(
        self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any
    ) -> None:
        """Initialize the vehicle image entity."""
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_vehicle_image"
        ImageEntity.__init__(self, coordinator.hass)
        self._asset_cache: dict[Path, bytes] = {}
        self._api_image: bytes | None = None
        self._api_fetch_done = not bool(vehicle.thumbnail_url)
        # The state must never be None: the bundled asset (or a successful API
        # fetch) always has a known "last updated" time.
        self._attr_image_last_updated = datetime.now(UTC)
        if self._api_fetch_done:
            self._attr_content_type = SVG_CONTENT_TYPE

    @property
    def image_url(self) -> str | None:
        """Return the API image URL, when the vehicle list provides one."""
        return self.vehicle.thumbnail_url

    @property
    def image_last_updated(self) -> datetime | None:
        """Return the report time used to refresh the image cache."""
        condition = self.coordinator.data.get(self._car_id)
        if condition is not None and condition.last_updated_timestamp is not None:
            return datetime.fromtimestamp(
                condition.last_updated_timestamp, tz=UTC
            )
        return self._attr_image_last_updated

    def _asset_path(self) -> Path:
        """Return the bundled asset for this vehicle."""
        return vehicle_image_asset(
            self.vehicle.series_name,
            self.vehicle.car_name,
            model_name=self.vehicle.model_name,
        )

    async def _async_fetch_api_image(self) -> None:
        """Fetch the API image once, with a shorter timeout than the proxy's.

        Any failure is non-fatal: the bundled asset covers it and the fetch is
        not retried for this entity, so a slow or dead URL never costs every
        image request the whole timeout.
        """
        self._api_fetch_done = True
        url = self.vehicle.thumbnail_url
        if not url:
            return

        try:
            response = await self._client.get(
                url,
                timeout=API_IMAGE_TIMEOUT,
                follow_redirects=True,
            )
            response.raise_for_status()
            content_type = valid_image_content_type(
                response.headers.get("content-type")
                or infer_image_type(response.content)
            )
        except (
            httpx.HTTPError,
            httpx.InvalidURL,
            ImageContentTypeError,
            ValueError,
        ) as err:
            _LOGGER.debug(
                "Deepal vehicle image fetch failed for %s: %s", self._car_id, err
            )
            return

        # Trust the declared type only when the body really is a known image:
        # an HTML error page with an image content type would otherwise be
        # served as a picture and show as a broken image in the frontend. The
        # type exposed is the one detected from the magic bytes, so parameters
        # such as ";charset=utf-8" (which Changan's CDN sends and aiohttp
        # rejects in web.Response) never reach the image proxy.
        detected_type = infer_image_type(response.content)
        if detected_type is None:
            _LOGGER.debug(
                "Deepal vehicle image for %s is not a recognised image (%s bytes, "
                "declared %s); using the bundled asset",
                self._car_id,
                len(response.content),
                content_type,
            )
            return

        self._api_image = response.content
        self._attr_content_type = detected_type
        _LOGGER.debug(
            "Deepal vehicle image loaded from the API for %s", self._car_id
        )

    async def _asset_bytes(self, path: Path) -> bytes | None:
        """Return the bundled asset bytes, reading them once per entity.

        Falls back to the generic asset when the model render is missing, and
        logs a clear error when the assets were not deployed at all.
        """
        for candidate in dict.fromkeys((path, GENERIC_ASSET)):
            if candidate not in self._asset_cache:
                if not await self.hass.async_add_executor_job(candidate.is_file):
                    continue
                self._asset_cache[candidate] = (
                    await self.hass.async_add_executor_job(candidate.read_bytes)
                )
            return self._asset_cache[candidate]

        _LOGGER.error(
            "Deepal vehicle image assets are missing (%s); reinstall the "
            "integration so the assets directory is deployed",
            path,
        )
        return None

    async def async_image(self) -> bytes | None:
        """Return the API image bytes, or the bundled fallback.

        A missing, slow, unreachable or non-image API response must never leave
        the entity without a picture, because the Home Assistant image proxy
        cancels the request when the entity takes too long.
        """
        if not self._api_fetch_done:
            await self._async_fetch_api_image()

        if self._api_image is not None:
            return self._api_image

        self._attr_content_type = SVG_CONTENT_TYPE
        asset = self._asset_path()
        _LOGGER.debug(
            "Deepal vehicle image for %s served from the bundled asset (%s)",
            self._car_id,
            asset.name,
        )
        return await self._asset_bytes(asset)
