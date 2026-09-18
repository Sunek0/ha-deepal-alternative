"""Cover platform (windows and boot) for the Changan Deepal integration."""

from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import DeepalDataUpdateCoordinator
from .entity import DeepalEntity, async_setup_control_entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the window and boot covers."""
    async_setup_control_entities(
        hass,
        entry,
        async_add_entities,
        lambda coordinator, vehicle: [
            DeepalWindowsCover(coordinator, vehicle),
            DeepalBootCover(coordinator, vehicle),
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
        self._attr_name = f"{vehicle.series_name} Windows"

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
        )

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the windows."""
        await self.async_send_command(
            lambda: self.client.control_windows(self._car_id, False),
            is_done=lambda: self.is_closed is True,
        )


class DeepalBootCover(DeepalEntity, CoverEntity):
    """Boot/trunk cover."""

    _attr_device_class = CoverDeviceClass.DOOR
    _attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

    def __init__(
        self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any
    ) -> None:
        """Initialize the boot cover."""
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_boot_cover"
        self._attr_name = f"{vehicle.series_name} Boot"

    @property
    def is_closed(self) -> bool | None:
        """Return True when the boot is closed."""
        cond = self.condition
        return None if cond is None else not cond.doors.trunk_open

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the boot."""
        await self.async_send_command(
            lambda: self.client.control_trunk(self._car_id, True),
            is_done=lambda: self.is_closed is False,
        )

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the boot."""
        await self.async_send_command(
            lambda: self.client.control_trunk(self._car_id, False),
            is_done=lambda: self.is_closed is True,
        )
