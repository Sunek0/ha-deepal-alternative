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
from .deepal import DeepalAPIError, DeepalError, DeepalRateLimitError
from .vehicle_model import is_s05, is_s05_phev

_LOGGER = logging.getLogger(__name__)


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
    if condition is None:
        return []
    raw = ((condition.raw_data or {}).get("charge") or {}).get("chargePlanList")
    if not isinstance(raw, list):
        raw = getattr(getattr(condition, "battery", None), "charge_plans", None)
    if not isinstance(raw, list):
        return []
    return [plan for plan in raw if isinstance(plan, dict)]


def _has_value(value: Any) -> bool:
    """Return whether a plan field carries a real value."""
    return value is not None and str(value).strip() != ""


def _is_usable_plan(plan: dict[str, Any]) -> bool:
    """Return whether ``modify-plan`` can address the reported plan.

    The S05 PHEV reports a placeholder plan (``planId 1``, ``isValid 0``,
    ``startTime`` only) until a real reservation exists. Modifying it fails
    with ``HW_1_1_01_001``; the car needs ``add-plan`` instead.
    """
    if plan.get("planId") is None:
        return False
    return _has_value(plan.get("endTime")) or (
        _as_int(plan.get("endSwitch")) is not None
    )


def _plan_id_for_modify(condition: Any, stored: Any) -> str | None:
    """Return the plan id to modify, or ``None`` when the car needs an add.

    A plan id without plan details is kept so a car that does not report the
    plan list keeps the previous ``modify-plan`` behavior. The stored snapshot
    is used only when the fresh condition carries no plan id at all.
    """
    if condition is None:
        return None
    plan_id = condition.battery.charge_plan_id
    if not plan_id:
        stored_id = stored.battery.charge_plan_id if stored is not None else None
        return str(stored_id) if stored_id else None
    plan = next(
        (
            plan
            for plan in _plans(condition)
            if plan.get("planId") is not None and str(plan["planId"]) == str(plan_id)
        ),
        None,
    )
    if plan is not None and not _is_usable_plan(plan):
        return None
    return str(plan_id)


def _is_plan_command_failure(err: DeepalError) -> bool:
    """Return whether a plan command failed without an auth or rate-limit cause.

    A rejected command comes back as a generic ``DeepalAPIError`` (for example
    ``HW_1_1_01_001``). Authentication errors have their own class, and a
    rate-limit error must reach the caller instead of triggering more commands.
    """
    return isinstance(err, DeepalAPIError) and not isinstance(
        err, DeepalRateLimitError
    )


def _reported_plan_id(condition: Any, stored: Any) -> str | None:
    """Return the plan id the car reports, preferring the fresh condition."""
    plan_id = condition.battery.charge_plan_id if condition is not None else None
    if not plan_id and stored is not None:
        plan_id = stored.battery.charge_plan_id
    return str(plan_id) if plan_id else None


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
    start: str, end: str, enabled: bool, *, clear_plan: bool = False
):
    """Return an optimistic update for the schedule fields."""

    def _apply(condition: Any) -> Any:
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
    await coordinator.async_execute_command(
        car_id,
        lambda: coordinator.client.control_charge_plan_delete(car_id, str(plan_id)),
        optimistic_update=_optimistic_schedule(start, end, False),
        wake_first=True,
    )


async def _async_add_plan(
    coordinator: Any,
    car_id: str,
    start: str,
    end: str,
    enabled: bool,
    time_zone: str,
) -> None:
    """Create a charge plan with the requested times and end switch."""
    await coordinator.async_execute_command(
        car_id,
        lambda: coordinator.client.control_charge_plan_add(
            car_id,
            start,
            end,
            1 if enabled else 0,
            1,
            1,
            time_zone,
        ),
        optimistic_update=_optimistic_schedule(start, end, enabled, clear_plan=True),
        wake_first=True,
    )


async def _async_toggle_plan(
    coordinator: Any,
    car_id: str,
    plan_id: Any,
    start: str,
    end: str,
    enabled: bool,
) -> None:
    """Enable or disable a plan without changing its times."""
    await coordinator.async_execute_command(
        car_id,
        lambda: coordinator.client.control_charge_plan_validity(
            car_id, str(plan_id), enabled
        ),
        optimistic_update=_optimistic_schedule(start, end, enabled),
        wake_first=True,
    )


async def _async_disable_plan(
    coordinator: Any,
    car_id: str,
    plan_id: Any,
    start: str,
    end: str,
) -> None:
    """Delete a plan after the car rejected the disable command.

    A rejected disable must not leave the plan active, and adding a plan would
    not switch it off. When the delete also fails the caller gets one
    translated error instead of a half-applied schedule.
    """
    try:
        await _async_delete_plan(coordinator, car_id, plan_id, start, end)
    except (HomeAssistantError, DeepalError) as err:
        raise HomeAssistantError(
            f"Could not switch off the Deepal charge schedule: {err}",
            translation_domain=DOMAIN,
            translation_key="command_failed",
            translation_placeholders={"error": str(err)},
        ) from err


async def async_set_charge_schedule(
    coordinator: Any,
    vehicle: Any,
    start: str,
    end: str,
    enabled: bool,
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

    On the PHEV a placeholder plan without an end time/switch is not
    modifiable, so the reservation is created with ``add-plan``. On the PHEV
    the plan on/off command is tried first when disabling or when
    ``toggle_only`` is set (the switch), and a failed disable deletes the plan
    instead of adding one. A rejected ``modify-plan`` falls back to
    ``add-plan`` when enabling. The returned strategy is ``modify-plan``,
    ``add-plan``, ``plan-validity``, ``delete-plan`` or ``noop``.
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
    plan_time_zone = (
        condition.battery.charge_plan_time_zone
        if condition is not None
        else None
    )
    command_time_zone = plan_time_zone or time_zone
    try:
        if is_s05_phev(vehicle) or not is_s05(vehicle):
            phev = is_s05_phev(vehicle)
            plan_id = (
                _plan_id_for_modify(condition, stored)
                if phev
                else _reported_plan_id(condition, stored)
            )
            if plan_id is None:
                if not enabled:
                    # There is no plan to disable, and the car may treat any
                    # added plan as active: send nothing instead of turning it
                    # on.
                    return "noop", command_time_zone
                await _async_add_plan(
                    coordinator,
                    vehicle.car_id,
                    start,
                    end,
                    enabled,
                    command_time_zone,
                )
                return "add-plan", command_time_zone

            if phev and toggle_only:
                # The switch only flips the plan on/off, so use the dedicated
                # command first: the car may ignore ``endSwitch`` 0 on modify.
                try:
                    await _async_toggle_plan(
                        coordinator,
                        vehicle.car_id,
                        plan_id,
                        start,
                        end,
                        enabled,
                    )
                except DeepalAPIError as err:
                    if not _is_plan_command_failure(err):
                        raise
                    _LOGGER.debug(
                        "Deepal plan on/off rejected for %s (plan %s): %s",
                        vehicle.car_id,
                        plan_id,
                        err,
                    )
                else:
                    return "plan-validity", command_time_zone
                if not enabled:
                    # Switching off must end with no active plan: delete it if
                    # the on/off command was rejected. Never add a plan here,
                    # because a new plan would be created active.
                    await _async_disable_plan(
                        coordinator,
                        vehicle.car_id,
                        plan_id,
                        start,
                        end,
                    )
                    return "delete-plan", command_time_zone

            try:
                await coordinator.async_execute_command(
                    vehicle.car_id,
                    lambda: client.control_charge_schedule(
                        vehicle.car_id,
                        plan_id,
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
            except DeepalAPIError as err:
                if not (phev and _is_plan_command_failure(err)):
                    raise
                _LOGGER.debug(
                    "Deepal modify-plan rejected for %s (plan %s): %s",
                    vehicle.car_id,
                    plan_id,
                    err,
                )
                if not enabled:
                    # A rejected disable must not leave the plan active, and a
                    # new add-plan would not switch it off.
                    await _async_disable_plan(
                        coordinator,
                        vehicle.car_id,
                        plan_id,
                        start,
                        end,
                    )
                    return "delete-plan", command_time_zone
                # Some PHEVs only hold a placeholder plan (no end time) that
                # modify-plan rejects with HW_1_1_01_001. Add a real plan.
                await _async_add_plan(
                    coordinator,
                    vehicle.car_id,
                    start,
                    end,
                    enabled,
                    command_time_zone,
                )
                return "add-plan", command_time_zone
            return "modify-plan", command_time_zone

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
