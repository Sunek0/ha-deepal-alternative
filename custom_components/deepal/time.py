"""Time platform (charge schedule) for the Changan Deepal integration."""

from datetime import time
from typing import Any

from homeassistant.components.time import TimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import DeepalDataUpdateCoordinator
from .entity import DeepalEntity, async_setup_control_entities
from .runtime_data import DeepalConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeepalConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the charge schedule time entities."""
    async_setup_control_entities(
        hass,
        entry,
        async_add_entities,
        lambda coordinator, vehicle: [
            DeepalChargeScheduleTime(
                coordinator, vehicle, "charge_schedule_start", "start"
            ),
            DeepalChargeScheduleTime(
                coordinator, vehicle, "charge_schedule_end", "end"
            ),
        ],
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

    _attr_icon = "mdi:clock-outline"

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

    async def async_set_value(self, value: time) -> None:
        """Update the schedule time."""
        cond = self.condition
        if not cond or not cond.battery.charge_plan_id:
            raise HomeAssistantError("Deepal charge schedule plan is not available")
        start = cond.battery.charge_schedule_start or "0000"
        end = cond.battery.charge_schedule_end or "0000"
        if self._field == "start":
            start = _format_hhmm(value)
        else:
            end = _format_hhmm(value)

        def _optimistic(condition: Any) -> Any:
            condition.battery.charge_schedule_start = start
            condition.battery.charge_schedule_end = end
            return condition

        await self.async_send_command(
            lambda: self.client.control_charge_schedule(
                self._car_id,
                cond.battery.charge_plan_id,
                start,
                end,
                cond.battery.charge_schedule_enabled,
                cond.battery.charge_plan_type or 1,
                cond.battery.charge_plan_time_format or 1,
                cond.battery.charge_plan_time_zone or "GMT+08:00",
            ),
            optimistic_update=_optimistic,
        )
