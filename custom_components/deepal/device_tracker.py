"""Vehicle location tracker for the Changan Deepal integration.

The tracker is opt-in (`enable_location`, off by default): the platform is only
set up when the user enables it. European vehicles currently report no position,
so the entity may stay unknown until the server exposes one.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ENABLE_LOCATION
from .coordinator import DeepalDataUpdateCoordinator
from .entity import DeepalEntity, remove_entity_registry_entries
from .entry_platform import is_international
from .runtime_data import DeepalConfigEntry

# Registry key of the tracker entity; the unique id is ``deepal_<car>_location``.
LOCATION_KEY = "location"


def remove_location_trackers(
    hass: HomeAssistant,
    entry: DeepalConfigEntry,
    coordinator: DeepalDataUpdateCoordinator,
) -> None:
    """Remove location trackers an entry can no longer create.

    SDA entries are not forwarded to this platform, so a tracker created while
    the platform gate was missing would stay in the registry forever as an
    unavailable entity. Only the entity-registry entry is removed: the vehicle
    device and the rest of its entities are untouched.
    """
    if is_international(entry):
        return
    registry = er.async_get(hass)
    for vehicle in coordinator.vehicles:
        remove_entity_registry_entries(
            registry, vehicle, "device_tracker", (LOCATION_KEY,)
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeepalConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the location tracker for international entries with the option on."""
    if not is_international(entry):
        return
    if not entry.options.get(CONF_ENABLE_LOCATION, False):
        return
    coordinator: DeepalDataUpdateCoordinator = entry.runtime_data.coordinator
    entities = [
        DeepalLocationTracker(coordinator, vehicle)
        for vehicle in coordinator.vehicles
    ]
    if entities:
        async_add_entities(entities)


class DeepalLocationTracker(DeepalEntity, TrackerEntity):
    """Last known vehicle position, kept across reports without coordinates."""

    _attr_source_type = SourceType.GPS
    _attr_translation_key = "location"

    def __init__(
        self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any
    ) -> None:
        """Initialize the location tracker."""
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_{LOCATION_KEY}"

    @property
    def latitude(self) -> float | None:
        """Return the vehicle latitude when the car has reported one."""
        cond = self.condition
        return cond.latitude if cond else None

    @property
    def longitude(self) -> float | None:
        """Return the vehicle longitude when the car has reported one."""
        cond = self.condition
        return cond.longitude if cond else None
