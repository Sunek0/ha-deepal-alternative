"""Diagnostics support for the Deepal Alternative integration.

The report is meant to make telemetry discovery possible from Home Assistant
alone: it contains the mapped telemetry, the raw payloads the vehicle sent and
the MQTT parameters no entity consumes yet. Credentials, personal identifiers
and location-like values are redacted case-insensitively at any depth, and the
device segment of MQTT topics is masked.
"""

from __future__ import annotations

import re
from typing import Any

from homeassistant.components.diagnostics import REDACTED
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CAC_TOKEN,
    CONF_CONTROL_PIN,
    CONF_DEVICE_ID,
    CONF_EMAIL,
    CONF_PHONE,
    CONF_PRIVATE_KEY,
    CONF_REFRESH_TOKEN,
    CONF_USER_ID,
)
from .deepal import VehicleCondition
from .deepal.mqtt import unmapped_s05_keys
from .runtime_data import DeepalConfigEntry

#: Exact report keys that are always redacted. Compared without distinguishing
#: case, underscores or dashes, so `Lat`, `plateNumber` or `deviceDID` collapse
#: to their canonical spelling before the lookup.
_SENSITIVE_EXACT_KEYS = {
    CONF_ACCESS_TOKEN,
    CONF_CAC_TOKEN,
    CONF_CONTROL_PIN,
    CONF_DEVICE_ID,
    CONF_EMAIL,
    CONF_PHONE,
    CONF_PRIVATE_KEY,
    CONF_REFRESH_TOKEN,
    CONF_USER_ID,
    "address",
    "authcode",
    "devicedid",
    "deviceid",
    "gps",
    "imageurl",
    "imgurl",
    "licenseplate",
    "latitude",
    "lat",
    "longitude",
    "lon",
    "lng",
    "platenumber",
    "position",
    "pubkey",
    "rctoken",
    "safecode",
    "serialno",
    "seriralno",
    "thumbnailurl",
    "userid",
    "vehicleid",
    "vehiclevin",
    "vin",
    "vincode",
}

#: Name fragments that mark a key as sensitive even when its exact spelling is
#: new. Matched against the compacted (case, underscore and dash insensitive)
#: key. Deliberately does not include "key" or "vin": they appear inside
#: innocent names such as "unlockKeyDrivingStatus".
_SENSITIVE_KEY_PARTS = (
    "authorization",
    "bearer",
    "email",
    "latitude",
    "longitude",
    "mobile",
    "password",
    "phone",
    "pin",
    "plate",
    "private",
    "serial",
    "token",
)

#: `$vdp/<did>/...` MQTT topic strings: the device segment is masked wherever a
#: topic appears in the report.
_VDP_TOPIC = re.compile(r"^\$vdp/[^/]+")


def _is_sensitive_key(key: Any) -> bool:
    """Return whether a report key must be redacted, without distinguishing case."""
    normalized = str(key).lower().replace("-", "_")
    compact = normalized.replace("_", "")
    return (
        normalized in _SENSITIVE_EXACT_KEYS
        or compact in _SENSITIVE_EXACT_KEYS
        or any(part in compact for part in _SENSITIVE_KEY_PARTS)
    )


def _redact_string(value: str) -> str:
    """Mask the device segment of an MQTT topic string, leaving other text intact."""
    if _VDP_TOPIC.match(value):
        return _VDP_TOPIC.sub(f"$vdp/{REDACTED}", value, count=1)
    return value


def _redact(value: Any) -> Any:
    """Return a redacted, report-safe copy of ``value``."""
    if isinstance(value, dict):
        return {
            key: REDACTED if _is_sensitive_key(key) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return _redact_string(value)
    return value


def _vehicle_data(vehicle: Any) -> dict[str, Any]:
    """Serialize one vehicle summary."""
    return {
        "car_id": vehicle.car_id,
        "vin": vehicle.vin,
        "series_name": vehicle.series_name,
        "series_code": vehicle.series_code,
        "model_name": vehicle.model_name,
        "model_code": vehicle.model_code,
        "car_name": vehicle.car_name,
        "license_plate": vehicle.license_plate,
        "thumbnail_url": vehicle.thumbnail_url,
        "protocol_type": vehicle.protocol_type,
    }


def _condition_dump(condition: VehicleCondition) -> dict[str, Any]:
    """Serialize a condition without duplicating the raw payload sections."""
    return condition.model_dump(
        mode="json", exclude={"raw_data", "mqtt_raw_data", "mqtt_variants", "sda_plan"}
    )


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: DeepalConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a Deepal config entry."""
    coordinator = entry.runtime_data.coordinator
    conditions: dict[str, VehicleCondition] = coordinator.data or {}

    capabilities: dict[str, Any] = {}
    for vehicle in coordinator.vehicles:
        vehicle_capabilities = coordinator.vehicle_capabilities(vehicle.car_id)
        capabilities[vehicle.car_id] = (
            vehicle_capabilities.model_dump(mode="json")
            if vehicle_capabilities is not None
            else None
        )

    report = {
        "vehicles": [_vehicle_data(vehicle) for vehicle in coordinator.vehicles],
        "config_entry_data": dict(entry.data),
        "config_entry_options": dict(entry.options),
        "capabilities": capabilities,
        "mapped_telemetry": {
            car_id: _condition_dump(condition)
            for car_id, condition in conditions.items()
        },
        "raw_rest": {
            car_id: condition.raw_data for car_id, condition in conditions.items()
        },
        "raw_mqtt": {
            car_id: condition.mqtt_raw_data
            for car_id, condition in conditions.items()
        },
        "raw_sda": {
            car_id: condition.mqtt_raw_data
            for car_id, condition in conditions.items()
            if condition.condition_source == "sda-rest"
        },
        "condition_sources": {
            car_id: condition.condition_source
            for car_id, condition in conditions.items()
        },
        "raw_mqtt_variants": {
            car_id: condition.mqtt_variants
            for car_id, condition in conditions.items()
            if condition.mqtt_variants is not None
        },
        "sda_plans": {
            car_id: condition.sda_plan
            for car_id, condition in conditions.items()
            if condition.sda_plan is not None
        },
        "mqtt_attempts": {
            vehicle.car_id: coordinator.mqtt_attempt(vehicle.car_id)
            for vehicle in coordinator.vehicles
            if coordinator.mqtt_attempt(vehicle.car_id) is not None
        },
        "unmapped_mqtt_keys": {
            car_id: sorted(unmapped_s05_keys(condition.mqtt_raw_data or {}))
            for car_id, condition in conditions.items()
            if condition.mqtt_raw_data
        },
    }
    return _redact(report)
