"""Number platform (charge limit) for the Changan Deepal integration."""

from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfRatio
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import DeepalDataUpdateCoordinator
from .entity import DeepalEntity, async_setup_control_entities
from .runtime_data import DeepalConfigEntry


def _set_charge_limit(condition: Any, percentage: int) -> Any:
    condition.battery.charge_limit_percent = percentage
    return condition


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeepalConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the charge limit number."""
    async_setup_control_entities(
        hass,
        entry,
        async_add_entities,
        lambda coordinator, vehicle: [DeepalChargeLimitNumber(coordinator, vehicle)],
    )


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
        self._attr_name = f"{vehicle.series_name} Charge Limit"

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
