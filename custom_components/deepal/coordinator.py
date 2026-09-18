"""DataUpdateCoordinator for Changan Deepal integration."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .deepal import (
    DeepalAPIError,
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

_PENDING_RESULT_CODES = (None, -100, 0, 1015)


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
        self._command_in_progress = False

    async def _async_fetch(self) -> dict[str, VehicleCondition]:
        """Fetch vehicles and their conditions."""
        if not self.vehicles:
            self.vehicles = await self.client.get_vehicles()

        data: dict[str, VehicleCondition] = {}
        for vehicle in self.vehicles:
            if self._uses_mqtt(vehicle):
                try:
                    condition = await self.client.s05_mqtt_condition(vehicle.car_id)
                except DeepalAPIError as err:
                    _LOGGER.warning(
                        "Deepal MQTT telemetry unavailable for %s (%s); using the "
                        "REST condition endpoint",
                        vehicle.car_id,
                        err,
                    )
                    condition = await self.client.get_vehicle_condition(vehicle.car_id)
            else:
                condition = await self.client.get_vehicle_condition(vehicle.car_id)
            data[vehicle.car_id] = condition

        return data

    def _uses_mqtt(self, vehicle: Vehicle) -> bool:
        """Return whether this vehicle should use the MQTT telemetry path.

        MQTT needs the account user id returned by login; without it (today,
        entries configured with pasted tokens) the REST condition is used so the
        integration keeps working until the entry is re-authenticated.
        """
        if not isinstance(self.client, DeepalIntlClient):
            return False
        if not self.client.is_mqtt_vehicle(vehicle):
            return False
        if not self.client.user_id:
            _LOGGER.warning(
                "Deepal vehicle %s is MQTT-backed but the entry has no user id; "
                "using the REST condition endpoint (stale data). Re-authenticate "
                "to enable MQTT telemetry.",
                vehicle.car_id,
            )
            return False
        return True

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

    async def async_execute_command(
        self,
        vehicle_id: str,
        send_command: Callable[[], Awaitable[str]],
        *,
        is_done: Callable[[], bool] | None = None,
        timeout: float = 30.0,
        interval: float = 2.0,
    ) -> None:
        """Send a remote command and poll until the vehicle reports new data."""
        if not isinstance(self.client, DeepalIntlClient):
            raise HomeAssistantError("Remote commands require the international platform")
        if self._command_in_progress:
            raise HomeAssistantError(
                "A Deepal command is already in progress; wait for the vehicle data to refresh"
            )

        self._command_in_progress = True
        try:
            current = (self.data or {}).get(vehicle_id)
            previous_last_updated = current.last_updated_timestamp if current else None

            command_id = await send_command()

            try:
                await self.client.control_condition_inquiry(vehicle_id)
            except DeepalError as err:
                _LOGGER.warning("Deepal condition inquiry failed: %s", err)

            await self._async_poll_command(
                vehicle_id,
                command_id,
                previous_last_updated,
                timeout,
                interval,
                is_done,
            )
        finally:
            self._command_in_progress = False

    def vehicle_uses_mqtt(self, car_id: str) -> bool:
        """Return whether a vehicle reports telemetry over MQTT."""
        if not isinstance(self.client, DeepalIntlClient):
            return False
        vehicle = next((item for item in self.vehicles if item.car_id == car_id), None)
        return bool(vehicle and self.client.is_mqtt_vehicle(vehicle))

    async def _async_poll_command(
        self,
        vehicle_id: str,
        command_id: str,
        previous_last_updated: int | None,
        timeout: float,
        interval: float,
        is_done: Callable[[], bool] | None = None,
    ) -> None:
        """Poll the command result and condition until the state changes or times out."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        while True:
            result = await self.client.control_result(vehicle_id, command_id)
            condition = await self.client.get_vehicle_condition(vehicle_id)

            data = dict(self.data or {})
            data[vehicle_id] = condition
            self.async_set_updated_data(data)

            result_code = result.get("resultCode")
            if result_code not in _PENDING_RESULT_CODES:
                raise HomeAssistantError(
                    f"Deepal command failed with result code {result_code}: "
                    f"{result.get('errorMsg')}"
                )

            condition_changed = (
                condition.last_updated_timestamp is not None
                and condition.last_updated_timestamp != previous_last_updated
            )
            state_done = is_done() if is_done is not None else True
            if condition_changed and state_done:
                return

            if loop.time() >= deadline:
                _LOGGER.warning(
                    "Deepal command %s timed out before the vehicle reported new data",
                    command_id,
                )
                return

            await asyncio.sleep(interval)
