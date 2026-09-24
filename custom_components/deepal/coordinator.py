"""DataUpdateCoordinator for Changan Deepal integration."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .deepal import (
    CommandResult,
    CommandResultStatus,
    DeepalAPIError,
    DeepalAuthError,
    DeepalClient,
    DeepalError,
    DeepalIntlClient,
    Vehicle,
    VehicleCapabilities,
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

_COMMAND_RESULT_INTERVAL = 1.0
_COMMAND_TIMEOUT = 60.0
_COMMAND_LOCK_TIMEOUT = 30.0
_STATELESS_COMMAND_TIMEOUT = 15.0
_OPTIMISTIC_CONFIRM_TIMEOUT = 15.0
_CONDITION_FETCH_INTERVAL = 5.0
_OPTIMISTIC_HOLD_SECONDS = 120.0
_CA_TOKEN_ERROR_CODES = {"APIGW_-1_7_01_004", "APIGW_1_7_02_001"}


def _command_failure_message(result: CommandResult) -> str:
    """Build the error message for a failed command result."""
    message = (
        f"Deepal command failed with result code {result.code}: "
        f"{result.error_message}"
    )
    if "TBOX_" in (result.error_message or ""):
        message += (
            " (the vehicle did not accept the command; it may be "
            "offline or busy, try again when it is awake)"
        )
    return message


def _diff_paths(before: Any, after: Any, prefix: str = "") -> dict[str, Any]:
    """Return the dotted paths whose value differs between two model dumps."""
    changes: dict[str, Any] = {}
    if isinstance(after, dict):
        before_dict = before if isinstance(before, dict) else {}
        for key, value in after.items():
            path = f"{prefix}.{key}" if prefix else key
            changes.update(_diff_paths(before_dict.get(key), value, path))
    elif before != after:
        changes[prefix] = after
    return changes


def _path_get(obj: Any, path: str) -> Any:
    for part in path.split("."):
        obj = getattr(obj, part)
    return obj


def _path_set(obj: Any, path: str, value: Any) -> None:
    parts = path.split(".")
    for part in parts[:-1]:
        obj = getattr(obj, part)
    setattr(obj, parts[-1], value)


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
        self._command_locks: dict[str, asyncio.Lock] = {}
        self._optimistic_holds: dict[str, dict[str, Any]] = {}
        self._background_tasks: set[asyncio.Task] = set()
        self._capabilities: dict[str, VehicleCapabilities | None] = {}

    async def _async_fetch(self) -> dict[str, VehicleCondition]:
        """Fetch vehicles and their conditions."""
        if not self.vehicles:
            self.vehicles = await self.client.get_vehicles()

        data: dict[str, VehicleCondition] = {}
        for vehicle in self.vehicles:
            await self._async_maybe_fetch_capabilities(vehicle)
            condition = await self._async_fetch_condition(vehicle.car_id)
            condition = await self._overlay_app_comfort(vehicle, condition)
            data[vehicle.car_id] = self._apply_optimistic_hold(
                vehicle.car_id, condition
            )

        return data

    async def _async_maybe_fetch_capabilities(self, vehicle: Vehicle) -> None:
        """Fetch the vehicle function configuration once per entry setup.

        The capability list changes with the vehicle, not with telemetry, so it
        is fetched once and cached until the entry reloads; failures are cached
        as well because the endpoint is optional and must never affect polling.
        """
        if vehicle.car_id in self._capabilities:
            return
        if not isinstance(self.client, DeepalIntlClient):
            return
        try:
            capabilities = await self.client.get_vehicle_capabilities(
                vehicle.car_id, vin=vehicle.vin
            )
        except DeepalError as err:
            _LOGGER.debug(
                "Deepal capabilities fetch failed for %s: %s", vehicle.car_id, err
            )
            capabilities = None
        self._capabilities[vehicle.car_id] = capabilities

    def vehicle_capabilities(self, car_id: str) -> VehicleCapabilities | None:
        """Return the cached capabilities of a vehicle, if they were fetched."""
        return self._capabilities.get(car_id)

    async def _overlay_app_comfort(
        self, vehicle: Vehicle, condition: VehicleCondition
    ) -> VehicleCondition:
        """Overlay the app's seat and steering state onto an MQTT snapshot.

        The S05 seat modules report sentinel values over MQTT while they are
        asleep, and the MQTT ``steeringWheelHeating`` field does not follow the
        switch the app shows. The server condition endpoint returns the same
        report already normalized the way the app displays it.
        """
        if not self._uses_mqtt(vehicle):
            return condition
        try:
            app_condition = await self.client.get_vehicle_condition(
                vehicle.car_id, vin=vehicle.vin
            )
        except DeepalError as err:
            _LOGGER.debug(
                "Deepal app condition overlay failed for %s: %s", vehicle.car_id, err
            )
            return condition
        mqtt_ts = condition.last_updated_timestamp
        app_ts = app_condition.last_updated_timestamp
        if mqtt_ts is not None and app_ts is not None and app_ts < mqtt_ts:
            return condition
        raw = app_condition.raw_data or {}
        if raw.get("seat"):
            condition.seats = app_condition.seats
        if (raw.get("vehicleStatus") or {}).get("steeringWheelHeater") is not None:
            condition.climate.steering_wheel_heater_on = (
                app_condition.climate.steering_wheel_heater_on
            )
            condition.climate.steering_wheel_heater_level = (
                app_condition.climate.steering_wheel_heater_level
            )
        if raw.get("fuel") and all(
            value is None for value in condition.fuel.model_dump().values()
        ):
            condition.fuel = app_condition.fuel
        return condition

    def _register_optimistic_hold(
        self, vehicle_id: str, before: dict[str, Any], after: dict[str, Any]
    ) -> None:
        """Remember the fields a command changed so reports cannot revert them."""
        changes = _diff_paths(before, after)
        if changes:
            self._optimistic_holds[vehicle_id] = {
                "expires": time.monotonic() + _OPTIMISTIC_HOLD_SECONDS,
                "values": changes,
            }

    def _apply_optimistic_hold(
        self, vehicle_id: str, condition: VehicleCondition
    ) -> VehicleCondition:
        """Keep the optimistic values until the vehicle confirms them.

        The car applies commands with a delay (and the account is rate limited),
        so reports generated before the command took effect would otherwise
        revert the entity to the previous value.
        """
        hold = self._optimistic_holds.get(vehicle_id)
        if hold is None:
            return condition
        if time.monotonic() >= hold["expires"]:
            self._optimistic_holds.pop(vehicle_id, None)
            return condition
        remaining: dict[str, Any] = {}
        for path, value in hold["values"].items():
            try:
                if _path_get(condition, path) == value:
                    continue
                _path_set(condition, path, value)
            except AttributeError:
                continue
            remaining[path] = value
        if remaining:
            hold["values"] = remaining
        else:
            self._optimistic_holds.pop(vehicle_id, None)
        return condition

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
        return await self._async_refresh_tokens(force=True)

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

    @staticmethod
    def _condition_is_fresh(
        condition: VehicleCondition, current: VehicleCondition | None
    ) -> bool:
        """Return whether a fetched condition may replace the current state.

        MQTT snapshots can be stale (the car reports only when it is awake), so
        a condition whose report timestamp did not advance must not overwrite
        the optimistic state applied by a command.
        """
        if current is None:
            return True
        if condition.last_updated_timestamp is None:
            return True
        if current.last_updated_timestamp is None:
            return True
        return condition.last_updated_timestamp > current.last_updated_timestamp

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

    async def _async_refresh_tokens(self, force: bool = False) -> bool:
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
            token = await refresh(force=force)
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

    async def _async_with_session_retry(
        self, action: Callable[[], Awaitable[Any]]
    ) -> Any:
        """Run an action, refreshing the session once when it fails on auth.

        Interactive commands (climate, seats, locks...) are not retried by the
        periodic update, so an expired session used to surface the gateway
        kick-out error until the next poll. Mirrors the update path: refresh
        with the stored refresh token, persist the new tokens and retry the
        failed call once. Re-raises the original error when the session cannot
        be refreshed.
        """
        try:
            return await action()
        except DeepalAuthError:
            if not await self._async_refresh_tokens(force=True):
                raise
            return await action()

    async def async_condition_inquiry(self, vehicle_id: str) -> None:
        """Ask the vehicle for fresh data, recovering an expired session."""
        if not isinstance(self.client, DeepalIntlClient):
            raise HomeAssistantError("Remote commands require the international platform")
        await self._async_with_session_retry(
            lambda: self.client.control_condition_inquiry(vehicle_id)
        )

    def _schedule_condition_inquiry(self, vehicle_id: str) -> None:
        """Nudge the vehicle for fresh data without delaying the command.

        The request forces the car to report, but awaiting it (up to the 15 s
        HTTP timeout) would delay the result polling on a busy vehicle. It is
        best-effort, so it runs as a tracked background task.
        """
        task = asyncio.create_task(self._async_nudge_condition(vehicle_id))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _async_nudge_condition(self, vehicle_id: str) -> None:
        """Run the best-effort condition inquiry and never raise."""
        try:
            await self._async_with_session_retry(
                lambda: self.client.control_condition_inquiry(vehicle_id)
            )
        except DeepalError as err:
            _LOGGER.warning("Deepal condition inquiry failed: %s", err)
        except Exception:  # noqa: BLE001 - background task must not raise
            _LOGGER.exception("Deepal condition inquiry failed unexpectedly")

    async def _async_update_data(self) -> dict[str, VehicleCondition]:
        """Fetch data from Changan Deepal API."""
        await self._async_maybe_refresh_tokens()
        try:
            return await self._async_fetch()
        except DeepalAuthError as err:
            _LOGGER.warning("Deepal authentication failed, attempting token refresh")
            if await self._async_refresh_tokens(force=True):
                try:
                    return await self._async_fetch()
                except DeepalError as retry_err:
                    raise ConfigEntryAuthFailed("Authentication token expired") from retry_err
            raise ConfigEntryAuthFailed("Authentication token expired") from err
        except DeepalError as err:
            _LOGGER.error("Error communicating with Deepal API: %s", err)
            raise UpdateFailed(f"Error fetching Deepal data: {err}") from err

    def _vehicle_command_lock(self, vehicle_id: str) -> asyncio.Lock:
        """Return the per-vehicle command lock, creating it on first use."""
        lock = self._command_locks.get(vehicle_id)
        if lock is None:
            lock = asyncio.Lock()
            self._command_locks[vehicle_id] = lock
        return lock

    async def async_execute_command(
        self,
        vehicle_id: str,
        send_command: Callable[[], Awaitable[str]],
        *,
        is_done: Callable[[], bool] | None = None,
        optimistic_update: Callable[[VehicleCondition], VehicleCondition] | None = None,
        serialize: bool | None = None,
        timeout: float = _COMMAND_TIMEOUT,
        interval: float = _COMMAND_RESULT_INTERVAL,
    ) -> None:
        """Send a remote command and poll until the vehicle reports new data.

        Commands that share the vehicle state (an optimistic update is given, or
        serialize=True) run one at a time per vehicle: a second one waits up to
        _COMMAND_LOCK_TIMEOUT seconds for its turn and then runs, instead of
        failing. Stateless commands (lights, horn) never wait, and commands for
        different vehicles are independent.
        """
        if not isinstance(self.client, DeepalIntlClient):
            raise HomeAssistantError("Remote commands require the international platform")

        if serialize is None:
            serialize = optimistic_update is not None

        if not serialize:
            await self._async_execute_command(
                vehicle_id,
                send_command,
                is_done=is_done,
                optimistic_update=optimistic_update,
                timeout=timeout,
                interval=interval,
            )
            return

        lock = self._vehicle_command_lock(vehicle_id)
        try:
            async with asyncio.timeout(_COMMAND_LOCK_TIMEOUT):
                await lock.acquire()
        except TimeoutError as error:
            raise HomeAssistantError(
                "Another Deepal command for this vehicle is taking too long; "
                "try again in a few seconds"
            ) from error

        try:
            await self._async_execute_command(
                vehicle_id,
                send_command,
                is_done=is_done,
                optimistic_update=optimistic_update,
                timeout=timeout,
                interval=interval,
            )
        finally:
            lock.release()

    async def _async_execute_command(
        self,
        vehicle_id: str,
        send_command: Callable[[], Awaitable[str]],
        *,
        is_done: Callable[[], bool] | None,
        optimistic_update: Callable[[VehicleCondition], VehicleCondition] | None,
        timeout: float,
        interval: float,
    ) -> None:
        """Run one command and poll until the vehicle reports new data."""
        current = (self.data or {}).get(vehicle_id)
        previous_last_updated = current.last_updated_timestamp if current else None

        command_id = await self._async_with_session_retry(send_command)

        if optimistic_update is None and is_done is None:
            await self._async_confirm_stateless_command(
                vehicle_id, command_id, timeout, interval
            )
            return

        applied_optimistic = False

        if optimistic_update is not None and current is not None:
            try:
                before = current.model_dump()
                updated = optimistic_update(current.model_copy(deep=True))
                data = dict(self.data or {})
                data[vehicle_id] = updated
                self.async_set_updated_data(data)
                applied_optimistic = True
                self._register_optimistic_hold(
                    vehicle_id, before, updated.model_dump()
                )
            except Exception:  # noqa: BLE001 - never break the command
                _LOGGER.exception("Deepal optimistic state update failed")

        self._schedule_condition_inquiry(vehicle_id)

        try:
            await self._async_poll_command(
                vehicle_id,
                command_id,
                previous_last_updated,
                timeout,
                interval,
                is_done,
                applied_optimistic=applied_optimistic,
            )
        except HomeAssistantError:
            if applied_optimistic and current is not None:
                self._restore_condition(vehicle_id, current)
            raise

    async def _async_confirm_stateless_command(
        self,
        vehicle_id: str,
        command_id: str,
        timeout: float,
        interval: float,
    ) -> None:
        """Confirm a stateless command without waiting for telemetry.

        Lights and horn do not change any telemetry field, so waiting for a
        fresh condition would hold the caller for the whole command timeout and
        surface the vehicle's late result for a command the gateway already
        accepted. Poll the result for a short window instead: a reported failure
        raises, acceptance or an inconclusive result returns.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + min(timeout, _STATELESS_COMMAND_TIMEOUT)

        while True:
            result = await self._async_with_session_retry(
                lambda: self.client.control_result_status(vehicle_id, command_id)
            )

            if result.status is CommandResultStatus.FAILED:
                raise HomeAssistantError(_command_failure_message(result))

            if result.status in (
                CommandResultStatus.SUCCESS,
                CommandResultStatus.ALREADY_DONE,
            ):
                return

            if loop.time() >= deadline:
                _LOGGER.debug(
                    "Deepal stateless command %s still pending after %.0fs; "
                    "returning",
                    command_id,
                    min(timeout, _STATELESS_COMMAND_TIMEOUT),
                )
                return

            await asyncio.sleep(interval)

    def _restore_condition(
        self, vehicle_id: str, condition: VehicleCondition
    ) -> None:
        """Undo an optimistic update after a command failure.

        The snapshot is only restored when no newer report has replaced it, so
        a fresh condition that arrived while polling is never discarded.
        """
        self._optimistic_holds.pop(vehicle_id, None)
        data = dict(self.data or {})
        current = data.get(vehicle_id)
        if current is None:
            return
        if (
            current.last_updated_timestamp is not None
            and condition.last_updated_timestamp is not None
            and current.last_updated_timestamp != condition.last_updated_timestamp
        ):
            return
        data[vehicle_id] = condition
        self.async_set_updated_data(data)

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
        applied_optimistic: bool = False,
    ) -> None:
        """Poll the command result while bounding the condition request rate.

        Optimistic commands already show their requested state and hold it for
        two minutes, so they stop after a short confirmation window instead of
        keeping the vehicle lock for the full command timeout; a slow gateway
        then no longer blocks every queued command.
        """
        loop = asyncio.get_running_loop()
        effective_timeout = (
            min(timeout, _OPTIMISTIC_CONFIRM_TIMEOUT)
            if applied_optimistic
            else timeout
        )
        deadline = loop.time() + effective_timeout
        next_condition_at = 0.0
        condition_changed = False

        while True:
            result = await self._async_with_session_retry(
                lambda: self.client.control_result_status(vehicle_id, command_id)
            )
            if result.status is CommandResultStatus.FAILED:
                raise HomeAssistantError(_command_failure_message(result))

            now = loop.time()
            if now >= next_condition_at:
                condition = await self._async_fetch_condition(vehicle_id)
                condition = self._apply_optimistic_hold(vehicle_id, condition)
                next_condition_at = now + condition_interval
                current = (self.data or {}).get(vehicle_id)
                if self._condition_is_fresh(condition, current):
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
                confirmed = (
                    is_done is not None or applied_optimistic or condition_changed
                )
                if state_done and confirmed:
                    return

            if loop.time() >= deadline:
                if applied_optimistic:
                    _LOGGER.debug(
                        "Deepal command %s is still pending after %.0fs; keeping "
                        "the optimistic state until the next poll",
                        command_id,
                        effective_timeout,
                    )
                else:
                    _LOGGER.warning(
                        "Deepal command %s timed out before the vehicle reported "
                        "new data",
                        command_id,
                    )
                return

            await asyncio.sleep(interval)
