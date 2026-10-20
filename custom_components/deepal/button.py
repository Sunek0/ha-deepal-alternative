"""Button platform for the Changan Deepal integration."""

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import DeepalDataUpdateCoordinator, WakeResult
from .deepal import DeepalError, FLASH_HONK_BEE, FLASH_HONK_FLASH, FLASH_HONK_FLASH_BEE
from .entity import DeepalEntity, async_setup_control_entities
from .runtime_data import DeepalConfigEntry

# The coordinator serializes state-sharing commands per vehicle
PARALLEL_UPDATES = 0


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
            DeepalFlashAndHonkButton(coordinator, vehicle),
        ],
    )


class DeepalRefreshButton(DeepalEntity, ButtonEntity):
    """Ask the vehicle to report fresh condition data."""


    def __init__(
        self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any
    ) -> None:
        """Initialize the refresh button."""
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_refresh"
        self._attr_translation_key = "refresh_vehicle_data"

    async def async_press(self) -> None:
        """Request fresh data and refresh the coordinator."""
        try:
            result = await self.coordinator.async_refresh_vehicle(self._car_id)
        except DeepalError as err:
            raise HomeAssistantError(
                f"Deepal refresh command failed: {err}",
                translation_domain=DOMAIN,
                translation_key="refresh_command_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        if result is WakeResult.FRESH:
            return
        if result is WakeResult.NO_REPORT:
            raise HomeAssistantError(
                "The vehicle did not report fresh data after the wake request; "
                "it may be offline or asleep",
                translation_domain=DOMAIN,
                translation_key="wake_no_fresh_report",
            )
        if result in (WakeResult.THROTTLED, WakeResult.FAILED):
            try:
                await self.coordinator.async_condition_inquiry(self._car_id)
            except DeepalError:
                pass
        await self.coordinator.async_request_refresh()


class DeepalFlashLightsButton(DeepalEntity, ButtonEntity):
    """Flash the vehicle lights."""


    def __init__(
        self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any
    ) -> None:
        """Initialize the flash lights button."""
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_flash_lights"
        self._attr_translation_key = "flash_lights"

    async def async_press(self) -> None:
        """Flash the lights."""
        await self.async_send_command(
            lambda: self.client.control_flashing_honking(
                self._car_id, FLASH_HONK_FLASH
            ),
            cooldown_key="flash_lights",
        )


class DeepalHonkHornButton(DeepalEntity, ButtonEntity):
    """Sound the vehicle horn."""


    def __init__(
        self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any
    ) -> None:
        """Initialize the horn button."""
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_honk_horn"
        self._attr_translation_key = "honk_horn"

    async def async_press(self) -> None:
        """Sound the horn."""
        await self.async_send_command(
            lambda: self.client.control_flashing_honking(
                self._car_id, FLASH_HONK_BEE
            ),
            cooldown_key="honk_horn",
        )


class DeepalFlashAndHonkButton(DeepalEntity, ButtonEntity):
    """Flash the lights and sound the horn together."""


    def __init__(
        self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any
    ) -> None:
        """Initialize the lights-and-horn button."""
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_flash_and_honk"
        self._attr_translation_key = "flash_and_honk"

    async def async_press(self) -> None:
        """Flash the lights and sound the horn together."""
        await self.async_send_command(
            lambda: self.client.control_flashing_honking(
                self._car_id, FLASH_HONK_FLASH_BEE
            ),
            cooldown_key="flash_and_honk",
        )
