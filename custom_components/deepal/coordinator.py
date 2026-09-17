"""DataUpdateCoordinator for Changan Deepal integration."""

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .deepal import (
    DeepalAuthError,
    DeepalClient,
    DeepalError,
    DeepalIntlClient,
    Vehicle,
    VehicleCondition,
)
from .const import (
    DOMAIN,
    DEFAULT_SCAN_INTERVAL,
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_CAC_TOKEN,
)

_LOGGER = logging.getLogger(__name__)


class DeepalDataUpdateCoordinator(DataUpdateCoordinator[dict[str, VehicleCondition]]):
    """Class to manage fetching Changan Deepal data from API."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: DeepalClient | DeepalIntlClient,
        update_interval: timedelta = timedelta(seconds=DEFAULT_SCAN_INTERVAL),
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self.entry = entry
        self.client = client
        self.vehicles: list[Vehicle] = []

    async def _async_fetch(self) -> dict[str, VehicleCondition]:
        """Fetch vehicles and their conditions."""
        if not self.vehicles:
            self.vehicles = await self.client.get_vehicles()

        data: dict[str, VehicleCondition] = {}
        for vehicle in self.vehicles:
            condition = await self.client.get_vehicle_condition(vehicle.car_id)
            data[vehicle.car_id] = condition

        return data

    async def _async_refresh_tokens(self) -> bool:
        """Refresh the international session and persist the new tokens."""
        refresh = getattr(self.client, "refresh_tokens", None)
        if refresh is None or not getattr(self.client, "refresh_token", None):
            return False

        try:
            token = await refresh()
        except DeepalError as err:
            _LOGGER.error("Deepal token refresh failed: %s", err)
            return False

        self.hass.config_entries.async_update_entry(
            self.entry,
            data={
                **self.entry.data,
                CONF_ACCESS_TOKEN: token.access_token,
                CONF_REFRESH_TOKEN: token.refresh_token
                or self.entry.data.get(CONF_REFRESH_TOKEN, ""),
                CONF_CAC_TOKEN: token.cac_token or self.entry.data.get(CONF_CAC_TOKEN, ""),
            },
        )
        return True

    async def _async_update_data(self) -> dict[str, VehicleCondition]:
        """Fetch data from Changan Deepal API."""
        try:
            return await self._async_fetch()
        except DeepalAuthError as err:
            _LOGGER.warning("Deepal authentication failed, attempting token refresh")
            if await self._async_refresh_tokens():
                try:
                    return await self._async_fetch()
                except DeepalError as retry_err:
                    raise ConfigEntryAuthFailed("Authentication token expired") from retry_err
            raise ConfigEntryAuthFailed("Authentication token expired") from err
        except DeepalError as err:
            _LOGGER.error("Error communicating with Deepal API: %s", err)
            raise UpdateFailed(f"Error fetching Deepal data: {err}") from err
