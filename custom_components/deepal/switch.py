"""Switch platform (charge schedule) for the Changan Deepal integration."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import DeepalDataUpdateCoordinator
from .entity import DeepalEntity, async_setup_control_entities
from .runtime_data import DeepalConfigEntry


def _set_schedule_enabled(condition: Any, enabled: bool) -> Any:
    condition.battery.charge_schedule_enabled = enabled
    return condition


def _set_steering_wheel_heat(condition: Any, enabled: bool) -> Any:
    condition.climate.steering_wheel_heater_on = enabled
    return condition


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeepalConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the charge schedule and steering wheel heating switches."""
    async_setup_control_entities(
        hass,
        entry,
        async_add_entities,
        lambda coordinator, vehicle: [
            DeepalChargeScheduleSwitch(coordinator, vehicle),
            DeepalSteeringWheelHeatSwitch(coordinator, vehicle),
        ],
    )


class DeepalChargeScheduleSwitch(DeepalEntity, SwitchEntity):
    """Enable or disable the charging schedule."""

    _attr_icon = "mdi:calendar-clock"

    def __init__(
        self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any
    ) -> None:
        """Initialize the charge schedule switch."""
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_charge_schedule"
        self._attr_name = f"{vehicle.series_name} Charge Schedule"

    @property
    def is_on(self) -> bool | None:
        """Return True when the schedule is enabled."""
        cond = self.condition
        return cond.battery.charge_schedule_enabled if cond else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the schedule."""
        await self._async_update(enabled=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the schedule."""
        await self._async_update(enabled=False)

    async def _async_update(self, *, enabled: bool) -> None:
        cond = self.condition
        if not cond or not cond.battery.charge_plan_id:
            raise HomeAssistantError("Deepal charge schedule plan is not available")
        await self.async_send_command(
            lambda: self.client.control_charge_schedule(
                self._car_id,
                cond.battery.charge_plan_id,
                cond.battery.charge_schedule_start or "0000",
                cond.battery.charge_schedule_end or "0000",
                enabled,
                cond.battery.charge_plan_type or 1,
                cond.battery.charge_plan_time_format or 1,
                cond.battery.charge_plan_time_zone or "GMT+08:00",
            ),
            optimistic_update=lambda new: _set_schedule_enabled(new, enabled),
        )


class DeepalSteeringWheelHeatSwitch(DeepalEntity, SwitchEntity):
    """Turn the steering wheel heating on or off."""

    _attr_icon = "mdi:steering"

    def __init__(
        self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any
    ) -> None:
        """Initialize the steering wheel heating switch."""
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_steering_wheel_heating"
        self._attr_name = f"{vehicle.series_name} Steering Wheel Heating"

    @property
    def is_on(self) -> bool | None:
        """Return True when the steering wheel heating is on."""
        cond = self.condition
        return cond.climate.steering_wheel_heater_on if cond else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the steering wheel heating on."""
        await self._async_update(enabled=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the steering wheel heating off."""
        await self._async_update(enabled=False)

    async def _async_update(self, *, enabled: bool) -> None:
        await self.async_send_command(
            lambda: self.client.control_steering_wheel_heat(
                self._car_id, enabled
            ),
            optimistic_update=lambda cond: _set_steering_wheel_heat(cond, enabled),
        )
