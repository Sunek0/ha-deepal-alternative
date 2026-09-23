"""Vehicle model helpers shared by the Home Assistant entity platforms."""

from typing import Any

# Series codes of the models known to lack some telemetry and controls: the S05
# reports charging info but no SOC-set code, and its MQTT payload carries no
# speed, gear, outside temperature, PM2.5, air quality or mileage fields.
S05_MODEL_CODES = ("S05", "C857")


def normalize_model(*values: str | None) -> str:
    """Upper-case alphanumerics of the given model fields, for containment checks."""
    return " ".join(
        "".join(
            character for character in (value or "").upper() if character.isalnum()
        )
        for value in values
    ).strip()


def is_s05(vehicle: Any) -> bool:
    """Return whether the vehicle is an S05 (series name or C857 series code)."""
    model = normalize_model(
        vehicle.series_name,
        vehicle.series_code,
        vehicle.model_name,
        vehicle.model_code,
    )
    return any(code in model for code in S05_MODEL_CODES)


def is_bev(vehicle: Any) -> bool:
    """Return whether the vehicle is battery electric (BEV token in its model)."""
    model = normalize_model(
        vehicle.series_name,
        vehicle.series_code,
        vehicle.model_name,
        vehicle.model_code,
    )
    return "BEV" in model


def supports_fuel(vehicle: Any, capabilities: Any) -> bool:
    """Return whether the vehicle has a fuel tank the fuel entities should expose.

    The official app requests the fuel section for every vehicle, so the gate is
    built from the function configuration (`#oilMileage`) plus a BEV model
    exclusion: the PHEV reports the code and the S05 EV model code carries the
    `BEV` token, so both known cars resolve without knowing the PHEV model code.
    Missing capabilities or model data keeps the fuel entities away.
    """
    if capabilities is None or not getattr(capabilities, "has_fuel", False):
        return False
    return not is_bev(vehicle)
