"""Model-aware charge-schedule commands shared by the service and the UI."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .deepal import DeepalError
from .vehicle_model import is_s05, is_s05_phev

_LOGGER = logging.getLogger(__name__)
# The car always lists a default plan with this id. Only observed on the S05
# PHEV, so it is only interpreted for that model.
_PLACEHOLDER_PLAN_ID = "1"
# Seconds to wait before re-reading the plan list after a delete, and between
# the delayed coordinator refreshes after an add/delete. Module level so the
# tests can set them to 0.
_DELETE_SETTLE_SECONDS = 4
_REFRESH_DELAYS = (8, 10)
# How many times the purge looks for the new plan before it gives up.
_PURGE_WAIT_ATTEMPTS = 6


def ha_gmt_offset(hass: HomeAssistant) -> str:
    """Return the current Home Assistant timezone as ``GMT+HH:MM``."""
    try:
        offset = datetime.now(ZoneInfo(hass.config.time_zone)).utcoffset()
    except Exception:  # noqa: BLE001 - a broken zone must not break the command
        return "GMT+00:00"
    if offset is None:
        return "GMT+00:00"
    minutes = int(offset.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    hours, rest = divmod(abs(minutes), 60)
    return f"GMT{sign}{hours:02d}:{rest:02d}"


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _plans(condition: Any) -> list[dict[str, Any]]:
    raw = ((condition.raw_data or {}).get("charge") or {}).get("chargePlanList")
    if not isinstance(raw, list):
        return []
    return [plan for plan in raw if isinstance(plan, dict)]


def _active_plan_ids(condition: Any, plans: list[dict[str, Any]]) -> list[str]:
    """Return active plan ids from the raw list and the normalized battery."""
    ids = {
        str(plan.get("planId"))
        for plan in plans
        if _as_int(plan.get("isValid")) == 1 and plan.get("planId") is not None
    }
    if condition is not None:
        for plan in condition.battery.charge_plans:
            if (
                _as_int(plan.get("isValid")) == 1
                and plan.get("planId") is not None
            ):
                ids.add(str(plan["planId"]))
        if condition.battery.charge_plan_valid and condition.battery.charge_plan_id:
            ids.add(str(condition.battery.charge_plan_id))
    return sorted(ids)


def _optimistic_schedule(
    start: str,
    end: str,
    enabled: bool,
    *,
    clear_plan: bool = False,
    keep_times: bool = False,
):
    """Return an optimistic update for the schedule fields.

    ``keep_times`` leaves the start and end alone. A delete must not write the
    times: the coordinator drops an unconfirmed value to unknown once the car
    stops reporting it, and the car reports no times when only the default plan
    is left, so the last times would be lost.
    """

    def _apply(condition: Any) -> Any:
        if not keep_times:
            condition.battery.charge_schedule_start = start
            condition.battery.charge_schedule_end = end
        condition.battery.charge_schedule_enabled = enabled
        condition.battery.charge_plan_valid = enabled
        if clear_plan:
            # The add-plan command returns a new plan id only through the app
            # condition. Do not keep the previous id while that condition is
            # stale: the switch-off would delete the old plan instead of the
            # new one.
            condition.battery.charge_plan_id = None
            condition.battery.charge_plans = []
        return condition

    return _apply


async def _fresh_condition(coordinator: Any, vehicle: Any) -> Any | None:
    """Fetch the app condition, which is the authoritative plan list."""
    try:
        return await coordinator.client.get_vehicle_condition(
            vehicle.car_id,
            vin=getattr(vehicle, "vin", None),
            model_code=getattr(vehicle, "model_code", None),
        )
    except DeepalError:
        return None


async def _async_delete_plan(
    coordinator: Any,
    car_id: str,
    plan_id: Any,
    start: str,
    end: str,
    *,
    optimistic: bool = True,
) -> None:
    """Delete one plan through the coordinator wake/command/refresh path.

    ``optimistic=False`` leaves the published state alone. The purge of older
    plans after an add must not mark the schedule as disabled: the new plan is
    on, and the switch would flip to "off" until the next refresh.
    """
    await coordinator.async_execute_command(
        car_id,
        lambda: coordinator.client.control_charge_plan_delete(car_id, str(plan_id)),
        optimistic_update=(
            _optimistic_schedule(start, end, False, keep_times=True)
            if optimistic
            else None
        ),
        # Deletes share the plan list, so they run one at a time per vehicle
        # even without an optimistic update.
        serialize=True,
        wake_first=True,
    )


def _stale_plan_ids(plans: list[dict[str, Any]], keep_id: Any) -> list[str]:
    """Return the ids of every real plan except the one to keep.

    Failed modify calls used to leave a new plan behind each time and the car
    switches every added plan on, so old plans pile up and stay active. The app
    shows one plan only; the placeholder plan (id 1) is never touched.
    """
    keep = str(keep_id) if keep_id else None
    return [
        str(plan["planId"])
        for plan in plans
        if plan.get("planId") is not None
        and str(plan["planId"]) not in (keep, _PLACEHOLDER_PLAN_ID)
    ][:25]


def _plan_lock(coordinator: Any) -> asyncio.Lock:
    """Return the per-coordinator lock that serializes plan deletes.

    The coordinator class does not define it, so it is created on first use.
    """
    lock = getattr(coordinator, "_deepal_plan_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        coordinator._deepal_plan_lock = lock
    return lock


def _spawn(coordinator: Any, coro: Any, name: str) -> None:
    """Run a follow-up coroutine tied to the config entry.

    A background task of the entry is cancelled when the entry unloads, which a
    plain ``hass.async_create_task`` would not do.
    """
    coordinator.config_entry.async_create_background_task(
        coordinator.hass, coro, name
    )


async def _delete_plans_verified(
    coordinator: Any,
    vehicle: Any,
    plan_ids: list[str],
    start: str,
    end: str,
    *,
    only_ids: set[str] | None = None,
    raise_errors: bool = False,
    optimistic: bool = True,
) -> None:
    """Delete plans one command at a time and re-check what the car still lists.

    A delete sent a few seconds after an add can be ignored by the car, and two
    overlapping delete runs confuse it, so every run waits for the previous one.
    """
    async with _plan_lock(coordinator):
        ids = list(plan_ids)
        for attempt in range(3):
            for plan_id in ids:
                try:
                    await _async_delete_plan(
                        coordinator,
                        vehicle.car_id,
                        plan_id,
                        start,
                        end,
                        optimistic=optimistic,
                    )
                except (HomeAssistantError, DeepalError) as err:
                    if raise_errors and attempt == 0:
                        raise
                    _LOGGER.warning(
                        "Deepal could not delete the charge plan %s: %s", plan_id, err
                    )
            await asyncio.sleep(_DELETE_SETTLE_SECONDS)
            fresh = await _fresh_condition(coordinator, vehicle)
            if fresh is None:
                return
            ids = _stale_plan_ids(_plans(fresh), None)
            if only_ids is not None:
                ids = [i for i in ids if i in only_ids]
            if not ids:
                return
        _LOGGER.warning(
            "Deepal: the car still lists the charge plan(s) %s after 3 attempts",
            ", ".join(ids),
        )


async def _refresh_later(coordinator: Any) -> None:
    """Re-read the car after an add/delete settles.

    The refresh right after a command still sees the old plan list, which made
    the switch show "off" until the next poll although the plan was on.
    """
    for delay in _REFRESH_DELAYS:
        await asyncio.sleep(delay)
        try:
            await coordinator.async_request_refresh()
        except Exception:  # noqa: BLE001 - a refresh must never fail the command
            _LOGGER.debug("Deepal refresh after the plan change failed")


def _purge_other_plans(
    coordinator: Any,
    vehicle: Any,
    plans: list[dict[str, Any]],
    keep_id: Any,
    start: str,
    end: str,
) -> None:
    """Delete the stale plans in the background; a failure only logs."""
    stale = _stale_plan_ids(plans, keep_id)
    if not stale:
        return
    _spawn(
        coordinator,
        _purge_after_add(coordinator, vehicle, stale, start, end),
        "deepal_purge_charge_plans",
    )


async def _purge_after_add(
    coordinator: Any,
    vehicle: Any,
    stale: list[str],
    start: str,
    end: str,
) -> None:
    """Delete the older plans only once the car lists the new one.

    The car applies the add a few seconds after it accepts the command. A delete
    sent before that left the car with the default plan only: the switch fell to
    "off" until the new plan showed up, and a lost add would have removed the
    schedule altogether. So the older plans stay until a plan that is neither
    one of them nor the default plan appears in the car's list.
    """
    old = set(stale)
    for _ in range(_PURGE_WAIT_ATTEMPTS):
        await asyncio.sleep(_DELETE_SETTLE_SECONDS)
        fresh = await _fresh_condition(coordinator, vehicle)
        if fresh is None:
            continue
        listed = {
            str(plan["planId"])
            for plan in _plans(fresh)
            if plan.get("planId") is not None
        }
        if listed - old - {_PLACEHOLDER_PLAN_ID}:
            await _delete_plans_verified(
                coordinator,
                vehicle,
                stale,
                start,
                end,
                only_ids=old,
                optimistic=False,
            )
            return
    _LOGGER.warning(
        "Deepal: the car did not list the new charge plan, so the older plan(s) %s "
        "were kept",
        ", ".join(stale),
    )


async def _async_set_phev_schedule(
    coordinator: Any,
    vehicle: Any,
    plans: list[dict[str, Any]],
    start: str,
    end: str,
    enabled: bool,
    command_time_zone: str,
) -> str:
    """Set or remove the charge reservation of an S05 PHEV.

    The car rejects modify-plan and the plan on/off command, so a plan either
    exists or it does not. On or a time change adds a plan with the times and
    then removes the older real plans; off deletes every real plan. The
    placeholder plan is never touched.
    """
    client = coordinator.client

    if enabled:
        await coordinator.async_execute_command(
            vehicle.car_id,
            lambda: client.control_charge_plan_add(
                vehicle.car_id, start, end, 1, 1, 1, command_time_zone
            ),
            optimistic_update=_optimistic_schedule(
                start, end, True, clear_plan=True
            ),
            wake_first=True,
        )
        _purge_other_plans(coordinator, vehicle, plans, None, start, end)
        _spawn(coordinator, _refresh_later(coordinator), "deepal_refresh_after_plan")
        return "add-plan"

    real_ids = _stale_plan_ids(plans, None)
    if not real_ids:
        # Nothing to switch off. Keep the chosen times for the next "on"
        # without sending a command to the car.
        data = coordinator.data or {}
        current = data.get(vehicle.car_id)
        if current is not None:
            _optimistic_schedule(start, end, False)(current)
            coordinator.async_set_updated_data(data)
        return "noop"
    try:
        await _delete_plans_verified(
            coordinator, vehicle, real_ids, start, end, raise_errors=True
        )
    except (HomeAssistantError, DeepalError) as err:
        # Never fall through to add-plan here: it would create an enabled plan
        # instead of switching the schedule off.
        raise HomeAssistantError(
            f"Could not switch off the charge schedule: {err}"
        ) from err
    _spawn(coordinator, _refresh_later(coordinator), "deepal_refresh_after_plan")
    return "delete-plan"


async def async_set_charge_schedule(
    coordinator: Any,
    vehicle: Any,
    start: str,
    end: str,
    enabled: bool | None,
    time_zone: str,
    *,
    wait_for_plan: bool = False,
    toggle_only: bool = False,
) -> tuple[str, str]:
    """Set, update or remove the charge reservation of one vehicle.

    Returns the strategy used and the effective command timezone. The plan's
    own ``timeZone`` wins; the Home Assistant zone is the fallback when the car
    does not report one. The S05 PHEV uses ``add-plan``/``delete-plan`` (see
    ``_async_set_phev_schedule``), other international models keep
    ``modify-plan``, and the S05 BEV ``add-plan``/``delete-plan``.

    ``enabled=None`` keeps the state the car reports: the newest real plan for
    the PHEV, the coordinator state for the other models.
    """
    client = coordinator.client
    stored = (coordinator.data or {}).get(vehicle.car_id)
    condition = stored
    fresh = await _fresh_condition(coordinator, vehicle)
    if fresh is not None:
        # The app condition is the authoritative plan list. The coordinator's
        # snapshot can lag behind an add-plan, and using its stale plan id made
        # the switch delete the previous plan instead of the new one.
        condition = fresh
    plans = _plans(condition) if condition is not None else []
    phev = is_s05_phev(vehicle)
    if enabled is None:
        if phev:
            newest = plans[0] if plans else {}
            enabled = (
                _as_int(newest.get("isValid")) == 1
                and str(newest.get("planId")) != _PLACEHOLDER_PLAN_ID
            )
        else:
            enabled = bool(
                condition.battery.charge_schedule_enabled
                if condition is not None
                else True
            )
    plan_time_zone = (
        condition.battery.charge_plan_time_zone
        if condition is not None
        else None
    )
    command_time_zone = plan_time_zone or time_zone
    try:
        if phev:
            strategy = await _async_set_phev_schedule(
                coordinator, vehicle, plans, start, end, enabled, command_time_zone
            )
            return strategy, command_time_zone
        if not is_s05(vehicle):
            plan_id = condition.battery.charge_plan_id if condition else None
            if not plan_id and stored is not None:
                plan_id = stored.battery.charge_plan_id
            async def _add_plan() -> None:
                await coordinator.async_execute_command(
                    vehicle.car_id,
                    lambda: client.control_charge_plan_add(
                        vehicle.car_id,
                        start,
                        end,
                        1 if enabled else 0,
                        1,
                        1,
                        command_time_zone,
                    ),
                    optimistic_update=_optimistic_schedule(
                        start, end, enabled, clear_plan=True
                    ),
                    wake_first=True,
                )

            if plan_id and (toggle_only or not enabled):
                # Local patch: the switch only flips the plan on or off, so use
                # the dedicated validity command; fall back to modify/add below.
                try:
                    await coordinator.async_execute_command(
                        vehicle.car_id,
                        lambda: client.control_charge_plan_validity(
                            vehicle.car_id, str(plan_id), enabled
                        ),
                        optimistic_update=_optimistic_schedule(start, end, enabled),
                        wake_first=True,
                    )
                    return "plan-validity", command_time_zone
                except (HomeAssistantError, DeepalError):
                    pass
                if not enabled:
                    # The car ignores end-switch 0 on modify/add, so removing
                    # the plan is the reliable way to switch it off.
                    try:
                        await _async_delete_plan(
                            coordinator,
                            vehicle.car_id,
                            plan_id,
                            start,
                            end,
                        )
                        return "delete-plan", command_time_zone
                    except (HomeAssistantError, DeepalError) as err:
                        # Never fall through to add-plan here: it would create
                        # an enabled plan instead of switching it off.
                        raise HomeAssistantError(
                            f"Could not switch off the charge schedule: {err}"
                        ) from err

            if plan_id:
                strategy = "modify-plan"
                try:
                    await coordinator.async_execute_command(
                        vehicle.car_id,
                        lambda: client.control_charge_schedule(
                            vehicle.car_id,
                            str(plan_id),
                            start,
                            end,
                            enabled,
                            1,
                            1,
                            command_time_zone,
                        ),
                        optimistic_update=_optimistic_schedule(start, end, enabled),
                        wake_first=True,
                    )
                except (HomeAssistantError, DeepalError):
                    # Local patch: some PHEVs only hold a placeholder plan
                    # (no end time) that modify-plan rejects with
                    # HW_1_1_01_001. Fall back to adding a plan.
                    strategy = "add-plan"
                    await _add_plan()
            else:
                strategy = "add-plan"
                await _add_plan()
            return strategy, command_time_zone

        active_plan_ids = _active_plan_ids(condition, plans)
        if not active_plan_ids and not enabled and wait_for_plan:
            # A switch-off issued right after an add can arrive before the app
            # condition exposes the new plan id. Poll the app condition for a
            # short window instead of leaving the freshly added plan active.
            for _ in range(6):
                await asyncio.sleep(5)
                fresh = await _fresh_condition(coordinator, vehicle)
                if fresh is None:
                    continue
                condition = fresh
                plans = _plans(condition)
                active_plan_ids = _active_plan_ids(condition, plans)
                if active_plan_ids:
                    break

        current_start = (
            condition.battery.charge_schedule_start or start
            if condition is not None
            else start
        )
        current_end = (
            condition.battery.charge_schedule_end or end
            if condition is not None
            else end
        )
        for plan_id in active_plan_ids:
            await _async_delete_plan(
                coordinator,
                vehicle.car_id,
                plan_id,
                current_start,
                current_end,
            )
        if enabled:
            strategy = "add-plan"
            await coordinator.async_execute_command(
                vehicle.car_id,
                lambda: client.control_charge_plan_add(
                    vehicle.car_id,
                    start,
                    end,
                    1,
                    1,
                    1,
                    command_time_zone,
                ),
                optimistic_update=_optimistic_schedule(
                    start, end, True, clear_plan=True
                ),
                wake_first=True,
            )
        else:
            strategy = "delete-plan"
        return strategy, command_time_zone
    except HomeAssistantError:
        raise
    except DeepalError as err:
        raise HomeAssistantError(
            f"Deepal charge schedule command failed: {err}",
            translation_domain=DOMAIN,
            translation_key="command_failed",
            translation_placeholders={"error": str(err)},
        ) from err
