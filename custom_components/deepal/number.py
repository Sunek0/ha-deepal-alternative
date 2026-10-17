"""Number platform (charge limit) for the Changan Deepal integration."""

from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import PERCENTAGE_UNIT
from .coordinator import DeepalDataUpdateCoordinator
from .entity import DeepalEntity, async_setup_control_entities
from .runtime_data import DeepalConfigEntry
from .vehicle_model import is_s05

# The coordinator serializes state-sharing commands per vehicle
PARALLEL_UPDATES = 0


SEAT_LABELS = {"front_left": "Front Left", "front_right": "Front Right"}
SEAT_FUNCTIONS = {
    "heating": ("control_seats_heat", "heating_level"),
    "ventilation": ("control_seats_wind", "ventilation_level"),
}


def supports_charge_limit(vehicle: Any, capabilities: Any) -> bool:
    """Return whether the vehicle supports setting the AC charge limit.

    Capability-first: a vehicle whose function configuration reports a
    charge-limit code gets the control even when its model is otherwise
    excluded (the S05 PHEV). The S05 keeps losing it when the capabilities
    are unavailable or report no charge-limit code, because the signed
    charge_max command is accepted without changing the limit on that model
    (verified on the S05 EV). Every other model keeps the control, so a
    missing capability list never removes it.
    """
    if capabilities is not None and getattr(capabilities, "has_charge_limit", False):
        return True
    return not is_s05(vehicle)


def build_control_numbers(
    coordinator: DeepalDataUpdateCoordinator, vehicle: Any
) -> list[Any]:
    """Build the charge limit and seat level numbers for one vehicle."""
    entities: list[Any] = []
    capabilities = coordinator.vehicle_capabilities(vehicle.car_id)
    if supports_charge_limit(vehicle, capabilities):
        entities.append(DeepalChargeLimitNumber(coordinator, vehicle))
    for seat in SEAT_LABELS:
        for function in SEAT_FUNCTIONS:
            entities.append(DeepalSeatLevelNumber(coordinator, vehicle, seat, function))
    return entities


def _set_charge_limit(condition: Any, percentage: int) -> Any:
    condition.battery.charge_limit_percent = percentage
    return condition


def _set_seat_level(condition: Any, seat: str, field: str, level: int) -> Any:
    setattr(getattr(condition.seats, seat), field, level)
    return condition


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeepalConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the charge limit and seat level numbers."""
    async_setup_control_entities(hass, entry, async_add_entities, build_control_numbers)


class DeepalChargeLimitNumber(DeepalEntity, NumberEntity):
    """Maximum battery state of charge for AC charging."""

    _attr_native_min_value = 60
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE_UNIT
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any
    ) -> None:
        """Initialize the charge limit number."""
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_charge_limit"
        self._attr_translation_key = "charge_limit"

    @property
    def native_value(self) -> int | None:
        """Return the configured charge limit."""
        cond = self.condition
        return cond.battery.charge_limit_percent if cond else None

    async def async_set_native_value(self, value: float) -> None:
        """Set the charge limit."""
        await self.async_send_command(
            lambda: self.client.control_charge_limit(self._car_id, int(value)),
            optimistic_update=lambda cond: _set_charge_limit(cond, int(value)),
        )


class DeepalSeatLevelNumber(DeepalEntity, NumberEntity):
    """Front seat heating or ventilation level (0 = off, 1-3 = level)."""

    _attr_native_min_value = 0
    _attr_native_max_value = 3
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        coordinator: DeepalDataUpdateCoordinator,
        vehicle: Any,
        seat: str,
        function: str,
    ) -> None:
        """Initialize the seat level number."""
        super().__init__(coordinator, vehicle)
        self._seat = seat
        self._function = function
        self._field = SEAT_FUNCTIONS[function][1]
        self._attr_unique_id = (
            f"deepal_{vehicle.car_id}_seat_{seat}_{function}_control"
        )
        self._attr_translation_key = f"seat_{function}_level_{seat}"

    @property
    def native_value(self) -> int | None:
        """Return the seat heating or ventilation level.

        An unknown or out-of-range level is exposed as unknown instead of a
        number the slider cannot represent.
        """
        cond = self.condition
        if not cond:
            return None
        level = getattr(getattr(cond.seats, self._seat), self._field)
        if level is None or not 0 <= level <= 3:
            return None
        return level

    async def async_set_native_value(self, value: float) -> None:
        """Set the seat level (0 turns the function off)."""
        level = max(0, min(3, int(value)))
        switch = 1 if level > 0 else 0
        level_arg = level if level > 0 else None
        if self._seat == "front_left":
            kwargs: dict[str, int | None] = {
                "master_switch": switch,
                "master_level": level_arg,
            }
        else:
            kwargs = {"copilot_switch": switch, "copilot_level": level_arg}
        method = (
            self.client.control_seats_heat
            if self._function == "heating"
            else self.client.control_seats_wind
        )
        await self.async_send_command(
            lambda: method(self._car_id, **kwargs),
            optimistic_update=lambda cond: _set_seat_level(
                cond, self._seat, self._field, level
            ),
        )
