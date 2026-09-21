"""Lock platform (doors) for the Changan Deepal integration."""

from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import DeepalDataUpdateCoordinator
from .entity import DeepalEntity, async_setup_control_entities
from .runtime_data import DeepalConfigEntry


def _set_locked(condition: Any, locked: bool) -> Any:
    condition.doors.locked = locked
    return condition


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeepalConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the door lock entity."""
    async_setup_control_entities(
        hass,
        entry,
        async_add_entities,
        lambda coordinator, vehicle: [DeepalDoorsLock(coordinator, vehicle)],
        requires_control_pin=True,
    )


class DeepalDoorsLock(DeepalEntity, LockEntity):
    """Vehicle door lock."""

    _attr_icon = "mdi:car-door-lock"

    def __init__(
        self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any
    ) -> None:
        """Initialize the lock entity."""
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_doors_lock"
        self._attr_translation_key = "doors"

    @property
    def is_locked(self) -> bool | None:
        """Return True when the doors are locked."""
        cond = self.condition
        return cond.doors.locked if cond else None

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the doors."""
        await self.async_send_command(
            lambda: self.client.control_doors(self._car_id, False),
            is_done=lambda: self.is_locked is True,
            optimistic_update=lambda cond: _set_locked(cond, True),
        )

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the doors."""
        await self.async_send_command(
            lambda: self.client.control_doors(self._car_id, True),
            is_done=lambda: self.is_locked is False,
            optimistic_update=lambda cond: _set_locked(cond, False),
        )
