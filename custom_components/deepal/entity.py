"""Shared entity helpers for the Changan Deepal integration."""

from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DEFAULT_MODEL,
    DOMAIN,
    MANUFACTURER,
)
from .coordinator import DeepalDataUpdateCoordinator
from .deepal import DeepalError, DeepalIntlClient
from .runtime_data import DeepalConfigEntry


class DeepalEntity(CoordinatorEntity[DeepalDataUpdateCoordinator]):
    """Base entity with device information and command helpers."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.vehicle = vehicle
        self._car_id = vehicle.car_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.vehicle.car_id)},
            name=self.vehicle.series_name or DEFAULT_MODEL,
            manufacturer=MANUFACTURER,
            model=self.vehicle.series_name or DEFAULT_MODEL,
        )

    @property
    def condition(self):
        """Return the vehicle condition from the coordinator."""
        return self.coordinator.data.get(self._car_id)

    @property
    def client(self) -> DeepalIntlClient:
        """Return the international client."""
        return self.coordinator.client

    async def async_send_command(
        self,
        send_command: Callable[[], Awaitable[str]],
        *,
        is_done: Callable[[], bool] | None = None,
        optimistic_update: Callable[[Any], Any] | None = None,
    ) -> None:
        """Send a signed command and wait for the vehicle to report the state."""
        try:
            await self.coordinator.async_execute_command(
                self._car_id,
                send_command,
                is_done=is_done,
                optimistic_update=optimistic_update,
            )
        except DeepalError as err:
            raise HomeAssistantError(f"Deepal command failed: {err}") from err


def async_setup_control_entities(
    hass: HomeAssistant,
    entry: DeepalConfigEntry,
    async_add_entities: AddEntitiesCallback,
    build_entities: Callable[[Any, Any], list],
    *,
    requires_control_pin: bool = False,
) -> None:
    """Set up control entities for international, command-capable vehicles.

    Platforms whose commands require an ``rcToken`` pass ``requires_control_pin``
    so their entities are only created once the entry stores the control PIN.
    """
    coordinator: DeepalDataUpdateCoordinator = entry.runtime_data.coordinator
    client = coordinator.client
    if not isinstance(client, DeepalIntlClient) or not client.private_key_pem:
        return
    if requires_control_pin and not client.control_pin:
        return

    entities = []
    for vehicle in coordinator.vehicles:
        entities.extend(build_entities(coordinator, vehicle))

    if entities:
        async_add_entities(entities)
