"""Number platform (charge limit) for the Changan Deepal integration."""

from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfRatio
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import DeepalDataUpdateCoordinator
from .entity import DeepalEntity, async_setup_control_entities
from .runtime_data import DeepalConfigEntry


SEAT_LABELS = {"front_left": "Front Left", "front_right": "Front Right"}
SEAT_FUNCTIONS = {
    "heating": ("control_seats_heat", "heating_level", "mdi:car-seat-heater"),
    "ventilation": ("control_seats_wind", "ventilation_level", "mdi:car-seat-cooler"),
}


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

    def _build(coordinator: DeepalDataUpdateCoordinator, vehicle: Any) -> list[Any]:
        entities: list[Any] = [DeepalChargeLimitNumber(coordinator, vehicle)]
        for seat in SEAT_LABELS:
            for function in SEAT_FUNCTIONS:
                entities.append(
                    DeepalSeatLevelNumber(coordinator, vehicle, seat, function)
                )
        return entities

    async_setup_control_entities(hass, entry, async_add_entities, _build)


class DeepalChargeLimitNumber(DeepalEntity, NumberEntity):
    """Maximum battery state of charge for AC charging."""

    _attr_native_min_value = 60
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfRatio.PERCENTAGE
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:battery-heart"

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
        self._attr_icon = SEAT_FUNCTIONS[function][2]

    @property
    def native_value(self) -> int | None:
        """Return the seat heating or ventilation level."""
        cond = self.condition
        if not cond:
            return None
        return getattr(getattr(cond.seats, self._seat), self._field)

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
