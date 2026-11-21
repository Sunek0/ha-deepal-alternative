"""Switch platform (charge schedule) for the Changan Deepal integration."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .charge_schedule import (
    async_set_charge_schedule,
    ha_gmt_offset,
    plan_set_outside_home_assistant,
)
from .coordinator import DeepalDataUpdateCoordinator
from .entity import (
    DeepalEntity,
    async_setup_control_entities,
    remove_entity_registry_entries,
)
from .runtime_data import DeepalConfigEntry
from .vehicle_model import is_s05_phev, supports_charge_schedule

# The coordinator serializes state-sharing commands per vehicle
PARALLEL_UPDATES = 0

#: Switch keys that only exist on models with the charge-schedule option.
CHARGE_SCHEDULE_SWITCH_KEYS = frozenset({"charge_schedule", "charge_schedule_full"})


def _set_steering_wheel_heat(condition: Any, enabled: bool) -> Any:
    condition.climate.steering_wheel_heater_on = enabled
    return condition


def _plan_attributes(vehicle: Any, cond: Any) -> dict[str, Any] | None:
    """Say who set the active S05 PHEV plan and whether HA can change it.

    ``set_by`` is ``app_or_car`` for a plan saved in the app or on the car
    (Home Assistant cannot switch it off or replace it), ``home_assistant``
    for a plan Home Assistant added, and ``none`` when no plan is active.
    """
    if not is_s05_phev(vehicle) or cond is None:
        return None
    plans = [p for p in (cond.battery.charge_plans or []) if isinstance(p, dict)]
    if plan_set_outside_home_assistant(vehicle, plans):
        set_by = "app_or_car"
    elif plans and str(plans[0].get("isValid")) == "1":
        set_by = "home_assistant"
    else:
        set_by = "none"
    return {"set_by": set_by, "controllable": set_by != "app_or_car"}


def build_switches(
    coordinator: DeepalDataUpdateCoordinator, vehicle: Any
) -> list[SwitchEntity]:
    """Build the switches whose model supports them."""
    entities: list[SwitchEntity] = []
    if supports_charge_schedule(vehicle):
        entities.append(DeepalChargeScheduleSwitch(coordinator, vehicle))
        if is_s05_phev(vehicle):
            entities.append(DeepalChargeScheduleFullSwitch(coordinator, vehicle))
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
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Who set the active plan and whether Home Assistant can change it."""
        return _plan_attributes(self.vehicle, self.condition)

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
        if (
            is_s05_phev(self.vehicle)
            and cond is not None
            and cond.battery.charge_schedule_start is not None
            and cond.battery.charge_schedule_end is None
        ):
            # The PHEV plan has a start and no end: "continue to full charge".
            end = None
        await async_set_charge_schedule(
            self.coordinator,
            self.vehicle,
            start,
            end,
            enabled,
            ha_gmt_offset(self.hass),
            wait_for_plan=not enabled,
            toggle_only=True,
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


class DeepalChargeScheduleFullSwitch(DeepalEntity, SwitchEntity):
    """Charge from the start time until the battery is full (S05 PHEV).

    The app and the car store this as a plan without an end time; the end time
    entity cannot be cleared, so this switch is the way to set it from Home
    Assistant. On adds an active "continue to full charge" plan from the start
    time; off replaces an active one with a plan that ends at 08:00 (or the end
    time entity can be set instead).
    """

    def __init__(
        self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any
    ) -> None:
        """Initialize the charge-to-full switch."""
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_charge_schedule_full"
        self._attr_translation_key = "charge_schedule_full"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Who set the active plan and whether Home Assistant can change it."""
        return _plan_attributes(self.vehicle, self.condition)

    @property
    def is_on(self) -> bool | None:
        """Return True when the plan has a start and no end."""
        cond = self.condition
        if cond is None or cond.battery.charge_schedule_start is None:
            return None
        return cond.battery.charge_schedule_end is None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Add an active plan that charges until full."""
        cond = self.condition
        start = (cond.battery.charge_schedule_start if cond else None) or "0000"
        await async_set_charge_schedule(
            self.coordinator,
            self.vehicle,
            start,
            None,
            True,
            ha_gmt_offset(self.hass),
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Give the plan an end time again (08:00) while keeping its state."""
        cond = self.condition
        start = (cond.battery.charge_schedule_start if cond else None) or "0000"
        await async_set_charge_schedule(
            self.coordinator,
            self.vehicle,
            start,
            "0800",
            None,
            ha_gmt_offset(self.hass),
        )
