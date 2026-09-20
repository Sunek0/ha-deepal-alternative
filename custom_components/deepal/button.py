"""Button platform for the Changan Deepal integration."""

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import DeepalDataUpdateCoordinator
from .deepal import DeepalError, FLASH_HONK_BEE, FLASH_HONK_FLASH
from .entity import DeepalEntity, async_setup_control_entities
from .runtime_data import DeepalConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeepalConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the control buttons."""
    async_setup_control_entities(
        hass,
        entry,
        async_add_entities,
        lambda coordinator, vehicle: [
            DeepalRefreshButton(coordinator, vehicle),
            DeepalFlashLightsButton(coordinator, vehicle),
            DeepalHonkHornButton(coordinator, vehicle),
        ],
    )


class DeepalRefreshButton(DeepalEntity, ButtonEntity):
    """Ask the vehicle to report fresh condition data."""

    _attr_icon = "mdi:refresh"

    def __init__(
        self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any
    ) -> None:
        """Initialize the refresh button."""
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_refresh"
        self._attr_name = f"{vehicle.series_name} Refresh Vehicle Data"

    async def async_press(self) -> None:
        """Request fresh data and refresh the coordinator."""
        try:
            await self.client.control_condition_inquiry(self._car_id)
        except DeepalError as err:
            raise HomeAssistantError(f"Deepal refresh command failed: {err}") from err
        await self.coordinator.async_request_refresh()


class DeepalFlashLightsButton(DeepalEntity, ButtonEntity):
    """Flash the vehicle lights."""

    _attr_icon = "mdi:car-light-high"

    def __init__(
        self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any
    ) -> None:
        """Initialize the flash lights button."""
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_flash_lights"
        self._attr_name = f"{vehicle.series_name} Flash Lights"

    async def async_press(self) -> None:
        """Flash the lights."""
        await self.async_send_command(
            lambda: self.client.control_flashing_honking(
                self._car_id, FLASH_HONK_FLASH
            )
        )


class DeepalHonkHornButton(DeepalEntity, ButtonEntity):
    """Sound the vehicle horn."""

    _attr_icon = "mdi:bullhorn"

    def __init__(
        self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any
    ) -> None:
        """Initialize the horn button."""
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_honk_horn"
        self._attr_name = f"{vehicle.series_name} Honk Horn"

    async def async_press(self) -> None:
        """Sound the horn."""
        await self.async_send_command(
            lambda: self.client.control_flashing_honking(
                self._car_id, FLASH_HONK_BEE
            )
        )
