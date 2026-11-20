"""Time platform (charge schedule) for the Changan Deepal integration."""

from datetime import time
from typing import Any

from homeassistant.components.time import TimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .charge_schedule import async_set_charge_schedule, ha_gmt_offset
from .coordinator import DeepalDataUpdateCoordinator
from .entity import (
    DeepalEntity,
    async_setup_control_entities,
    remove_entity_registry_entries,
)
from .runtime_data import DeepalConfigEntry
from .vehicle_model import is_s05, is_s05_phev, supports_charge_schedule

# The coordinator serializes state-sharing commands per vehicle
PARALLEL_UPDATES = 0

#: Time keys that only exist on models with the charge-schedule option.
CHARGE_SCHEDULE_TIME_KEYS = frozenset(
    {"charge_schedule_start", "charge_schedule_end"}
)


def build_times(
    coordinator: DeepalDataUpdateCoordinator, vehicle: Any
) -> list[TimeEntity]:
    """Build the charge-schedule time entities when the model supports them."""
    if not supports_charge_schedule(vehicle):
        return []
    return [
        DeepalChargeScheduleTime(coordinator, vehicle, "charge_schedule_start", "start"),
        DeepalChargeScheduleTime(coordinator, vehicle, "charge_schedule_end", "end"),
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeepalConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the charge schedule time entities."""
    coordinator: DeepalDataUpdateCoordinator = entry.runtime_data.coordinator
    registry = er.async_get(hass)

    for vehicle in coordinator.vehicles:
        if not supports_charge_schedule(vehicle):
            remove_entity_registry_entries(
                registry, vehicle, "time", CHARGE_SCHEDULE_TIME_KEYS
            )

    async_setup_control_entities(
        hass,
        entry,
        async_add_entities,
        build_times,
    )


def _parse_hhmm(value: Any) -> time | None:
    if value is None:
        return None
    text = str(value).zfill(4)
    if len(text) != 4 or not text.isdigit():
        return None
    hour = int(text[:2])
    minute = int(text[2:])
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)


def _format_hhmm(value: time) -> str:
    return f"{value.hour:02d}{value.minute:02d}"


class DeepalChargeScheduleTime(DeepalEntity, TimeEntity):
    """Start or end time of the charging schedule."""


    def __init__(
        self,
        coordinator: DeepalDataUpdateCoordinator,
        vehicle: Any,
        key: str,
        field: str,
    ) -> None:
        """Initialize the schedule time entity."""
        super().__init__(coordinator, vehicle)
        self._field = field
        self._attr_unique_id = f"deepal_{vehicle.car_id}_{key}"
        self._attr_translation_key = key

    @property
    def native_value(self) -> time | None:
        """Return the configured time."""
        cond = self.condition
        if not cond:
            return None
        value = (
            cond.battery.charge_schedule_start
            if self._field == "start"
            else cond.battery.charge_schedule_end
        )
        return _parse_hhmm(value)

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Expose the timezone the plan time is expressed in."""
        cond = self.condition
        zone = cond.battery.charge_plan_time_zone if cond else None
        if not zone:
            hass = getattr(self, "hass", None)
            if hass is not None:
                zone = ha_gmt_offset(hass)
        return {"time_zone": zone} if zone else None

    async def async_set_value(self, value: time) -> None:
        """Update the schedule time."""
        cond = self.condition
        start = (
            cond.battery.charge_schedule_start or "0000"
            if cond is not None
            else "0000"
        )
        end = (
            cond.battery.charge_schedule_end or "0800"
            if cond is not None
            else "0800"
        )
        if self._field == "start":
            start = _format_hhmm(value)
        else:
            end = _format_hhmm(value)

        # None = keep whatever the car reports right now. The coordinator state
        # can lag a few seconds behind an add/delete, and using it here turned a
        # time edit right after "on" into an "off".
        enabled = None
        if is_s05(self.vehicle) and not is_s05_phev(self.vehicle):
            # The BEV has no separate "store a disabled plan" command: a new
            # add-plan with the chosen times becomes active immediately.
            enabled = True

        await async_set_charge_schedule(
            self.coordinator,
            self.vehicle,
            start,
            end,
            enabled,
            ha_gmt_offset(self.hass),
            wait_for_plan=False,
        )
