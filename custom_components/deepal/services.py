"""Services for the Deepal Alternative integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .charge_schedule import async_set_charge_schedule, ha_gmt_offset
from .const import DOMAIN
from .deepal import DeepalIntlClient
from .runtime_data import DeepalRuntimeData
from .vehicle_model import is_s05

SERVICE_SET_CHARGE_SCHEDULE = "set_charge_schedule"

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_VEHICLE_ID = "vehicle_id"
ATTR_START_TIME = "start_time"
ATTR_END_TIME = "end_time"
ATTR_ENABLED = "enabled"

SET_CHARGE_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_VEHICLE_ID): cv.string,
        vol.Required(ATTR_START_TIME): cv.string,
        vol.Required(ATTR_END_TIME): cv.string,
        vol.Optional(ATTR_ENABLED, default=True): cv.boolean,
    }
)


def _normalize_time(value: Any) -> str:
    """Return the wire ``HHMM`` value or raise a translated validation error."""
    text = str(value).strip().replace(":", "")
    if len(text) != 4 or not text.isdigit():
        raise ServiceValidationError(
            "Invalid charge schedule time",
            translation_domain=DOMAIN,
            translation_key="invalid_charge_schedule_time",
            translation_placeholders={"value": str(value)},
        )
    hours, minutes = int(text[:2]), int(text[2:])
    if hours > 23 or minutes > 59:
        raise ServiceValidationError(
            "Invalid charge schedule time",
            translation_domain=DOMAIN,
            translation_key="invalid_charge_schedule_time",
            translation_placeholders={"value": str(value)},
        )
    return text


def _resolve_target(
    hass: HomeAssistant, data: dict[str, Any]
) -> tuple[ConfigEntry, DeepalRuntimeData, Any]:
    """Return the Deepal entry, runtime and vehicle targeted by the call."""
    entry_id = data.get(ATTR_CONFIG_ENTRY_ID)
    vehicle_id = data.get(ATTR_VEHICLE_ID)
    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if isinstance(getattr(entry, "runtime_data", None), DeepalRuntimeData)
        and isinstance(entry.runtime_data.client, DeepalIntlClient)
        and (not entry_id or entry.entry_id == entry_id)
    ]
    candidates: list[tuple[ConfigEntry, DeepalRuntimeData, Any]] = []
    for entry in entries:
        runtime: DeepalRuntimeData = entry.runtime_data
        for vehicle in runtime.coordinator.vehicles:
            if vehicle_id and vehicle.car_id != vehicle_id:
                continue
            candidates.append((entry, runtime, vehicle))
    if not candidates:
        raise ServiceValidationError(
            "No Deepal vehicle matches the target",
            translation_domain=DOMAIN,
            translation_key="charge_schedule_no_target",
        )
    if len(candidates) > 1:
        raise ServiceValidationError(
            "Several Deepal vehicles match the target; pass config_entry_id or vehicle_id",
            translation_domain=DOMAIN,
            translation_key="charge_schedule_multiple_targets",
        )
    return candidates[0]


async def _async_handle_set_charge_schedule(call: ServiceCall) -> ServiceResponse:
    """Create, update or remove a vehicle charge reservation."""
    hass = call.hass
    start = _normalize_time(call.data[ATTR_START_TIME])
    end = _normalize_time(call.data[ATTR_END_TIME])
    enabled = bool(call.data[ATTR_ENABLED])

    entry, runtime, vehicle = _resolve_target(hass, call.data)
    if not is_s05(vehicle):
        raise ServiceValidationError(
            "The charge schedule is only supported on the S05",
            translation_domain=DOMAIN,
            translation_key="charge_schedule_unsupported",
        )

    strategy, effective_time_zone = await async_set_charge_schedule(
        runtime.coordinator,
        vehicle,
        start,
        end,
        enabled,
        ha_gmt_offset(hass),
        wait_for_plan=not enabled,
    )

    return {
        "config_entry_id": entry.entry_id,
        "vehicle_id": vehicle.car_id,
        "strategy": strategy,
        "start_time": start,
        "end_time": end,
        "enabled": enabled,
        "time_zone": effective_time_zone,
    }


async def async_register_services(hass: HomeAssistant) -> None:
    """Register the Deepal services once per Home Assistant instance."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_CHARGE_SCHEDULE):
        return
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_CHARGE_SCHEDULE,
        _async_handle_set_charge_schedule,
        schema=SET_CHARGE_SCHEDULE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
