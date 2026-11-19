"""Model-aware charge-schedule commands shared by the service and the UI."""

from __future__ import annotations

import asyncio
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
