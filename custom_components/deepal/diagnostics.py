"""Diagnostics support for the Deepal Alternative integration.

The report is meant to make telemetry discovery possible from Home Assistant
alone: it contains the mapped telemetry, the raw payloads the vehicle sent and
the MQTT parameters no entity consumes yet. Credentials, personal identifiers
and location-like values are redacted.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
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

TO_REDACT = {
    CONF_ACCESS_TOKEN,
    CONF_CAC_TOKEN,
    CONF_CONTROL_PIN,
    CONF_DEVICE_ID,
    CONF_EMAIL,
    CONF_PHONE,
    CONF_PRIVATE_KEY,
    CONF_REFRESH_TOKEN,
    CONF_USER_ID,
    "vin",
    "thumbnail_url",
    "image_url",
    "imgUrl",
    "vehicle_id",
    # Location-like keys that must never leave the installation raw.
    "latitude",
    "longitude",
    "lat",
    "lon",
    "lng",
    "gps",
    "position",
    "address",
}


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
        mode="json", exclude={"raw_data", "mqtt_raw_data"}
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
        "unmapped_mqtt_keys": {
            car_id: sorted(unmapped_s05_keys(condition.mqtt_raw_data or {}))
            for car_id, condition in conditions.items()
            if condition.mqtt_raw_data
        },
    }
    return async_redact_data(report, TO_REDACT)
