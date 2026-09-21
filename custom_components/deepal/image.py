"""Image platform for the Changan Deepal integration."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import DeepalDataUpdateCoordinator
from .entity import DeepalEntity
from .runtime_data import DeepalConfigEntry

ASSETS_DIR = Path(__file__).parent / "assets"
GENERIC_ASSET = ASSETS_DIR / "vehicle_generic.svg"
SVG_CONTENT_TYPE = "image/svg+xml"

# Match the longest codes first so no model code is a prefix of another.
_MODEL_CODES = ("SL03", "S07", "L07", "S05")


def _normalize(value: str | None) -> str:
    """Upper-case alphanumerics of a vehicle name, for containment checks."""
    return "".join(character for character in (value or "").upper() if character.isalnum())


def vehicle_image_asset(
    series_name: str | None = None,
    car_name: str | None = None,
    model_name: str | None = None,
) -> Path:
    """Return the bundled fallback asset for a vehicle model.

    The S05 Pro and Max share the same official render for now; per-trim art
    can be reintroduced here when available (the capability trim hint stays
    exposed in the diagnostics for that purpose). Unknown models fall back to
    the generic Deepal image, and models without a bundled render use a
    text-only placeholder.
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
    """Set up the vehicle image entities."""
    coordinator: DeepalDataUpdateCoordinator = entry.runtime_data.coordinator

    async_add_entities(
        DeepalVehicleImage(coordinator, vehicle)
        for vehicle in coordinator.vehicles
    )


class DeepalVehicleImage(DeepalEntity, ImageEntity):
    """Vehicle photo with a bundled per-model fallback.

    The image URL returned by the API wins when present; otherwise the entity
    serves a bundled SVG selected from the model and trim, so the picture on
    the device page always exists.
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
        if not self.vehicle.thumbnail_url:
            # Static bundled image: content type and "last updated" only need
            # to be set once, at startup.
            self._attr_content_type = SVG_CONTENT_TYPE
            self._attr_image_last_updated = datetime.now(UTC)

    @property
    def image_url(self) -> str | None:
        """Return the API image URL, when the vehicle list provides one."""
        return self.vehicle.thumbnail_url

    @property
    def content_type(self) -> str:
        """Return the content type of the served image."""
        if self.vehicle.thumbnail_url:
            return self._attr_content_type
        return SVG_CONTENT_TYPE

    @property
    def image_last_updated(self) -> datetime | None:
        """Return the report time used to refresh the image cache."""
        if self.vehicle.thumbnail_url:
            condition = self.coordinator.data.get(self._car_id)
            if condition is not None and condition.last_updated_timestamp is not None:
                return datetime.fromtimestamp(
                    condition.last_updated_timestamp, tz=UTC
                )
            return self._attr_image_last_updated
        return self._attr_image_last_updated

    def _asset_path(self) -> Path:
        """Return the bundled asset for this vehicle."""
        return vehicle_image_asset(
            self.vehicle.series_name,
            self.vehicle.car_name,
            model_name=self.vehicle.model_name,
        )

    async def async_image(self) -> bytes | None:
        """Return the API image bytes, or the bundled fallback."""
        if self.vehicle.thumbnail_url:
            return await super().async_image()
        path = self._asset_path()
        if path not in self._asset_cache:
            self._asset_cache[path] = await self.hass.async_add_executor_job(
                path.read_bytes
            )
        return self._asset_cache[path]
