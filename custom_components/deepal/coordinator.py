"""DataUpdateCoordinator for Changan Deepal integration."""

import asyncio
import logging
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, NoReturn

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .charging import ChargingSessionManager, charging_flag
from .deepal import (
    CA_TOKEN_ERROR_CODES,
    CommandResult,
    CommandResultStatus,
    DeepalAPIError,
    DeepalAuthError,
    DeepalClient,
    DeepalCommandAuthError,
    DeepalCommandNotReady,
    DeepalConnectionError,
    DeepalError,
    DeepalIntlClient,
    DeepalRateLimitError,
    Vehicle,
    VehicleCapabilities,
    VehicleCondition,
)
from .snapshot import (
    SNAPSHOT_VERSION,
    conditions_from_snapshot,
    conditions_to_snapshot,
)
from .vehicle_model import uses_s05_charge_enum
from .deepal.mqtt import (
    REST_SUBSYSTEM_WARNING_KEYS,
    S05_CHARGE_GUN_KEYS,
    S05_DC_GUN_KEYS,
    is_s05_model,
    rest_subsystem_warnings,
)
from .const import (
    DOMAIN,
    DEFAULT_SCAN_INTERVAL,
    CONF_ACCESS_TOKEN,
    CONF_ENABLE_LOCATION,
    CONF_REFRESH_TOKEN,
    CONF_CAC_TOKEN,
    CONF_USER_ID,
    CONF_MQTT_LIVE_SESSION,
    DEFAULT_ENABLE_LOCATION,
    CORNER_POSITIONS,
    DEFAULT_MQTT_LIVE_SESSION,
    WAKE_BEFORE_COMMAND_TIMEOUT,
    WAKE_COOLDOWN,
    WAKE_REPORT_TIMEOUT,
    WAKE_STALE_AFTER,
)

_LOGGER = logging.getLogger(__name__)

_COMMAND_RESULT_INTERVAL = 1.0
_COMMAND_TIMEOUT = 60.0
_COMMAND_LOCK_TIMEOUT = 30.0
_STATELESS_COMMAND_TIMEOUT = 15.0
_OPTIMISTIC_CONFIRM_TIMEOUT = 15.0
_CONDITION_FETCH_INTERVAL = 5.0
_WAKE_POLL_INTERVAL = 5.0
_VEHICLE_REFRESH_INTERVAL = 600.0
_OPTIMISTIC_HOLD_SECONDS = 120.0
_CHARGING_READ_INTERVAL = 600.0
# A rejected CA/MQTT token triggers a forced session refresh, which bypasses the
# SDK's own INTL_REFRESH_THROTTLE_SECONDS window (1800 s) because the refresh no
# longer depends on the JWT expiry. This coarser per-entry cap keeps that
# trigger at one attempt per hour, as ha-intl-platform requires.
_CA_REFRESH_MIN_INTERVAL = 3600.0
# Home Assistant's statistics code treats a total_increasing drop below this
# fraction of the previous value as a meter reset; smaller drops are precision
# dips that trigger a warning and subtract the delta from the long-term sum.
_ODOMETER_RESET_RATIO = 0.9
# The last published condition is written at most this often (seconds).
_SNAPSHOT_SAVE_DELAY = 30.0
# Pushed conditions are coalesced per vehicle to absorb the car's delta bursts.
# REST-only fields are refreshed by the periodic scan, not by a per-push overlay.
_PUSH_COALESCE_SECONDS = 0.5
# A non-zero S05 subsystem register is only a fault once the car has been
# continuously ready beyond the dashboard bulb check. A waking car also reports
# power status 2 with the airbag register at 1 for a few seconds (owner report
# 2026-11-20), so the first ready report after sleep must not raise a fault.
_S05_WARNING_SETTLE_SECONDS = 60.0
# The S05 publishes 0.0 kPa on the four wheels in the module-init burst that
# follows a wake (live capture 2026-11-21: three times, always ~2 s). A zero is
# only published once it has persisted this long, so a real puncture still shows.
_TIRE_ZERO_SETTLE_SECONDS = 60.0
#: The S05 lights sourced from the REST subsystem registers.
_S05_SUBSYSTEM_WARNING_FIELDS = frozenset(REST_SUBSYSTEM_WARNING_KEYS)


class WakeResult(StrEnum):
    """Outcome of an explicit wake-and-read attempt."""

    NOT_NEEDED = "not_needed"
    THROTTLED = "throttled"
    FRESH = "fresh"
    NO_REPORT = "no_report"
    FAILED = "failed"


@dataclass
class _OptimisticFieldHold:
    """One optimistic field waiting for the vehicle to confirm it."""

    expires: float
    value: Any


# How long the vehicle needs to complete a command's physical cycle before it
# accepts the same command again (measured on the real car). Comfort controls
# are purposely absent: their changes are frequent adjustments and go through
# the command queue without a minimum wait.
_COMMAND_COOLDOWN_SECONDS: dict[str, float] = {
    "flash_lights": 30.0,
    "flash_and_honk": 30.0,
    "honk_horn": 6.0,
}

# Gateway code returned when a signed command is submitted while the vehicle is
# still asleep. The code itself is a generic "Operation failed"; the observed
# meaning is only known for command submission (live S05, 2026-09-30).
_ASLEEP_COMMAND_ERROR_CODE = "APP_1_1_05_001"
_ASLEEP_COMMAND_MESSAGE = (
    "The vehicle did not accept the command; it may not have woken up or be "
    "offline. Try again once it is awake."
)

# Result code returned when a command is rejected because the vehicle is
# powered on (observed with the windows; upstream dec_deepal v2.0.0rc2).
_POWER_NOT_OFF_RESULT_CODE = 1032
_POWER_NOT_OFF_HINT = (
    " (the vehicle must be powered off before this command can run)"
)


def _command_failure_message(result: CommandResult) -> str:
    """Build the error message for a failed command result."""
    message = (
        f"Deepal command failed with result code {result.code}: "
        f"{result.error_message}"
    )
    if result.code == _POWER_NOT_OFF_RESULT_CODE:
        message += _POWER_NOT_OFF_HINT
    elif "TBOX_" in (result.error_message or ""):
        message += (
            " (the vehicle did not accept the command; it may be "
            "offline or busy, try again when it is awake)"
        )
    return message


def _command_failure_error(result: CommandResult) -> HomeAssistantError:
    """Build the translated error for a failed command result."""
    if result.code == _POWER_NOT_OFF_RESULT_CODE:
        key = "command_result_failed_power_off"
    elif "TBOX_" in (result.error_message or ""):
        key = "command_result_failed_unreachable"
    else:
        key = "command_result_failed"
    return HomeAssistantError(
        _command_failure_message(result),
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders={
            "code": str(result.code),
            "message": result.error_message or "",
        },
    )


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


_SEAT_LEVEL_FIELDS = ("heating_level", "ventilation_level")


def _overlay_seat_levels(source: Any, target: Any) -> None:
    """Copy the seat levels a source actually reported onto the target.

    Fields the source does not know (``None``) are left alone, so a partial
    app condition cannot wipe a level the MQTT snapshot did report.
    """
    for position in CORNER_POSITIONS:
        source_seat = getattr(source, position)
        target_seat = getattr(target, position)
        for field in _SEAT_LEVEL_FIELDS:
            value = getattr(source_seat, field)
            if value is not None:
                setattr(target_seat, field, value)


def _retain_seat_levels(
    previous: Any, condition: Any, pending: set[str] | None = None
) -> None:
    """Keep the last valid seat levels when a report comes back unknown.

    The S05 sends its sleep sentinel while a seat module sleeps; the previous
    valid level is still the car's real state, so it must not be reset. Levels
    whose last written value came from an unconfirmed optimistic update are not
    retained (``pending``): they expire instead of staying frozen.
    """
    for position in CORNER_POSITIONS:
        previous_seat = getattr(previous, position)
        seat = getattr(condition, position)
        for field in _SEAT_LEVEL_FIELDS:
            if pending and f"seats.{position}.{field}" in pending:
                continue
            if getattr(seat, field) is None:
                setattr(seat, field, getattr(previous_seat, field))


def _retain_odometer(previous: Any, condition: Any) -> None:
    """Keep the last odometer when a report would move it backwards.

    The odometer is a ``total_increasing`` value, but the MQTT and REST sources
    can disagree by their sub-kilometre precision and an MQTT snapshot can be
    older than the REST condition it replaces. Home Assistant only accepts a
    decrease as a meter reset when it falls below 90 % of the previous value;
    smaller drops are logged as precision dips and subtract the delta from the
    long-term sum. Mirror that threshold so the published series stays valid,
    retain the previous value when the field is missing, and still accept a real
    reset or a normal increase.
    """
    previous_value = previous.total_odometer_km
    value = condition.total_odometer_km
    if previous_value is None:
        return
    if value is None:
        condition.total_odometer_km = previous_value
        return
    if value >= previous_value:
        return
    previous_timestamp = previous.last_updated_timestamp
    current_timestamp = condition.last_updated_timestamp
    if (
        previous_timestamp is not None
        and current_timestamp is not None
        and current_timestamp < previous_timestamp
    ):
        condition.total_odometer_km = previous_value
        return
    if value >= _ODOMETER_RESET_RATIO * previous_value:
        condition.total_odometer_km = previous_value


_FUEL_FIELDS = (
    "level_percent",
    "remaining_range_km",
    "volume_l",
    "tank_capacity_l",
    "temperature_c",
)
_FUEL_STATIC_FIELDS = ("volume_l", "tank_capacity_l", "temperature_c")

_S05_GROUP_KEYS: dict[str, frozenset[str]] = {
    "doors": frozenset(
        {
            "driverDoor",
            "passengerDoor",
            "leftRearDoor",
            "rightRearDoor",
            "trunk",
            "hood",
            "hoodStatus",
            "driverDoorLock",
            "passengerDoorLock",
        }
    ),
    "windows": frozenset(
        {
            "diverWindow",
            "passengerWindow",
            "leftRearWindow",
            "rightRearWindow",
        }
    ),
    "lamps": frozenset(
        {
            "highBeam",
            "lowBeam",
            "positionLamp",
            "frontFoglamp",
            "rearFoglamp",
            "turnLndicatorLeft",
            "turnLndicatorRight",
        }
    ),
    "tires": frozenset(
        {
            "lfTyrePressure",
            "leftFrontTireTemperature",
            "lfPressureWarning",
            "rfTyrePressure",
            "rightFrontTireTemperature",
            "rfPressureWarning",
            "lrTyrePressure",
            "leftRearTireTemperature",
            "lrPressureWarning",
            "rrTyrePressure",
            "rightRearTireTemperature",
            "rrPressureWarning",
        }
    ),
    "charge": frozenset(("ChrgSts", *S05_CHARGE_GUN_KEYS)),
}

_SDA_GROUP_KEYS: dict[str, frozenset[str]] = {
    "doors": frozenset(
        {
            "DrvrDoorSts",
            "PassDoorSts",
            "LeReDoorSts",
            "RiReDoorSts",
            "ObjStTypePLGDoorSt",
            "FrtGateSts",
            "DrvrDoorLockLogicSts",
            "PassDoorLockLogicSts",
        }
    ),
    "windows": frozenset(
        {"DrvrWinPos", "PassWinPos", "LeReWinPos", "RiReWinPos"}
    ),
    "lamps": frozenset(
        {"HCM_LeHiBeSt", "HCM_RiHiBeSt", "HCM_LeLoBeSt", "HCM_RiLoBeSt"}
    ),
    "charge": frozenset({"BcuChrgSts", "AcChrgCnctrSts", "DcChrgCnctrSts"}),
}

_REST_GROUP_KEYS = {
    "doors": "door",
    "windows": "window",
    "lamps": "lamp",
    "tires": "tire",
    "charge": "charge",
}

#: Telemetry groups whose last known value is retained field by field.
_RETAINED_GROUPS = ("doors", "windows", "lamps", "tires")
#: Charger fields stored on ``battery`` but sourced from the charge group.
_CHARGE_FIELDS = (
    "charging_status",
    "charger_connected",
    "dc_gun_connected",
    "ac_gun_connected",
)


def _group_was_reported(condition: VehicleCondition, group: str) -> bool:
    """Return whether the source payload carried one telemetry group."""
    mqtt_raw = condition.mqtt_raw_data
    if mqtt_raw:
        key_sets = (
            _SDA_GROUP_KEYS
            if (condition.condition_source or "").startswith("sda")
            else _S05_GROUP_KEYS
        )
        keys = key_sets.get(group, frozenset())
        return bool(keys) and any(key in mqtt_raw for key in keys)
    raw = condition.raw_data or {}
    return _REST_GROUP_KEYS[group] in raw


def _retain_unreported_groups(
    previous: VehicleCondition,
    condition: VehicleCondition,
    pending: set[str] | None = None,
) -> None:
    """Keep the last known groups a partial payload did not carry.

    The retention is per field: a field whose last value came from an
    unconfirmed optimistic update must expire, but that pending mark must not
    publish the parser defaults for the rest of its group. A group with no
    pending field keeps the whole-group fast path.
    """
    pending = pending or set()
    for group in _RETAINED_GROUPS:
        if _group_was_reported(condition, group):
            continue
        previous_group = getattr(previous, group)
        group_pending = {
            path for path in pending if path.startswith(f"{group}.")
        }
        if not group_pending:
            setattr(condition, group, previous_group.model_copy(deep=True))
            continue
        current_group = getattr(condition, group)
        for field in type(previous_group).model_fields:
            if f"{group}.{field}" in group_pending:
                continue
            value = getattr(previous_group, field)
            setattr(
                current_group,
                field,
                value.model_copy(deep=True)
                if hasattr(value, "model_copy")
                else value,
            )
    if _group_was_reported(condition, "charge"):
        return
    for field in _CHARGE_FIELDS:
        if f"battery.{field}" in pending:
            continue
        setattr(condition.battery, field, getattr(previous.battery, field))


def _copy_missing_fields(target: Any, source: Any, fields: tuple[str, ...]) -> None:
    """Copy the source values the target does not carry yet."""
    for field in fields:
        if getattr(target, field) is not None:
            continue
        value = getattr(source, field)
        if value is not None:
            setattr(target, field, value)


class DeepalDataUpdateCoordinator(DataUpdateCoordinator[dict[str, VehicleCondition]]):
    """Class to manage fetching Changan Deepal data from API."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: DeepalClient | DeepalIntlClient,
        update_interval: timedelta = timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        wake_enabled: bool = True,
        live_session_enabled: bool = True,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self.entry = entry
        self.client = client
        self.wake_enabled = wake_enabled
        self.live_session_enabled = live_session_enabled
        self._mqtt_session: Any = None
        self._mqtt_session_state: dict[str, Any] | None = None
        self._live_session_stopping = False
        # Incremented per vehicle on every pushed/overlaid publication so the
        # periodic poll can detect a push that landed while it was in flight,
        # even when both conditions share the car's one-second report timestamp.
        self._vehicle_generation: dict[str, int] = {}
        self._push_pending: dict[str, VehicleCondition] = {}
        self._push_tasks: dict[str, asyncio.Task[None]] = {}
        self.vehicles: list[Vehicle] = []
        self._last_vehicle_refresh: float = 0.0
        self._last_ca_refresh_at: float | None = None
        self._command_locks: dict[str, asyncio.Lock] = {}
        self._command_cooldowns: dict[tuple[str, str], float] = {}
        self._optimistic_holds: dict[str, dict[str, _OptimisticFieldHold]] = {}
        self._optimistic_pending: dict[str, set[str]] = {}
        self._capabilities: dict[str, VehicleCapabilities | None] = {}
        self._last_steering_wheel: dict[str, tuple[bool, int | None]] = {}
        # Per-vehicle ready window and last app-condition report timestamp. The
        # S05 subsystem lights are only faults after a settled ready state and a
        # fresh REST block; both are memory-only, so a restart starts unconfirmed.
        self._ready_since: dict[str, float] = {}
        self._last_app_report_ts: dict[str, int | None] = {}
        # Per-vehicle, per-tire start of a zero-pressure reading, used to tell a
        # module-init glitch from a real puncture, plus the condition object
        # already guarded so a double merge does not process the same report
        # twice.
        self._tire_zero_since: dict[str, dict[str, float]] = {}
        self._tire_guard_condition: dict[str, VehicleCondition] = {}
        self._last_wake_at: dict[str, float] = {}
        self._wake_locks: dict[str, asyncio.Lock] = {}
        self._wake_poll_interval = _WAKE_POLL_INTERVAL
        self._wake_report_timeout = WAKE_REPORT_TIMEOUT
        self._last_wake_result: dict[str, dict[str, Any]] = {}
        self._mqtt_attempts: dict[str, dict[str, Any]] = {}
        self.model_assets: Any = None
        self.charging: ChargingSessionManager | None = None
        self._charging_read_task: asyncio.Task[None] | None = None
        self._charging_read_stop: asyncio.Event | None = None
        scan_seconds = (
            update_interval.total_seconds()
            if update_interval is not None
            else float(DEFAULT_SCAN_INTERVAL)
        )
        # While charging, read the charging vehicles every two main polls and
        # force a wake, with a 10-minute floor for short scan intervals.
        self._charging_read_interval = max(
            _CHARGING_READ_INTERVAL, 2.0 * scan_seconds
        )
        # Last conditions stored before the restart; only the previous state of
        # the merge rules until the first poll of this run has been published.
        self._store: Store[dict[str, Any]] = Store(
            hass, SNAPSHOT_VERSION, f"{DOMAIN}.{entry.entry_id}.last_condition"
        )
        self._restored: dict[str, VehicleCondition] = {}
        self._restored_loaded = False

    def mqtt_attempt(self, vehicle_id: str) -> dict[str, Any] | None:
        """Return the last failed MQTT exchange details for diagnostics."""
        return self._mqtt_attempts.get(vehicle_id)

    def wake_result(self, vehicle_id: str) -> dict[str, Any] | None:
        """Return the last wake outcome for diagnostics."""
        return self._last_wake_result.get(vehicle_id)

    def mqtt_session_stats(self) -> dict[str, Any] | None:
        """Return the live MQTT session state for diagnostics."""
        session = self._mqtt_session
        if session is None:
            return None
        stats = session.stats().as_dict()
        stats["enabled"] = self.live_session_enabled
        stats["details"] = self._mqtt_session_state
        return stats

    async def async_start_mqtt_session(self) -> None:
        """Start the live MQTT session for the international MQTT vehicles."""
        if not self.live_session_enabled or self._mqtt_session is not None:
            return
        if not isinstance(self.client, DeepalIntlClient) or not self.client.user_id:
            return
        self._live_session_stopping = False
        vehicles = [
            vehicle
            for vehicle in self.vehicles
            if self.client.is_mqtt_vehicle(vehicle)
            and not self.client.is_sda_mqtt_vehicle(vehicle)
        ]
        if not vehicles:
            return
        try:
            session = self.client.create_mqtt_session(
                vehicles,
                on_condition=self._on_live_condition,
                on_state=self._on_live_state,
                refresh_session=self._async_refresh_live_session,
            )
            self._mqtt_session = session
            await session.start()
        except Exception as err:  # noqa: BLE001 - a failed session must not break setup
            self._mqtt_session = None
            _LOGGER.warning(
                "Deepal live MQTT session could not start: %s", err
            )

    async def async_stop_mqtt_session(self) -> None:
        """Stop the live session and wait for its pending publication tasks."""
        self._live_session_stopping = True
        tasks = [
            task
            for task in list(self._push_tasks.values())
            if task is not None and not task.done()
        ]
        for task in tasks:
            task.cancel()
        self._push_tasks.clear()
        self._push_pending.clear()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        session = self._mqtt_session
        self._mqtt_session = None
        if getattr(self.client, "mqtt_session", None) is session:
            self.client.mqtt_session = None
        if session is not None:
            try:
                await session.stop()
            except Exception as err:  # noqa: BLE001 - unload must continue
                _LOGGER.debug("Deepal live MQTT session stop failed: %s", err)

    def _on_live_condition(
        self, vehicle_id: str, condition: VehicleCondition
    ) -> None:
        """Queue a pushed condition for a short per-vehicle coalescing window."""
        if self._live_session_stopping:
            return
        self._push_pending[vehicle_id] = condition
        task = self._push_tasks.get(vehicle_id)
        if task is not None and not task.done():
            return
        self._push_tasks[vehicle_id] = self.entry.async_create_background_task(
            self.hass,
            self._async_publish_push_later(vehicle_id),
            f"{DOMAIN} live push {vehicle_id}",
        )

    async def _async_publish_push_later(self, vehicle_id: str) -> None:
        """Wait for the coalescing window and publish the latest push."""
        try:
            await asyncio.sleep(_PUSH_COALESCE_SECONDS)
        except asyncio.CancelledError:
            return
        self._push_tasks.pop(vehicle_id, None)
        condition = self._push_pending.pop(vehicle_id, None)
        if condition is None:
            return
        await self._async_publish_push_condition(vehicle_id, condition)

    async def _async_publish_push_condition(
        self, vehicle_id: str, condition: VehicleCondition
    ) -> None:
        """Merge and publish one pushed condition without waiting for REST."""
        if self._live_session_stopping:
            return
        current = (self.data or {}).get(vehicle_id)
        if self._is_older_condition(current, condition):
            return
        try:
            condition = self._merge_condition(vehicle_id, condition)
            # A push does not carry the REST registers. Force the three S05
            # subsystem lights through the same gate so the glitchy MQTT bits
            # never reach the published condition.
            self._guard_subsystem_warnings(vehicle_id, condition)
            condition = self._apply_optimistic_hold(vehicle_id, condition)
            self._update_ready_window(vehicle_id, condition)
            data = dict(self.data or {})
            data[vehicle_id] = condition
            self._track_charging(data)
            self._sync_charging_read(data)
            self._vehicle_generation[vehicle_id] = (
                self._vehicle_generation.get(vehicle_id, 0) + 1
            )
            self.async_set_updated_data(data)
            store = getattr(self, "_store", None)
            if store is not None:
                store.async_delay_save(self._snapshot_payload, _SNAPSHOT_SAVE_DELAY)
        except Exception:  # noqa: BLE001 - a bad push must not kill the session
            _LOGGER.exception("Deepal live MQTT push publication failed")

    def _on_live_state(self, state: str, details: dict[str, Any]) -> None:
        """Keep the last session state for diagnostics and warn on conflicts."""
        self._mqtt_session_state = {
            "state": state,
            "details": details,
            "at": time.time(),
        }
        if state == "conflict":
            _LOGGER.warning(
                "Deepal live MQTT session is in conflict; backing off: %s",
                details,
            )

    async def _async_refresh_live_session(self, reason: str) -> bool:
        """Refresh the account session for a rejected live-session bootstrap."""
        return await self._async_refresh_session_for_mqtt(
            DeepalAPIError(reason)
        )

    async def _async_maybe_refresh_vehicles(self) -> None:
        """Refresh the account vehicle list and reload when it changed.

        The list changes rarely and the account is rate limited, so it is
        re-checked at most every ten minutes. A failed or empty refresh keeps
        the current list; a different vehicle set triggers a config entry
        reload so the platforms are rebuilt for the new set.
        """
        now = time.monotonic()
        first_fetch = not self.vehicles
        if (
            not first_fetch
            and now - self._last_vehicle_refresh < _VEHICLE_REFRESH_INTERVAL
        ):
            return
        self._last_vehicle_refresh = now
        try:
            vehicles = await self.client.get_vehicles()
        except DeepalError as err:
            if first_fetch:
                raise
            _LOGGER.debug("Deepal vehicle list refresh failed: %s", err)
            return
        if not vehicles:
            if first_fetch:
                self.vehicles = []
            else:
                _LOGGER.warning(
                    "Deepal account reported no vehicles; keeping the current list"
                )
            return
        current = {vehicle.car_id for vehicle in self.vehicles}
        if first_fetch or {vehicle.car_id for vehicle in vehicles} == current:
            self.vehicles = vehicles
            return
        _LOGGER.info("Deepal vehicle list changed; reloading the config entry")
        self.vehicles = vehicles
        self.hass.config_entries.async_schedule_reload(self.entry.entry_id)

    async def _async_fetch(self) -> dict[str, VehicleCondition]:
        """Fetch vehicles and their conditions."""
        await self._async_maybe_refresh_vehicles()

        data: dict[str, VehicleCondition] = {}
        failures: list[tuple[str, DeepalError]] = []
        for vehicle in self.vehicles:
            try:
                await self._async_maybe_fetch_capabilities(vehicle)
                condition = await self._async_fetch_condition(vehicle.car_id)
                condition = await self._overlay_app_comfort(vehicle, condition)
                data[vehicle.car_id] = self._apply_optimistic_hold(
                    vehicle.car_id, condition
                )
            except (DeepalRateLimitError, DeepalAuthError):
                # Rate limits need the coordinator backoff and session errors
                # need the refresh/reauth path, so they are never isolated.
                raise
            except DeepalError as err:
                failures.append((vehicle.car_id, err))
                previous = (self.data or {}).get(vehicle.car_id)
                if previous is not None:
                    data[vehicle.car_id] = previous
                _LOGGER.warning(
                    "Deepal condition fetch failed for %s: %s",
                    vehicle.car_id,
                    err,
                )

        if not data and failures:
            # Nothing could be published, not even a previous condition: let
            # the coordinator report the poll as failed.
            raise failures[-1][1]
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

    def _apply_steering_wheel_state(
        self, vehicle: Vehicle, condition: VehicleCondition
    ) -> None:
        """Apply the last server-authored steering wheel state, if there is one.

        The MQTT ``steeringWheelHeating`` field never follows the real switch, so
        whenever the app condition cannot author it (an unavailable request or a
        report without the field) the last state the server reported is kept
        instead of exposing the unreliable snapshot value. Before the first
        server-authored state the mapped MQTT value stands as the documented
        fallback.
        """
        remembered = self._last_steering_wheel.get(vehicle.car_id)
        if remembered is None:
            return
        condition.climate.steering_wheel_heater_on = remembered[0]
        condition.climate.steering_wheel_heater_level = remembered[1]

    def _apply_rest_subsystem_warnings(
        self,
        vehicle: Vehicle,
        condition: VehicleCondition,
        status: Any,
        *,
        report_ts: int | None = None,
    ) -> None:
        """Set the S05 airbag, ABS and power steering lights from REST registers.

        The REST overlay runs after the condition merge, so it is the place
        that can leave these three lights unknown on a sleeping car. A register
        is only trusted as a fault once the ready window was already established
        and the app report is fresh: the wake/self-check also reports ready with
        the airbag register at 1 for a few seconds (owner report 2026-11-20).
        Healthy values keep the last-known behavior, but an unconfirmed fault is
        never revived from the previous condition or the stored snapshot.
        """
        if not self._is_s05(vehicle):
            return
        established = self._ready_is_established(vehicle.car_id, condition)
        fresh = True
        if report_ts is not None:
            fresh = self._consume_app_report(vehicle.car_id, report_ts)
        previous = self._previous_condition(vehicle.car_id)
        self._resolve_subsystem_warnings(
            condition,
            previous,
            rest_subsystem_warnings(status, condition.power_status),
            established=established,
            fresh=fresh,
        )
        self._retain_unknown_warnings(
            condition,
            previous,
            skip=_S05_SUBSYSTEM_WARNING_FIELDS,
        )

    @staticmethod
    def _is_s05(vehicle: Vehicle) -> bool:
        """Return whether the vehicle uses the S05 REST subsystem registers."""
        return is_s05_model(vehicle.model_code) or is_s05_model(vehicle.series_code)

    @staticmethod
    def _resolve_subsystem_warnings(
        condition: VehicleCondition,
        previous: VehicleCondition | None,
        registers: dict[str, bool | None],
        *,
        established: bool,
        fresh: bool,
    ) -> None:
        """Publish the S05 subsystem lights under the ready/freshness rule.

        A non-zero register is a fault only while the ready window is settled
        and the app report advanced. Healthy values keep the last-known
        behavior; an unconfirmed fault is never revived from the previous
        condition or the stored snapshot.
        """
        for field in _S05_SUBSYSTEM_WARNING_FIELDS:
            value = registers.get(field)
            if value is True and not (established and fresh):
                value = None
            if value is None:
                retained = (
                    getattr(previous.warnings, field)
                    if previous is not None
                    else None
                )
                if retained is True:
                    value = True if established else None
                elif retained is False:
                    value = False
            setattr(condition.warnings, field, value)

    def _guard_subsystem_warnings(
        self, vehicle_id: str, condition: VehicleCondition
    ) -> None:
        """Keep the glitchy S05 bits out of non-REST publications.

        A live push or a command confirmation does not carry the REST
        registers, so it must never publish the MQTT airbag/ABS/EPS bits. A
        known non-S05 vehicle keeps its normal behavior; when the vehicle list
        is not loaded yet, the three diagnostic fields are resolved from the
        previous condition instead of exposing a possible false airbag light.
        """
        vehicle = self._vehicle(vehicle_id)
        if vehicle is not None and not self._is_s05(vehicle):
            return
        previous = self._previous_condition(vehicle_id)
        self._resolve_subsystem_warnings(
            condition,
            previous,
            rest_subsystem_warnings(None, condition.power_status),
            established=self._ready_is_established(vehicle_id, condition),
            fresh=True,
        )

    def _ready_is_established(
        self, vehicle_id: str, condition: VehicleCondition
    ) -> bool:
        """Return whether ready was already established before this report.

        A report without a power state carries no new ready/off information, so
        it keeps the current window instead of dropping a confirmed fault.
        """
        if condition.power_status not in (None, 2):
            return False
        since = self._ready_since.get(vehicle_id)
        return (
            since is not None
            and time.monotonic() - since >= _S05_WARNING_SETTLE_SECONDS
        )

    def _update_ready_window(
        self, vehicle_id: str, condition: VehicleCondition
    ) -> None:
        """Open or close the per-vehicle ready window from a published state."""
        vehicle = self._vehicle(vehicle_id)
        if vehicle is not None and not self._is_s05(vehicle):
            # The window only feeds the S05 subsystem warning rule.
            return
        if condition.power_status is None:
            # A partial push without the power state says nothing about ready.
            return
        if condition.power_status != 2:
            self._ready_since.pop(vehicle_id, None)
            # A new ready window must not inherit a stale app timestamp; a
            # backward clock would otherwise suppress every later report.
            self._last_app_report_ts.pop(vehicle_id, None)
            return
        if vehicle_id not in self._ready_since:
            self._ready_since[vehicle_id] = time.monotonic()

    def _consume_app_report(
        self, vehicle_id: str, report_ts: int | None
    ) -> bool:
        """Record the app report timestamp and return whether it advanced.

        The server can keep the last ``vehicleStatus`` block after the car
        sleeps. Reusing the same report timestamp means the block was not read
        again, so it must not raise a new fault. A missing timestamp falls back
        to the ready-window rule. Recording happens here so a later call in the
        same cycle sees the report as already consumed. The comparison is
        strict: two reports with the same second-resolution timestamp count as
        one read, which only matters inside a burst (the scan is minutes apart).
        """
        if report_ts is None:
            return True
        previous = self._last_app_report_ts.get(vehicle_id)
        if previous is not None and report_ts <= previous:
            return False
        self._last_app_report_ts[vehicle_id] = report_ts
        return True

    async def _overlay_app_comfort(
        self,
        vehicle: Vehicle,
        condition: VehicleCondition,
        *,
        app_condition: VehicleCondition | None = None,
    ) -> VehicleCondition:
        """Overlay the app's seat, steering and charge state onto an MQTT snapshot.

        The S05 seat modules report sentinel values over MQTT while they are
        asleep, and the MQTT ``steeringWheelHeating``/``frontDefrostStatus``
        fields do not follow the switches the app shows. The server condition
        endpoint returns the same report already normalized the way the app
        displays it. The steering wheel switch and the front defrost take the
        server value whenever it carries them, even when its report is older
        than the snapshot, because the MQTT fields are unreliable by design; the
        last server-authored steering wheel state is remembered and kept when a
        later app condition fails or omits the field, with the MQTT fallback
        only before the first server-authored state.
        The seat block and the charge connection flags keep the freshness rule
        (the server condition applies only when its report is not older), so a
        genuinely newer MQTT snapshot wins; the server condition is also the
        fallback for the gun fields a car omits over MQTT. For an S05 the cable
        flag is never copied: its REST `chargeConStatus` can stay stale while
        unplugged, and the MQTT `ChrgSts` state already decides it. The DC gun
        still fills from the app condition when the snapshot omits it. PHEV
        fuel and the AC charge limit are merged per field: dynamic fuel values
        keep the freshness rule, while volume, tank capacity, fuel temperature
        and the charge limit are slow or static and fill a missing field even
        when the server report is older.
        """
        if not self._uses_mqtt(vehicle):
            return condition
        # The MQTT airbag, ABS and power steering light bits glitch on a healthy
        # car, so for an S05 they are taken from the REST subsystem registers
        # only: unknown until the app condition confirms them.
        self._apply_rest_subsystem_warnings(vehicle, condition, None)
        if app_condition is None:
            try:
                app_condition = await self.client.get_vehicle_condition(
                    vehicle.car_id,
                    vin=vehicle.vin,
                    model_code=vehicle.model_code,
                )
            except DeepalError as err:
                _LOGGER.debug(
                    "Deepal app condition overlay failed for %s: %s",
                    vehicle.car_id,
                    err,
                )
                self._apply_steering_wheel_state(vehicle, condition)
                return condition
        assert app_condition is not None
        self._apply_rest_subsystem_warnings(
            vehicle,
            condition,
            (app_condition.raw_data or {}).get("vehicleStatus"),
            report_ts=app_condition.last_updated_timestamp,
        )
        mqtt_ts = condition.last_updated_timestamp
        app_ts = app_condition.last_updated_timestamp
        if (app_condition.raw_data or {}).get("charge", {}).get("chargePlanList"):
            # The charge plan only exists in the app condition (the MQTT report
            # carries no schedule); it is configuration, so it applies even
            # when the app report is older. The plan id, validity and the full
            # plan list are always taken from the app condition: a stale
            # charge_plan_id in the MQTT snapshot would make the switch delete
            # the wrong plan after an add.
            condition.battery.charge_schedule_start = (
                app_condition.battery.charge_schedule_start
            )
            condition.battery.charge_schedule_end = (
                app_condition.battery.charge_schedule_end
            )
            condition.battery.charge_plan_id = app_condition.battery.charge_plan_id
            condition.battery.charge_plan_type = (
                app_condition.battery.charge_plan_type
            )
            condition.battery.charge_plan_time_format = (
                app_condition.battery.charge_plan_time_format
            )
            condition.battery.charge_plan_time_zone = (
                app_condition.battery.charge_plan_time_zone
            )
            condition.battery.charge_plan_valid = (
                app_condition.battery.charge_plan_valid
            )
            condition.battery.charge_schedule_enabled = (
                app_condition.battery.charge_schedule_enabled
            )
            condition.battery.charge_plans = list(
                app_condition.battery.charge_plans
            )
        app_is_older = (
            mqtt_ts is not None and app_ts is not None and app_ts < mqtt_ts
        )
        raw = app_condition.raw_data or {}
        # The MQTT enum is the reliable source for app-originated changes
        # (2 = on, 1 = off, verified 2026-11-20); the REST field can stay 0
        # while the wheel is physically on. Keep the server value remembered
        # only as the fallback for a snapshot that omits the MQTT field.
        steering_on = app_condition.climate.steering_wheel_heater_on
        if (
            (raw.get("vehicleStatus") or {}).get("steeringWheelHeater") is not None
            and steering_on is not None
        ):
            self._last_steering_wheel[vehicle.car_id] = (
                steering_on,
                app_condition.climate.steering_wheel_heater_level,
            )
        if "steeringWheelHeating" not in (condition.mqtt_raw_data or {}):
            self._apply_steering_wheel_state(vehicle, condition)
        if (raw.get("hvac") or {}).get("defrostStatus") is not None:
            condition.climate.defrost_on = app_condition.climate.defrost_on
        if app_is_older:
            # A genuinely newer MQTT snapshot wins for dynamic fuel values, but
            # the static PHEV fields and the AC limit are absent from the MQTT
            # path, so an older REST report is still better than unknown.
            _copy_missing_fields(
                condition.fuel, app_condition.fuel, _FUEL_STATIC_FIELDS
            )
            if condition.battery.charge_limit_percent is None:
                condition.battery.charge_limit_percent = (
                    app_condition.battery.charge_limit_percent
                )
            return condition
        if raw.get("seat"):
            _overlay_seat_levels(app_condition.seats, condition.seats)
        app_charge = raw.get("charge") or {}
        mqtt_raw = condition.mqtt_raw_data or {}
        s05 = is_s05_model(vehicle.model_code) or is_s05_model(vehicle.series_code)
        if (
            not s05
            and not any(key in mqtt_raw for key in S05_CHARGE_GUN_KEYS)
            and condition.battery.charging_status in (None, "0")
            and app_charge.get("chargeConStatus") is not None
        ):
            condition.battery.charger_connected = (
                app_condition.battery.charger_connected
            )
        if (
            not any(key in mqtt_raw for key in S05_DC_GUN_KEYS)
            and app_charge.get("dcChargeGunConnectStatus") is not None
        ):
            condition.battery.dc_gun_connected = app_condition.battery.dc_gun_connected
        _copy_missing_fields(condition.fuel, app_condition.fuel, _FUEL_FIELDS)
        if condition.battery.charge_limit_percent is None:
            condition.battery.charge_limit_percent = (
                app_condition.battery.charge_limit_percent
            )
        return condition

    def _register_optimistic_hold(
        self, vehicle_id: str, before: dict[str, Any], after: dict[str, Any]
    ) -> None:
        """Remember the fields a command changed so reports cannot revert them.

        Holds are kept per changed field and merged with the holds of earlier
        commands: a command that touches other fields must not release them,
        while a command that touches the same field refreshes its value and its
        window. The changed paths are also marked as unconfirmed: the merge
        will not restore them from the previous condition once the hold expires
        unless a report carried them.
        """
        changes = _diff_paths(before, after)
        if not changes:
            return
        expires = time.monotonic() + _OPTIMISTIC_HOLD_SECONDS
        hold = self._optimistic_holds.setdefault(vehicle_id, {})
        for path, value in changes.items():
            hold[path] = _OptimisticFieldHold(expires, value)
        self._optimistic_pending.setdefault(vehicle_id, set()).update(changes)

    def _apply_optimistic_hold(
        self, vehicle_id: str, condition: VehicleCondition
    ) -> VehicleCondition:
        """Keep the optimistic values until the vehicle confirms them.

        The car applies commands with a delay (and the account is rate limited),
        so reports generated before the command took effect would otherwise
        revert the entity to the previous value. Each field has its own window:
        a value the vehicle never confirms expires when that window closes, and
        its unconfirmed mark keeps the previous-condition merge from restoring
        it. A report that carries the field clears the mark.
        """
        hold = self._optimistic_holds.get(vehicle_id)
        masked: set[str] = set()
        if hold is not None:
            now = time.monotonic()
            remaining: dict[str, _OptimisticFieldHold] = {}
            for path, entry in hold.items():
                if now >= entry.expires:
                    # This field's window closed: stop overriding it. Its
                    # unconfirmed mark stays so the merge cannot resurrect it.
                    continue
                try:
                    if _path_get(condition, path) == entry.value:
                        continue
                    _path_set(condition, path, entry.value)
                except AttributeError:
                    self._optimistic_pending.get(vehicle_id, set()).discard(path)
                    continue
                self._optimistic_pending.setdefault(vehicle_id, set()).add(path)
                remaining[path] = entry
                masked.add(path)
            if remaining:
                self._optimistic_holds[vehicle_id] = remaining
            else:
                self._optimistic_holds.pop(vehicle_id, None)
        pending = self._optimistic_pending.get(vehicle_id)
        if pending:
            # A value that is actually stored (not masked by the hold) and comes
            # from a report is confirmed: it stops being unconfirmed.
            for path in list(pending):
                if path in masked:
                    continue
                try:
                    if _path_get(condition, path) is not None:
                        pending.discard(path)
                except AttributeError:
                    pending.discard(path)
            if not pending:
                self._optimistic_pending.pop(vehicle_id, None)
        return condition

    async def _async_fetch_condition(self, vehicle_id: str) -> VehicleCondition:
        """Fetch one condition through MQTT when available, REST otherwise."""
        vehicle = next(
            (item for item in self.vehicles if item.car_id == vehicle_id), None
        )
        if vehicle is not None and self._uses_mqtt(vehicle):
            sda = self.client.is_sda_mqtt_vehicle(vehicle)
            if sda:
                # The official app reads the SDA condition over REST; the SDA
                # MQTT broker (prod-appmq, authType 2) is a separate exchange
                # not implemented yet, so REST comes first.
                try:
                    condition = await self.client.get_sda_vehicle_condition(
                        vehicle_id, vin=vehicle.vin
                    )
                    return self._merge_condition(vehicle_id, condition)
                except DeepalError as err:
                    _LOGGER.debug(
                        "Deepal SDA REST condition unavailable for %s: %s",
                        vehicle_id,
                        err,
                    )
            try:
                condition = await self.client.s05_mqtt_condition(
                    vehicle_id, vin=vehicle.vin, sda=sda
                )
                self._mqtt_attempts.pop(vehicle_id, None)
                return self._merge_condition(vehicle_id, condition)
            except DeepalAPIError as err:
                if getattr(err, "code", None) in CA_TOKEN_ERROR_CODES and (
                    await self._async_refresh_session_for_mqtt(err)
                ):
                    try:
                        condition = await self.client.s05_mqtt_condition(
                            vehicle_id, vin=vehicle.vin, sda=sda
                        )
                        self._mqtt_attempts.pop(vehicle_id, None)
                        return self._merge_condition(vehicle_id, condition)
                    except DeepalAPIError as retry_err:
                        err = retry_err
                self._record_mqtt_failure(vehicle_id, err)
            except DeepalError as err:
                # A broker connection or session failure is not a reason to
                # fail the poll while the REST condition endpoint is available.
                self._record_mqtt_failure(vehicle_id, err)
        vin = vehicle.vin if vehicle is not None else None
        if isinstance(self.client, DeepalIntlClient):
            # The model code selects the S05 PHEV REST charge rule and is an
            # international-only argument: the SDA client addresses vehicles by
            # car id and its signature does not accept it.
            condition = await self.client.get_vehicle_condition(
                vehicle_id,
                vin=vin,
                model_code=vehicle.model_code if vehicle is not None else None,
            )
        else:
            condition = await self.client.get_vehicle_condition(vehicle_id, vin=vin)
        condition.condition_source = "rest"
        condition = self._merge_condition(vehicle_id, condition)
        if vehicle is not None and self._is_s05(vehicle):
            # The MQTT overlay is not available on this path (REST-only vehicle
            # or MQTT fallback), so apply the REST subsystem rule here too.
            self._apply_rest_subsystem_warnings(
                vehicle,
                condition,
                (condition.raw_data or {}).get("vehicleStatus"),
                report_ts=condition.last_updated_timestamp,
            )
        return condition

    def _record_mqtt_failure(self, vehicle_id: str, err: DeepalError) -> None:
        """Keep the failed MQTT exchange for diagnostics and log the fallback."""
        exchange = getattr(self.client, "last_mqtt_exchange", None)
        if exchange is not None:
            self._mqtt_attempts[vehicle_id] = {
                "source": exchange.source,
                "variants": exchange.variants,
                "plan": (
                    exchange.plan.as_dict() if exchange.plan else None
                ),
                "qos": exchange.qos,
                "keepalive": exchange.keepalive,
                "connect_timeout": exchange.connect_timeout,
                "server_keep_alive": exchange.server_keep_alive,
                "maximum_qos": exchange.maximum_qos,
                "effective_qos": exchange.effective_qos,
                "effective_keepalive": exchange.effective_keepalive,
                "logout_sent": exchange.logout_sent,
                "logout_error": exchange.logout_error,
            }
        _LOGGER.warning(
            "Deepal MQTT telemetry unavailable for %s (%s); using the "
            "REST condition endpoint",
            vehicle_id,
            err,
        )

    async def _async_refresh_session_for_mqtt(self, err: Exception) -> bool:
        """Refresh the session when the CA gateway rejects it.

        A persistently rejected CA token must not refresh on every poll, so the
        attempt is capped at one per hour; a failed attempt occupies the window
        like the SDK's own throttle. The SDK still owns the per-client window
        and the single-flight behavior.
        """
        if not getattr(self.client, "refresh_token", None):
            return False
        now = time.monotonic()
        last_attempt = self._last_ca_refresh_at
        if (
            last_attempt is not None
            and now - last_attempt < _CA_REFRESH_MIN_INTERVAL
        ):
            _LOGGER.info(
                "Deepal CA token refresh throttled (last attempt %.0f s ago); "
                "using the REST condition",
                now - last_attempt,
            )
            return False
        self._last_ca_refresh_at = now
        _LOGGER.warning(
            "Deepal MQTT token rejected (%s); refreshing the session and retrying",
            err,
        )
        try:
            return await self._async_refresh_tokens(force=True)
        except DeepalConnectionError as err:
            # The CA token is auxiliary to telemetry: a refresh that cannot
            # reach the gateway must not fail the poll while REST still works.
            _LOGGER.warning(
                "Deepal session refresh failed (%s); using the REST condition",
                err,
            )
            return False

    def _previous_condition(self, vehicle_id: str) -> VehicleCondition | None:
        """Return the last published condition, or the stored one before it."""
        return (self.data or {}).get(vehicle_id) or self._restored.get(vehicle_id)

    @staticmethod
    def _retain_unknown_warnings(
        condition: VehicleCondition,
        previous: VehicleCondition | None,
        *,
        skip: frozenset[str] = frozenset(),
    ) -> None:
        """Fill the warning lights a condition did not report from the last one.

        Only unknown fields are filled, so a warning value reported by the
        current condition always wins. ``skip`` lets the S05 subsystem overlay
        apply its own ready/freshness rule instead of this blind retention.
        """
        if previous is None:
            return
        for field in type(condition.warnings).model_fields:
            if field in skip:
                continue
            if getattr(condition.warnings, field) is not None:
                continue
            retained = getattr(previous.warnings, field)
            if retained is not None:
                setattr(condition.warnings, field, retained)

    @staticmethod
    def _is_older_condition(
        current: VehicleCondition | None, incoming: VehicleCondition
    ) -> bool:
        """Return whether an incoming condition is older than the published one.

        A live push can arrive while the periodic poll is still in flight. The
        poll result must not replace a condition with a newer report
        timestamp; an incoming condition without a timestamp keeps the
        timestamped one and only contributes its REST-only fields.
        """
        if current is None or current.last_updated_timestamp is None:
            return False
        if incoming.last_updated_timestamp is None:
            # A report without a timestamp cannot be proven newer than a
            # timestamped pushed condition; keep the newer telemetry and only
            # merge its REST-only fields.
            return True
        return incoming.last_updated_timestamp < current.last_updated_timestamp

    @staticmethod
    def _is_newer_condition(
        current: VehicleCondition, incoming: VehicleCondition
    ) -> bool:
        """Return whether the incoming condition is strictly newer."""
        return (
            incoming.last_updated_timestamp is not None
            and (
                current.last_updated_timestamp is None
                or incoming.last_updated_timestamp
                > current.last_updated_timestamp
            )
        )

    @staticmethod
    def _merge_rest_only_fields(
        current: VehicleCondition, polled: VehicleCondition
    ) -> VehicleCondition:
        """Keep the newer pushed telemetry and take the REST-only fields.

        The poll can be older than a push that arrived while it was in flight.
        Its MQTT fields must not replace the push, but the charge plan,
        static fuel values, charge limit, steering wheel and defrost come from
        the app condition and would otherwise wait another scan interval.
        """
        merged = current.model_copy(deep=True)
        source = polled.battery
        target = merged.battery
        if (
            source.charge_plan_id is not None
            or source.charge_schedule_start is not None
            or source.charge_plans
        ):
            for field in (
                "charge_plan_id",
                "charge_plan_type",
                "charge_plan_time_format",
                "charge_plan_time_zone",
                "charge_plan_valid",
                "charge_schedule_start",
                "charge_schedule_end",
                "charge_schedule_enabled",
            ):
                setattr(target, field, getattr(source, field))
            if source.charge_plans:
                target.charge_plans = list(source.charge_plans)
        if target.charge_limit_percent is None:
            target.charge_limit_percent = source.charge_limit_percent
        _copy_missing_fields(merged.fuel, polled.fuel, _FUEL_STATIC_FIELDS)
        if polled.climate.steering_wheel_heater_on is not None:
            merged.climate.steering_wheel_heater_on = (
                polled.climate.steering_wheel_heater_on
            )
            merged.climate.steering_wheel_heater_level = (
                polled.climate.steering_wheel_heater_level
            )
        if polled.climate.defrost_on is not None:
            merged.climate.defrost_on = polled.climate.defrost_on
        # The S05 subsystem lights are REST-only too. Keep a value the poll just
        # confirmed even when a push replaced the base while it was in flight;
        # a poll that could not resolve them (None) must not erase the push's
        # retained value.
        for field in _S05_SUBSYSTEM_WARNING_FIELDS:
            value = getattr(polled.warnings, field)
            if value is not None:
                setattr(merged.warnings, field, value)
        return merged

    def _merge_condition(
        self, vehicle_id: str, condition: VehicleCondition
    ) -> VehicleCondition:
        """Keep the last known state for the fields the vehicle did not report.

        S05 condition payloads have no ``hvac.acStatus``; overwriting the state
        with the parser default would turn the climate entity off after every
        poll, discarding optimistic command feedback. The same applies to the
        seat levels: the sleep sentinel means unknown, and the last valid level
        is still the car's real state.

        A field whose last written value came from an unconfirmed optimistic
        update must not be restored this way: it expires to unknown when the
        vehicle stops reporting it, until a report carries it again. The last
        known position is also kept, so the location tracker does not flap when
        the car reports no coordinates. The dashboard warning lights reported as
        unknown (vehicle off, asleep or a REST fallback) keep their last known
        values as well. The S05 airbag, ABS and power-steering lights are the
        exception: their overlay applies its own ready/freshness rule after this
        merge, so an unconfirmed fault is not revived here. PHEV fuel and the
        AC charge limit also keep their last known values; an unconfirmed
        optimistic charge limit expires
        instead of being retained. The odometer keeps the previous value on a
        missing field, a stale lower report or a precision dip, so the
        ``total_increasing`` sensor only moves forward or resets. A partial
        payload that does not carry the door, window, lamp, tire or charger group
        keeps the previous group, so the parser defaults are not published as
        telemetry.
        """
        pending = self._optimistic_pending.get(vehicle_id)

        def keep(path: str) -> bool:
            return pending is None or path not in pending

        previous = self._previous_condition(vehicle_id)
        self._retain_valid_tire_pressures(vehicle_id, previous, condition)
        if previous is not None:
            if condition.latitude is None:
                condition.latitude = previous.latitude
            if condition.longitude is None:
                condition.longitude = previous.longitude
            self._retain_unknown_warnings(condition, previous)
            _retain_unreported_groups(previous, condition, pending)
            _retain_odometer(previous, condition)
            _copy_missing_fields(
                condition.battery,
                previous.battery,
                (
                    "charge_schedule_start",
                    "charge_schedule_end",
                    "charge_plan_id",
                    "charge_plan_type",
                    "charge_plan_time_format",
                    "charge_plan_time_zone",
                ),
            )
            if condition.battery.charge_plan_valid is None:
                condition.battery.charge_plan_valid = (
                    previous.battery.charge_plan_valid
                )
                condition.battery.charge_schedule_enabled = (
                    previous.battery.charge_schedule_enabled
                )
                condition.battery.charge_plans = list(
                    previous.battery.charge_plans
                )
            _copy_missing_fields(condition.fuel, previous.fuel, _FUEL_FIELDS)
            if condition.battery.charge_limit_percent is None and keep(
                "battery.charge_limit_percent"
            ):
                condition.battery.charge_limit_percent = (
                    previous.battery.charge_limit_percent
                )
            if condition.climate.power_on is None and keep("climate.power_on"):
                condition.climate.power_on = previous.climate.power_on
            if condition.climate.steering_wheel_heater_on is None and keep(
                "climate.steering_wheel_heater_on"
            ):
                condition.climate.steering_wheel_heater_on = (
                    previous.climate.steering_wheel_heater_on
                )
            if condition.climate.steering_wheel_heater_level is None and keep(
                "climate.steering_wheel_heater_level"
            ):
                condition.climate.steering_wheel_heater_level = (
                    previous.climate.steering_wheel_heater_level
                )
            if condition.climate.defrost_on is None and keep(
                "climate.defrost_on"
            ):
                condition.climate.defrost_on = previous.climate.defrost_on
            _retain_seat_levels(previous.seats, condition.seats, pending)
        return condition

    def _retain_valid_tire_pressures(
        self,
        vehicle_id: str,
        previous: VehicleCondition | None,
        condition: VehicleCondition,
        *,
        now: float | None = None,
    ) -> None:
        """Keep the last valid pressure while a zero is a wake-burst glitch.

        The car publishes ``0.0`` on the four wheels in the module-init burst
        that follows a wake (live S05 BEV, 2026-11-21: three times, always about
        two seconds after a valid snapshot and followed by the real values).
        Publishing that zero would make Home Assistant report four flat tires,
        so a zero keeps the last confirmed pressure until it has persisted for
        ``_TIRE_ZERO_SETTLE_SECONDS``; from then on it is published, because a
        real puncture must stay visible. A positive reading clears the timer.

        The poll path merges a fetched condition twice (the fetch merges it and
        the apply merges it again). The second pass carries the value we just
        restored, so it must not be mistaken for a fresh positive reading and
        clear the timer: each report object is guarded once.

        ``now`` is injectable so the 60-second window can be exercised without
        waiting; production always uses the monotonic clock.
        """
        if not _group_was_reported(condition, "tires"):
            # A delta without tire keys says nothing about the tires; the group
            # retention copies the last published values afterwards.
            return
        if self._tire_guard_condition.get(vehicle_id) is condition:
            # The poll path merges the same condition twice. Reports are
            # distinct objects even when two of them share a one-second
            # timestamp, so identity is the right dedupe key.
            return
        current_time = time.monotonic() if now is None else now
        zeros = self._tire_zero_since.setdefault(vehicle_id, {})
        for position in CORNER_POSITIONS:
            tire = getattr(condition.tires, position, None)
            if tire is None or tire.pressure_bar is None:
                continue
            if tire.pressure_bar > 0:
                zeros.pop(position, None)
                continue
            started = zeros.setdefault(position, current_time)
            if current_time - started >= _TIRE_ZERO_SETTLE_SECONDS:
                continue
            previous_tire = (
                getattr(previous.tires, position, None)
                if previous is not None
                else None
            )
            tire.pressure_bar = (
                previous_tire.pressure_bar if previous_tire is not None else None
            )
            _LOGGER.debug(
                "Deepal %s: ignoring an invalid 0.0 bar reading on %s",
                vehicle_id,
                position,
            )
        self._tire_guard_condition[vehicle_id] = condition

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
            warned = getattr(self, "_mqtt_user_id_warned", None)
            if warned is None:
                warned = self._mqtt_user_id_warned = set()
            if vehicle.car_id not in warned:
                warned.add(vehicle.car_id)
                _LOGGER.warning(
                    "Deepal vehicle %s is MQTT-backed but the entry has no user "
                    "id; using the REST condition endpoint (stale data). "
                    "Re-authenticate to enable MQTT telemetry.",
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
        except DeepalConnectionError:
            # A transport failure is not a rejected session: the update path
            # reports it as UpdateFailed instead of starting reauthentication.
            raise
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
                CONF_USER_ID: token.user_id
                or self.entry.data.get(CONF_USER_ID, ""),
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
        except (DeepalCommandAuthError, DeepalCommandNotReady):
            # Command prerequisites (PIN, rcToken, signing material) are not
            # an expired account session: never refresh the tokens or replay
            # the command, which could consume a second control-PIN attempt.
            raise
        except DeepalAuthError:
            if not await self._async_refresh_tokens(force=True):
                raise
            return await action()

    async def async_condition_inquiry(self, vehicle_id: str) -> None:
        """Ask the vehicle for fresh data, recovering an expired session."""
        if not isinstance(self.client, DeepalIntlClient):
            raise HomeAssistantError(
                "Remote commands require the international platform",
                translation_domain=DOMAIN,
                translation_key="commands_require_international",
            )
        await self._async_with_session_retry(
            lambda: self.client.control_condition_inquiry(vehicle_id)
        )

    def _vehicle(self, vehicle_id: str) -> Vehicle | None:
        """Return the cached vehicle entry for an id, if it was fetched."""
        return next(
            (item for item in self.vehicles if item.car_id == vehicle_id), None
        )

    def _wake_block_reason(
        self, vehicle_id: str, report_ts: int | None
    ) -> WakeResult | None:
        """Return why a wake is not needed, or ``None`` when it should run."""
        if not self.wake_enabled:
            return WakeResult.NOT_NEEDED
        if (
            report_ts is not None
            and time.time() - report_ts <= WAKE_STALE_AFTER
        ):
            return WakeResult.NOT_NEEDED
        last_wake = self._last_wake_at.get(vehicle_id)
        if last_wake is not None and time.monotonic() - last_wake < WAKE_COOLDOWN:
            return WakeResult.THROTTLED
        return None

    def _record_wake_result(
        self,
        vehicle_id: str,
        result: WakeResult,
        *,
        wake_sent: bool,
        timeout: float | None = None,
        error: DeepalError | None = None,
    ) -> None:
        """Keep the last wake outcome for the diagnostics report."""
        record: dict[str, Any] = {
            "result": str(result),
            "wake_sent": wake_sent,
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        if timeout is not None:
            record["timeout_s"] = round(timeout, 1)
        if error is not None:
            record["error"] = str(error)[:200]
            code = getattr(error, "code", None)
            if code:
                record["code"] = str(code)
        self._last_wake_result[vehicle_id] = record

    async def async_wake_vehicle(self, vehicle_id: str) -> None:
        """Wake an MQTT vehicle, recovering an expired session or CA token."""
        if not isinstance(self.client, DeepalIntlClient):
            raise HomeAssistantError(
                "Remote wake requires the international platform",
                translation_domain=DOMAIN,
                translation_key="wake_requires_international",
            )
        try:
            await self._async_with_session_retry(
                lambda: self.client.wake_vehicle(vehicle_id)
            )
        except DeepalAPIError as err:
            if (
                getattr(err, "code", None) in CA_TOKEN_ERROR_CODES
                and await self._async_refresh_session_for_mqtt(err)
            ):
                await self._async_with_session_retry(
                    lambda: self.client.wake_vehicle(vehicle_id)
                )
            else:
                raise

    async def _async_wait_for_report(
        self,
        vehicle_id: str,
        previous: int | None,
        *,
        timeout: float | None = None,
    ) -> VehicleCondition | None:
        """Wait for a newer MQTT report through one bounded SDK exchange.

        The SDK opens a single session and re-requests the condition on it, so
        the wait no longer pays a full MQTT session per poll. A session-level
        failure is retried with the remaining window, keeping the previous
        tolerance to per-poll errors.
        """
        vehicle = self._vehicle(vehicle_id)
        vin = vehicle.vin if vehicle is not None else None
        wait_timeout = self._wake_report_timeout if timeout is None else timeout
        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait_timeout
        while loop.time() < deadline:
            try:
                condition = await self.client.s05_wait_for_report(
                    vehicle_id,
                    previous_timestamp=previous,
                    interval=self._wake_poll_interval,
                    timeout=max(0.05, deadline - loop.time()),
                    vin=vin,
                )
            except DeepalError as err:
                _LOGGER.debug(
                    "Deepal wake report wait failed for %s: %s", vehicle_id, err
                )
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                await asyncio.sleep(min(self._wake_poll_interval, remaining))
                continue
            if condition is not None:
                return condition
            break
        return None

    async def _async_apply_condition(
        self, vehicle_id: str, condition: VehicleCondition
    ) -> None:
        """Merge and publish one fresh vehicle condition."""
        current = (self.data or {}).get(vehicle_id)
        if current is not None and self._is_older_condition(current, condition):
            return
        condition = self._merge_condition(vehicle_id, condition)
        vehicle = self._vehicle(vehicle_id)
        if vehicle is not None:
            condition = await self._overlay_app_comfort(vehicle, condition)
        else:
            # Without the vehicle we cannot run the REST overlay; keep the
            # glitchy S05 bits out of the published condition.
            self._guard_subsystem_warnings(vehicle_id, condition)
        condition = self._apply_optimistic_hold(vehicle_id, condition)
        latest = (self.data or {}).get(vehicle_id)
        if latest is not None and latest is not current:
            # A push replaced the base while the REST overlay was in flight.
            # Equal timestamps are common inside a one-second burst, so the
            # push that arrived later wins unless the fetched condition is
            # strictly newer.
            if (
                latest.last_updated_timestamp is None
                or condition.last_updated_timestamp is None
                or latest.last_updated_timestamp
                >= condition.last_updated_timestamp
            ):
                # Keep the push's newer MQTT fields but take the REST-only
                # fields, including a subsystem light the poll just confirmed.
                merged = self._merge_rest_only_fields(latest, condition)
                self._update_ready_window(vehicle_id, merged)
                data = dict(self.data or {})
                data[vehicle_id] = merged
                self._track_charging(data)
                self._sync_charging_read(data)
                self.async_set_updated_data(data)
                return
        self._update_ready_window(vehicle_id, condition)
        data = dict(self.data or {})
        data[vehicle_id] = condition
        self._track_charging(data)
        self._sync_charging_read(data)
        self.async_set_updated_data(data)

    async def _async_wake_and_wait(
        self,
        vehicle_id: str,
        *,
        wait_when_unconfirmed: bool = False,
        timeout: float | None = None,
    ) -> WakeResult:
        """Wake one vehicle and wait for a newer condition report.

        Returns a ``WakeResult`` so callers can distinguish a fresh report, a
        wake that was accepted but produced no report, and a wake request that
        failed. The gateway acknowledgement is unreliable while the car is
        deeply asleep (observed 2026-10-14), so a manual refresh passes
        ``wait_when_unconfirmed=True`` and lets the report decide the outcome.
        The wake cooldown is recorded as soon as the gateway accepts the wake,
        whether or not the report arrives afterwards.
        """
        timeout_seconds = self._wake_report_timeout if timeout is None else timeout
        current = (self.data or {}).get(vehicle_id)
        previous = current.last_updated_timestamp if current is not None else None
        wake_sent = False
        wake_error: DeepalError | None = None
        try:
            await self.async_wake_vehicle(vehicle_id)
        except DeepalError as err:
            wake_error = err
            _LOGGER.warning(
                "Deepal wake request failed for %s: %s", vehicle_id, err
            )
            if not wait_when_unconfirmed:
                self._record_wake_result(
                    vehicle_id,
                    WakeResult.FAILED,
                    wake_sent=False,
                    error=err,
                )
                return WakeResult.FAILED
        else:
            wake_sent = True
            self._last_wake_at[vehicle_id] = time.monotonic()

        condition = await self._async_wait_for_report(
            vehicle_id, previous, timeout=timeout_seconds
        )
        if condition is not None:
            await self._async_apply_condition(vehicle_id, condition)
            result = WakeResult.FRESH
        elif wake_sent:
            result = WakeResult.NO_REPORT
            _LOGGER.warning(
                "Deepal vehicle %s did not report fresh data within %.0f s "
                "after the wake request",
                vehicle_id,
                timeout_seconds,
            )
        else:
            result = WakeResult.FAILED

        self._record_wake_result(
            vehicle_id,
            result,
            wake_sent=wake_sent,
            timeout=timeout_seconds if wake_sent else None,
            error=wake_error if result is WakeResult.FAILED else None,
        )
        return result

    async def _async_prepare_pin_command(self, vehicle_id: str) -> None:
        """Wake a stale MQTT vehicle before a PIN-gated command.

        Best effort: a missing vehicle, a fresh report, a throttled wake or a
        wake that does not produce a new report all let the command proceed;
        only failed wake outcomes are logged. The per-vehicle wake lock
        serializes concurrent commands so they do not open duplicate MQTT
        sessions, and the throttle is re-checked inside it.
        """
        vehicle = self._vehicle(vehicle_id)
        if (
            vehicle is None
            or not self._uses_mqtt(vehicle)
            or self.client.is_sda_mqtt_vehicle(vehicle)
        ):
            return
        current = (self.data or {}).get(vehicle_id)
        previous = current.last_updated_timestamp if current is not None else None
        if self._wake_block_reason(vehicle_id, previous) is not None:
            return
        async with self._vehicle_wake_lock(vehicle_id):
            if self._wake_block_reason(vehicle_id, previous) is not None:
                return
            await self._async_wake_and_wait(
                vehicle_id, timeout=WAKE_BEFORE_COMMAND_TIMEOUT
            )

    async def async_refresh_vehicle(self, vehicle_id: str) -> WakeResult:
        """Refresh one vehicle, waking it first when its report is stale.

        MQTT vehicles are woken through the app's ``TxWakeup`` service when the
        last report is older than the stale threshold and the per-vehicle wake
        cooldown elapsed. A successful wake updates the coordinator data with
        the fresh condition, so the refresh button does not need a full poll.
        Concurrent refreshes share the per-vehicle wake lock, so a single wake
        is published per cooldown window. REST vehicles keep the signed
        condition-inquiry request.

        The charging loop does not use this path for MQTT vehicles: the live
        session already streams their charge telemetry, so it reads them without
        a wake (see :meth:`_async_read_charging_vehicle`).
        """
        vehicle = self._vehicle(vehicle_id)
        current = (self.data or {}).get(vehicle_id)
        previous = current.last_updated_timestamp if current is not None else None

        if vehicle is not None and self._uses_mqtt(vehicle):
            if self.client.is_sda_mqtt_vehicle(vehicle):
                # The app reads SDA conditions over REST and the CA-broker wake
                # is not implemented for the SDA architecture, so the refresh
                # falls through to the normal SDA condition update.
                return WakeResult.NOT_NEEDED
            reason = self._wake_block_reason(vehicle_id, previous)
            if reason is not None:
                self._record_wake_result(vehicle_id, reason, wake_sent=False)
                return reason
            async with self._vehicle_wake_lock(vehicle_id):
                reason = self._wake_block_reason(vehicle_id, previous)
                if reason is not None:
                    self._record_wake_result(
                        vehicle_id, reason, wake_sent=False
                    )
                    return reason
                return await self._async_wake_and_wait(
                    vehicle_id, wait_when_unconfirmed=True
                )
        if not isinstance(self.client, DeepalIntlClient):
            return WakeResult.NOT_NEEDED
        await self.async_condition_inquiry(vehicle_id)
        return WakeResult.NOT_NEEDED

    def _schedule_condition_inquiry(self, vehicle_id: str) -> None:
        """Nudge the vehicle for fresh data without delaying the command.

        The request forces the car to report, but awaiting it (up to the 15 s
        HTTP timeout) would delay the result polling on a busy vehicle. It is
        best-effort, so it runs as a background task tied to the entry, which
        Home Assistant cancels on unload.
        """
        self.entry.async_create_background_task(
            self.hass,
            self._async_nudge_condition(vehicle_id),
            "deepal condition nudge",
        )

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

    def _raise_rate_limited(self, err: DeepalRateLimitError) -> NoReturn:
        """Raise UpdateFailed, deferring the next refresh past the normal cadence.

        The gateway value wins when it asks for a longer wait; the configured
        scan interval and the default interval are the floor, so a rate-limited
        entry is never polled sooner than its normal cadence.
        """
        interval = (
            self.update_interval.total_seconds()
            if self.update_interval is not None
            else float(DEFAULT_SCAN_INTERVAL)
        )
        retry_after = max(
            err.retry_after or 0.0,
            interval,
            float(DEFAULT_SCAN_INTERVAL),
        )
        _LOGGER.warning(
            "Deepal rate limited; deferring the next update by %.0f s: %s",
            retry_after,
            err,
        )
        raise UpdateFailed(
            f"Deepal rate limited: {err}", retry_after=retry_after
        ) from err

    async def _async_update_data(self) -> dict[str, VehicleCondition]:
        """Fetch data from Changan Deepal API."""
        await self._async_load_snapshot()
        generations = dict(self._vehicle_generation)
        try:
            await self._async_maybe_refresh_tokens()
            data = await self._async_fetch()
        except DeepalAuthError as err:
            _LOGGER.warning("Deepal authentication failed, attempting token refresh")
            try:
                refreshed = await self._async_refresh_tokens(force=True)
            except DeepalConnectionError as refresh_err:
                raise UpdateFailed(
                    f"Error refreshing the Deepal session: {refresh_err}"
                ) from refresh_err
            if not refreshed:
                raise ConfigEntryAuthFailed("Authentication token expired") from err
            try:
                data = await self._async_fetch()
            except DeepalRateLimitError as retry_err:
                self._raise_rate_limited(retry_err)
            except DeepalAuthError as retry_err:
                raise ConfigEntryAuthFailed("Authentication token expired") from retry_err
            except DeepalError as retry_err:
                _LOGGER.error(
                    "Error communicating with Deepal API after token refresh: %s",
                    retry_err,
                )
                raise UpdateFailed(
                    f"Error fetching Deepal data: {retry_err}"
                ) from retry_err
        except DeepalRateLimitError as err:
            self._raise_rate_limited(err)
        except DeepalError as err:
            _LOGGER.error("Error communicating with Deepal API: %s", err)
            raise UpdateFailed(f"Error fetching Deepal data: {err}") from err
        for car_id, condition in list(data.items()):
            current = (self.data or {}).get(car_id)
            vehicle = self._vehicle(car_id)
            if (
                current is not None
                and vehicle is not None
                and self._uses_mqtt(vehicle)
                and (
                    self._is_older_condition(current, condition)
                    or (
                        self._vehicle_generation.get(car_id, 0)
                        != generations.get(car_id, 0)
                        and not self._is_newer_condition(current, condition)
                    )
                )
            ):
                # A push landed while the poll was in flight (possibly with the
                # same one-second timestamp): keep its MQTT fields and take the
                # poll's REST-only fields.
                data[car_id] = self._merge_rest_only_fields(current, condition)
        for car_id, condition in data.items():
            self._update_ready_window(car_id, condition)
        self._track_charging(data)
        self._sync_charging_read(data)
        # From now on the in-memory data is the previous state. A vehicle that
        # failed this poll keeps its restored condition as the fallback until a
        # poll publishes it.
        for car_id in list(self._restored):
            if car_id in data:
                del self._restored[car_id]
        self._store.async_delay_save(self._snapshot_payload, _SNAPSHOT_SAVE_DELAY)
        return data

    async def _async_load_snapshot(self) -> None:
        """Load the conditions stored before the restart, once per run."""
        if self._restored_loaded:
            return
        self._restored_loaded = True
        try:
            stored = await self._store.async_load()
        except Exception:  # noqa: BLE001 - a bad store must never block polling
            _LOGGER.debug("Deepal stored condition could not be read", exc_info=True)
            return
        self._restored = conditions_from_snapshot(VehicleCondition, stored)

    def _snapshot_payload(self) -> dict[str, Any]:
        """Return the data written to the store (the conditions last published).

        The opt-in vehicle location is only persisted while the option is on, so
        turning it off removes the coordinates from the stored condition.
        """
        options = getattr(self.entry, "options", None) or {}
        return conditions_to_snapshot(
            self.data,
            include_location=bool(
                options.get(CONF_ENABLE_LOCATION, DEFAULT_ENABLE_LOCATION)
            ),
        )

    def _charging_flag(self, car_id: str, condition: VehicleCondition) -> bool | None:
        """Return the charging flag with the vehicle's model semantics."""
        vehicle = self._vehicle(car_id)
        if uses_s05_charge_enum(vehicle, condition):
            return charging_flag(condition, True)
        return charging_flag(condition)

    def _track_charging(self, data: dict[str, VehicleCondition]) -> None:
        """Feed one telemetry snapshot into the charging-session tracker."""
        if self.charging is None:
            return
        now = datetime.now(UTC)
        for car_id, condition in data.items():
            self.charging.apply(
                car_id,
                self._charging_flag(car_id, condition),
                condition.battery.soc_percentage,
                condition.battery.remaining_range_km,
                now,
            )

    def _charging_vehicle_ids(
        self,
        data: dict[str, VehicleCondition],
    ) -> list[str]:
        """Return the vehicles that currently report an active charge."""
        return [
            car_id
            for car_id, condition in data.items()
            if self._charging_flag(car_id, condition) is True
        ]

    def _sync_charging_read(
        self, data: dict[str, VehicleCondition]
    ) -> None:
        """Start, keep or stop the charging refresh loop.

        Called on every published condition. A read from the loop itself cannot
        replace the running task: the not-done guard keeps it in place.
        """
        charging = self._charging_vehicle_ids(data)
        current = asyncio.current_task()
        if not charging:
            stop = self._charging_read_stop
            if stop is not None:
                stop.set()
            task = self._charging_read_task
            if task is not None and task is not current and not task.done():
                task.cancel()
            if task is not current:
                self._charging_read_task = None
                self._charging_read_stop = None
            return

        task = self._charging_read_task
        if task is not None and not task.done():
            return
        self._charging_read_stop = asyncio.Event()
        self._charging_read_task = self.entry.async_create_background_task(
            self.hass,
            self._async_charging_read_loop(),
            "deepal charging read",
        )
        _LOGGER.debug(
            "Deepal charging read loop started for %s",
            ", ".join(charging),
        )

    async def _async_charging_read_loop(self) -> None:
        """Read the charging vehicles every 10 minutes until charging ends."""
        stop = self._charging_read_stop
        if stop is None:
            return
        try:
            while not stop.is_set():
                try:
                    await asyncio.wait_for(
                        stop.wait(), timeout=self._charging_read_interval
                    )
                    return
                except asyncio.TimeoutError:
                    pass

                charging = self._charging_vehicle_ids(self.data or {})
                if not charging:
                    return
                for vehicle_id in charging:
                    try:
                        await self._async_read_charging_vehicle(vehicle_id)
                    except (DeepalError, HomeAssistantError) as err:
                        _LOGGER.warning(
                            "Deepal charging read failed for %s: %s",
                            vehicle_id,
                            err,
                        )
                    except Exception:  # noqa: BLE001 - one read must not kill the loop
                        _LOGGER.exception(
                            "Deepal charging read failed unexpectedly for %s",
                            vehicle_id,
                        )
                    if stop.is_set():
                        return
        finally:
            if self._charging_read_task is asyncio.current_task():
                self._charging_read_task = None
                self._charging_read_stop = None

    async def _async_read_charging_vehicle(self, vehicle_id: str) -> None:
        """Read one charging vehicle without polling the parked ones.

        An MQTT vehicle reports its charge telemetry through the live session
        every ~25 s while charging (live S05 BEV, 2026-11-21), so the loop reads
        it without waking it: the request goes over the already open session and
        the app-condition overlay still refreshes the REST-only charge plan.
        Waking it every ten minutes only cost 12 V and API quota. A vehicle
        without MQTT telemetry keeps the wake policy and the inquiry path.
        """
        vehicle = self._vehicle(vehicle_id)
        if vehicle is not None and self._uses_mqtt(vehicle):
            condition = await self._async_fetch_condition(vehicle_id)
        else:
            result = await self.async_refresh_vehicle(vehicle_id)
            if result is WakeResult.FRESH:
                return
            condition = await self._async_fetch_condition(vehicle_id)
        await self._async_apply_condition(vehicle_id, condition)

    def _vehicle_command_lock(self, vehicle_id: str) -> asyncio.Lock:
        """Return the per-vehicle command lock, creating it on first use."""
        lock = self._command_locks.get(vehicle_id)
        if lock is None:
            lock = asyncio.Lock()
            self._command_locks[vehicle_id] = lock
        return lock

    def _vehicle_wake_lock(self, vehicle_id: str) -> asyncio.Lock:
        """Return the per-vehicle wake lock, creating it on first use."""
        lock = self._wake_locks.get(vehicle_id)
        if lock is None:
            lock = asyncio.Lock()
            self._wake_locks[vehicle_id] = lock
        return lock

    def _check_command_cooldown(self, vehicle_id: str, cooldown_key: str) -> None:
        """Reject a command whose vehicle cycle is still running.

        The car refuses a repeat while it finishes the previous action; failing
        here with the remaining seconds avoids the cryptic vehicle rejection.
        """
        deadline = self._command_cooldowns.get((vehicle_id, cooldown_key))
        if deadline is None:
            return
        remaining = deadline - time.monotonic()
        if remaining > 0:
            seconds = math.ceil(remaining)
            raise HomeAssistantError(
                "The vehicle is still completing the previous command; wait "
                f"{seconds} s before repeating it",
                translation_domain=DOMAIN,
                translation_key="command_still_running",
                translation_placeholders={"seconds": str(seconds)},
            )

    def _record_command_cooldown(
        self, vehicle_id: str, cooldown_key: str | None
    ) -> None:
        """Start the cycle cooldown of a command that did not fail."""
        if cooldown_key is None:
            return
        seconds = _COMMAND_COOLDOWN_SECONDS.get(cooldown_key)
        if seconds:
            self._command_cooldowns[(vehicle_id, cooldown_key)] = (
                time.monotonic() + seconds
            )

    async def async_execute_command(
        self,
        vehicle_id: str,
        send_command: Callable[[], Awaitable[str]],
        *,
        is_done: Callable[[], bool] | None = None,
        optimistic_update: Callable[[VehicleCondition], VehicleCondition] | None = None,
        serialize: bool | None = None,
        cooldown_key: str | None = None,
        wake_first: bool = False,
        timeout: float = _COMMAND_TIMEOUT,
        interval: float = _COMMAND_RESULT_INTERVAL,
    ) -> None:
        """Send a remote command and poll until the vehicle reports new data.

        Commands that share the vehicle state (an optimistic update is given, or
        serialize=True) run one at a time per vehicle: a second one waits up to
        _COMMAND_LOCK_TIMEOUT seconds for its turn and then runs, instead of
        failing. Stateless commands (lights, horn) never wait, and commands for
        different vehicles are independent. ``cooldown_key`` gates commands the
        car is still cycling; the cooldown starts once the command is confirmed.
        ``wake_first`` wakes a stale MQTT vehicle before the command is sent,
        outside the command lock; the wake is best-effort and never blocks the
        command.
        """
        if not isinstance(self.client, DeepalIntlClient):
            raise HomeAssistantError(
                "Remote commands require the international platform",
                translation_domain=DOMAIN,
                translation_key="commands_require_international",
            )

        if cooldown_key is not None:
            self._check_command_cooldown(vehicle_id, cooldown_key)

        if wake_first:
            await self._async_prepare_pin_command(vehicle_id)

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
            self._record_command_cooldown(vehicle_id, cooldown_key)
            return

        lock = self._vehicle_command_lock(vehicle_id)
        try:
            async with asyncio.timeout(_COMMAND_LOCK_TIMEOUT):
                await lock.acquire()
        except TimeoutError as error:
            raise HomeAssistantError(
                "Another Deepal command for this vehicle is taking too long; "
                "try again in a few seconds",
                translation_domain=DOMAIN,
                translation_key="command_queue_busy",
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
            self._record_command_cooldown(vehicle_id, cooldown_key)
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

        try:
            command_id = await self._async_with_session_retry(send_command)
        except DeepalAPIError as err:
            if str(getattr(err, "code", None)) == _ASLEEP_COMMAND_ERROR_CODE:
                raise HomeAssistantError(
                    _ASLEEP_COMMAND_MESSAGE,
                    translation_domain=DOMAIN,
                    translation_key="command_asleep",
                ) from err
            raise

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
                raise _command_failure_error(result)

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
        self._optimistic_pending.pop(vehicle_id, None)
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
                raise _command_failure_error(result)

            now = loop.time()
            if now >= next_condition_at:
                condition = await self._async_fetch_condition(vehicle_id)
                # The command confirmation must not expose the unreliable MQTT
                # steering wheel field: apply the last server-authored state,
                # as the normal poll's comfort overlay does.
                vehicle = self._vehicle(vehicle_id)
                if vehicle is not None:
                    self._apply_steering_wheel_state(vehicle, condition)
                # The confirmation fetch has no REST subsystem registers, so
                # keep the glitchy MQTT bits out of the published condition.
                self._guard_subsystem_warnings(vehicle_id, condition)
                condition = self._apply_optimistic_hold(vehicle_id, condition)
                next_condition_at = now + condition_interval
                current = (self.data or {}).get(vehicle_id)
                if self._condition_is_fresh(condition, current):
                    self._update_ready_window(vehicle_id, condition)
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
