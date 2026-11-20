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
) -> None:
    """Delete one plan through the coordinator wake/command/refresh path."""
    try:
        await coordinator.async_execute_command(
            car_id,
            lambda: coordinator.client.control_charge_plan_delete(car_id, str(plan_id)),
            optimistic_update=_optimistic_schedule(
                start, end, False, keep_times=True
            ),
            wake_first=True,
        )
    except Exception as err:  # noqa: BLE001
        raise


_LOGGER = logging.getLogger(__name__)
_PLACEHOLDER_PLAN_ID = "1"


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


async def _delete_plans_verified(
    coordinator: Any,
    vehicle: Any,
    plan_ids: list[str],
    start: str,
    end: str,
    *,
    only_ids: set[str] | None = None,
    raise_errors: bool = False,
) -> None:
    """Delete plans one command at a time and re-check what the car still lists.

    A delete sent a few seconds after an add can be ignored by the car, and two
    overlapping delete runs confuse it, so every run waits for the previous one.
    """
    lock = getattr(coordinator, "_deepal_plan_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        try:
            coordinator._deepal_plan_lock = lock
        except AttributeError:
            pass
    async with lock:
        ids = list(plan_ids)
        for attempt in range(3):
            for plan_id in ids:
                try:
                    await _async_delete_plan(
                        coordinator, vehicle.car_id, plan_id, start, end
                    )
                except (HomeAssistantError, DeepalError) as err:
                    if raise_errors and attempt == 0:
                        raise
                    _LOGGER.warning(
                        "Deepal could not delete the charge plan %s: %s", plan_id, err
                    )
            await asyncio.sleep(4)
            fresh = await _fresh_condition(coordinator, vehicle)
            if fresh is None:
                return
            ids = _stale_plan_ids(_plans(fresh), None)
            if only_ids is not None:
                ids = [i for i in ids if i in only_ids]
            if not ids:
                return


async def _refresh_later(coordinator: Any) -> None:
    """Re-read the car after an add/delete settles.

    The refresh right after a command still sees the old plan list, which made
    the switch show "off" until the next poll although the plan was on.
    """
    for delay in (8, 10):
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
    coordinator.hass.async_create_task(
        _delete_plans_verified(
            coordinator, vehicle, stale, start, end, only_ids=set(stale)
        ),
        "deepal_purge_charge_plans",
    )


async def _async_set_charge_schedule(
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
    does not report one. ``modify-plan`` is used for the PHEV and other
    international models, ``add-plan``/``delete-plan`` for the S05 BEV.
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
    if enabled is None:
        newest = plans[0] if plans else {}
        enabled = (
            _as_int(newest.get("isValid")) == 1
            and str(newest.get("planId")) != _PLACEHOLDER_PLAN_ID
        )
    plan_time_zone = (
        condition.battery.charge_plan_time_zone
        if condition is not None
        else None
    )
    command_time_zone = plan_time_zone or time_zone
    try:
        if is_s05_phev(vehicle) or not is_s05(vehicle):
            phev = is_s05_phev(vehicle)
            plan_id = condition.battery.charge_plan_id if condition else None
            if not plan_id and stored is not None:
                plan_id = stored.battery.charge_plan_id
            if plan_id is not None and str(plan_id) == _PLACEHOLDER_PLAN_ID:
                plan_id = None  # the placeholder is not a plan to switch or modify

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

            if not phev:
                # Other international models: modify the plan, or add one.
                if plan_id:
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
                    return "modify-plan", command_time_zone
                if not enabled:
                    # There is no plan to disable, and the car treats any added
                    # plan as active: send nothing instead of turning it on.
                    return "noop", command_time_zone
                await _add_plan()
                return "add-plan", command_time_zone

            # S05 PHEV: the car rejects modify-plan and the plan on/off command,
            # so a plan exists or it does not. On = add a plan with the times
            # (then remove the older ones); off = delete the plan(s).
            real_ids = _stale_plan_ids(plans, None)
            if not enabled:
                if not real_ids:
                    # Nothing to switch off. Keep the chosen times for the next
                    # "on" without sending a command to the car.
                    try:
                        data = coordinator.data or {}
                        current = data.get(vehicle.car_id)
                        if current is not None:
                            _optimistic_schedule(start, end, False)(current)
                            coordinator.async_set_updated_data(data)
                    except Exception:  # noqa: BLE001
                        _LOGGER.debug("Deepal could not keep the chosen times")
                    return "noop", command_time_zone
                await _delete_plans_verified(
                    coordinator, vehicle, real_ids, start, end, raise_errors=True
                )
                coordinator.hass.async_create_task(
                    _refresh_later(coordinator), "deepal_refresh_after_plan"
                )
                return "delete-plan", command_time_zone
            await _add_plan()
            _purge_other_plans(coordinator, vehicle, plans, None, start, end)
            coordinator.hass.async_create_task(
                _refresh_later(coordinator), "deepal_refresh_after_plan"
            )
            return "add-plan", command_time_zone

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
    """Set the charge schedule and record the outcome in the plan log."""
    try:
        result = await _async_set_charge_schedule(
            coordinator,
            vehicle,
            start,
            end,
            enabled,
            time_zone,
            wait_for_plan=wait_for_plan,
            toggle_only=toggle_only,
        )
    except Exception as err:  # noqa: BLE001
        raise
    return result
