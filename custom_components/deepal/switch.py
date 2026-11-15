"""Switch platform (charge schedule) for the Changan Deepal integration."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import DeepalDataUpdateCoordinator
from .entity import (
    DeepalEntity,
    async_setup_control_entities,
    remove_entity_registry_entries,
)
from .runtime_data import DeepalConfigEntry
from .vehicle_model import supports_charge_schedule

# The coordinator serializes state-sharing commands per vehicle
PARALLEL_UPDATES = 0

#: Switch keys that only exist on models with the charge-schedule option.
CHARGE_SCHEDULE_SWITCH_KEYS = frozenset({"charge_schedule"})


def _set_schedule_enabled(condition: Any, enabled: bool) -> Any:
    condition.battery.charge_schedule_enabled = enabled
    return condition


def _set_steering_wheel_heat(condition: Any, enabled: bool) -> Any:
    condition.climate.steering_wheel_heater_on = enabled
    return condition


def build_switches(
    coordinator: DeepalDataUpdateCoordinator, vehicle: Any
) -> list[SwitchEntity]:
    """Build the switches whose model supports them."""
    entities: list[SwitchEntity] = []
    if supports_charge_schedule(vehicle):
        entities.append(DeepalChargeScheduleSwitch(coordinator, vehicle))
    entities.append(DeepalSteeringWheelHeatSwitch(coordinator, vehicle))
    return entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeepalConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the charge schedule and steering wheel heating switches."""
    coordinator: DeepalDataUpdateCoordinator = entry.runtime_data.coordinator
    registry = er.async_get(hass)

    for vehicle in coordinator.vehicles:
        if not supports_charge_schedule(vehicle):
            remove_entity_registry_entries(
                registry, vehicle, "switch", CHARGE_SCHEDULE_SWITCH_KEYS
            )

    async_setup_control_entities(
        hass,
        entry,
        async_add_entities,
        build_switches,
    )


class DeepalChargeScheduleSwitch(DeepalEntity, SwitchEntity):
    """Enable or disable the charging schedule."""


    def __init__(
        self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any
    ) -> None:
        """Initialize the charge schedule switch."""
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_charge_schedule"
        self._attr_translation_key = "charge_schedule"

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
            raise HomeAssistantError(
                "Deepal charge schedule plan is not available",
                translation_domain=DOMAIN,
                translation_key="charge_schedule_unavailable",
            )
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


    def __init__(
        self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any
    ) -> None:
        """Initialize the steering wheel heating switch."""
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_steering_wheel_heating"
        self._attr_translation_key = "steering_wheel_heating"

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

