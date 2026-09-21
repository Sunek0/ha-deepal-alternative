"""Cover platform (windows and trunk) for the Changan Deepal integration."""

from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import DeepalDataUpdateCoordinator
from .entity import DeepalEntity, async_setup_control_entities
from .runtime_data import DeepalConfigEntry


def _set_windows(condition: Any, is_open: bool) -> Any:
    windows = condition.windows
    windows.front_left_open = is_open
    windows.front_right_open = is_open
    windows.rear_left_open = is_open
    windows.rear_right_open = is_open
    return condition


def _set_trunk(condition: Any, is_open: bool) -> Any:
    condition.doors.trunk_open = is_open
    return condition


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeepalConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the window and trunk covers."""
    async_setup_control_entities(
        hass,
        entry,
        async_add_entities,
        lambda coordinator, vehicle: [
            DeepalWindowsCover(coordinator, vehicle),
            DeepalTrunkCover(coordinator, vehicle),
        ],
    )


class DeepalWindowsCover(DeepalEntity, CoverEntity):
    """All-window cover."""

    _attr_device_class = CoverDeviceClass.WINDOW
    _attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

    def __init__(
        self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any
    ) -> None:
        """Initialize the window cover."""
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_windows_cover"
        self._attr_translation_key = "windows"

    @property
    def is_closed(self) -> bool | None:
        """Return True when every window is closed."""
        cond = self.condition
        if not cond:
            return None
        windows = cond.windows
        return not (
            windows.front_left_open
            or windows.front_right_open
            or windows.rear_left_open
            or windows.rear_right_open
        )

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the windows."""
        await self.async_send_command(
            lambda: self.client.control_windows(self._car_id, True),
            is_done=lambda: self.is_closed is False,
            optimistic_update=lambda cond: _set_windows(cond, True),
        )

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the windows."""
        await self.async_send_command(
            lambda: self.client.control_windows(self._car_id, False),
            is_done=lambda: self.is_closed is True,
            optimistic_update=lambda cond: _set_windows(cond, False),
        )


class DeepalTrunkCover(DeepalEntity, CoverEntity):
    """Trunk cover."""

    _attr_device_class = CoverDeviceClass.GARAGE
    _attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

    def __init__(
        self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any
    ) -> None:
        """Initialize the trunk cover."""
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_boot_cover"
        self._attr_translation_key = "trunk"

    @property
    def is_closed(self) -> bool | None:
        """Return True when the trunk is closed."""
        cond = self.condition
        return None if cond is None else not cond.doors.trunk_open

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the trunk."""
        await self.async_send_command(
            lambda: self.client.control_trunk(self._car_id, True),
            is_done=lambda: self.is_closed is False,
            optimistic_update=lambda cond: _set_trunk(cond, True),
        )

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the trunk."""
        await self.async_send_command(
            lambda: self.client.control_trunk(self._car_id, False),
            is_done=lambda: self.is_closed is True,
            optimistic_update=lambda cond: _set_trunk(cond, False),
        )
