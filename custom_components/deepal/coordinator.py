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
    CommandResultStatus,
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

_COMMAND_RESULT_INTERVAL = 0.5
_COMMAND_TIMEOUT = 60.0
_CONDITION_FETCH_INTERVAL = 2.0
_CA_TOKEN_ERROR_CODES = {"APIGW_-1_7_01_004", "APIGW_1_7_02_001"}


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
            data[vehicle.car_id] = await self._async_fetch_condition(vehicle.car_id)

        return data

    async def _async_fetch_condition(self, vehicle_id: str) -> VehicleCondition:
        """Fetch one condition through MQTT when available, REST otherwise."""
        vehicle = next(
            (item for item in self.vehicles if item.car_id == vehicle_id), None
        )
        if vehicle is not None and self._uses_mqtt(vehicle):
            try:
                condition = await self.client.s05_mqtt_condition(
                    vehicle_id, vin=vehicle.vin
                )
                return self._merge_condition(vehicle_id, condition)
            except DeepalAPIError as err:
                if getattr(err, "code", None) in _CA_TOKEN_ERROR_CODES and (
                    await self._async_refresh_session_for_mqtt(err)
                ):
                    try:
                        condition = await self.client.s05_mqtt_condition(
                            vehicle_id, vin=vehicle.vin
                        )
                        return self._merge_condition(vehicle_id, condition)
                    except DeepalAPIError as retry_err:
                        err = retry_err
                _LOGGER.warning(
                    "Deepal MQTT telemetry unavailable for %s (%s); using the "
                    "REST condition endpoint",
                    vehicle_id,
                    err,
                )
        condition = await self.client.get_vehicle_condition(
            vehicle_id, vin=vehicle.vin if vehicle is not None else None
        )
        return self._merge_condition(vehicle_id, condition)

    async def _async_refresh_session_for_mqtt(self, err: Exception) -> bool:
        """Refresh the session when the CA gateway rejects it.

        The coordinator only decides that a refresh is justified here; the SDK
        owns the per-client refresh window and single-flight behavior.
        """
        if not getattr(self.client, "refresh_token", None):
            return False
        _LOGGER.warning(
            "Deepal MQTT token rejected (%s); refreshing the session and retrying",
            err,
        )
        return await self._async_refresh_tokens()

    def _merge_condition(
        self, vehicle_id: str, condition: VehicleCondition
    ) -> VehicleCondition:
        """Keep the last known AC state when the vehicle omits it.

        S05 condition payloads have no ``hvac.acStatus``; overwriting the state
        with the parser default would turn the climate entity off after every
        poll, discarding optimistic command feedback.
        """
        previous = (self.data or {}).get(vehicle_id)
        if previous is not None and condition.climate.power_on is None:
            condition.climate.power_on = previous.climate.power_on
        return condition

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

    async def _async_maybe_refresh_tokens(self) -> None:
        """Refresh proactively when the token is close to expiry.

        The coordinator only decides that a refresh is justified; the SDK owns
        the refresh window and may return the current session unchanged.
        """
        client = self.client
        if not isinstance(client, DeepalIntlClient):
            return
        if not getattr(client, "refresh_token", None):
            return
        expires_soon = getattr(client, "access_token_expires_soon", None)
        if not callable(expires_soon) or not expires_soon():
            return
        _LOGGER.debug("Deepal access token close to expiry; refreshing proactively")
        await self._async_refresh_tokens()

    async def _async_refresh_tokens(self) -> bool:
        """Refresh the international session and persist the new tokens.

        The SDK decides whether a request actually happens (its throttle may
        return the current session); success is reported only when the access
        token changed, so callers never retry an unchanged session.
        """
        refresh = getattr(self.client, "refresh_tokens", None)
        if refresh is None or not getattr(self.client, "refresh_token", None):
            return False

        previous_access_token = getattr(self.client, "access_token", None)
        try:
            token = await refresh()
        except DeepalError as err:
            _LOGGER.error("Deepal token refresh failed: %s", err)
            return False

        if token.access_token == previous_access_token:
            _LOGGER.debug(
                "Deepal token refresh kept the current access token; treating it "
                "as not refreshed"
            )
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
        await self._async_maybe_refresh_tokens()
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
        optimistic_update: Callable[[VehicleCondition], VehicleCondition] | None = None,
        timeout: float = _COMMAND_TIMEOUT,
        interval: float = _COMMAND_RESULT_INTERVAL,
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

            if optimistic_update is not None and current is not None:
                try:
                    updated = optimistic_update(current.model_copy(deep=True))
                    data = dict(self.data or {})
                    data[vehicle_id] = updated
                    self.async_set_updated_data(data)
                except Exception:  # noqa: BLE001 - never break the command
                    _LOGGER.exception("Deepal optimistic state update failed")

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
        condition_interval: float = _CONDITION_FETCH_INTERVAL,
    ) -> None:
        """Poll the command result while bounding the condition request rate."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        next_condition_at = 0.0
        condition_changed = False

        while True:
            result = await self.client.control_result_status(vehicle_id, command_id)
            if result.status is CommandResultStatus.FAILED:
                raise HomeAssistantError(
                    f"Deepal command failed with result code {result.code}: "
                    f"{result.error_message}"
                )

            now = loop.time()
            if now >= next_condition_at:
                condition = await self._async_fetch_condition(vehicle_id)
                next_condition_at = now + condition_interval
                data = dict(self.data or {})
                data[vehicle_id] = condition
                self.async_set_updated_data(data)
                if (
                    condition.last_updated_timestamp is not None
                    and condition.last_updated_timestamp != previous_last_updated
                ):
                    condition_changed = True

            if result.status in (
                CommandResultStatus.SUCCESS,
                CommandResultStatus.ALREADY_DONE,
            ):
                state_done = is_done() if is_done is not None else True
                if state_done and (is_done is not None or condition_changed):
                    return

            if loop.time() >= deadline:
                _LOGGER.warning(
                    "Deepal command %s timed out before the vehicle reported new data",
                    command_id,
                )
                return

            await asyncio.sleep(interval)
