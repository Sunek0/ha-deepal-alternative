"""Vehicle model helpers shared by the Home Assistant entity platforms."""

from typing import Any

from .deepal.mqtt import is_s05_model


def normalize_model(*values: str | None) -> str:
    """Upper-case alphanumerics of the given model fields, for containment checks."""
    return " ".join(
        "".join(
            character for character in (value or "").upper() if character.isalnum()
        )
        for value in values
    ).strip()


def is_s05(vehicle: Any) -> bool:
    """Return whether the vehicle is an S05.

    Delegates to the SDK model-code classifier so the entity gates and the MQTT
    normalization agree: a vehicle whose only identifier is an ``SC646`` model
    code (S05 PHEV) is an S05 for both.
    """
    return any(
        is_s05_model(value)
        for value in (
            vehicle.series_name,
            vehicle.series_code,
            vehicle.model_name,
            vehicle.model_code,
        )
    )


def is_bev(vehicle: Any) -> bool:
    """Return whether the vehicle is battery electric (BEV token in its model)."""
    model = normalize_model(
        vehicle.series_name,
        vehicle.series_code,
        vehicle.model_name,
        vehicle.model_code,
    )
    return "BEV" in model


def is_phev(vehicle: Any) -> bool:
    """Return whether the vehicle is a plug-in hybrid (HEV token, not BEV).

    The S05 family carries ``BEV`` in the battery-electric model code and
    ``HEV`` in the plug-in hybrid code. The check is model-based because the
    PHEV needs different entity gates than the electric S05.
    """
    model = normalize_model(
        vehicle.series_name,
        vehicle.series_code,
        vehicle.model_name,
        vehicle.model_code,
    )
    return "HEV" in model and "BEV" not in model


def is_s05_phev(vehicle: Any) -> bool:
    """Return whether the vehicle is an S05 plug-in hybrid."""
    return is_s05(vehicle) and is_phev(vehicle)


def supports_charge_schedule(vehicle: Any) -> bool:
    """Return whether the switch/time charge-schedule controls are available.

    The S05 BEV writes the plan through ``add-plan``/``delete-plan`` and the
    PHEV through ``modify-plan``; both use the model-aware command helper. Other
    international models keep the control they already had.
    """
    return not is_s05(vehicle) or is_s05(vehicle)


def supports_charge_plan(vehicle: Any) -> bool:
    """Return whether the vehicle exposes charge-plan telemetry (read-only).

    Every international vehicle may report a ``chargePlanList``; the platform
    only builds these read-only entities for the international client. The gate
    deliberately does not enable the switch/time controls, which keep the
    stricter :func:`supports_charge_schedule` gate.
    """
    return True


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


def seat_function_supported(
    capabilities: Any, position: str, function: str
) -> bool:
    """Return whether the fetched capabilities include a seat function.

    Conservative on purpose: without capabilities, or with a configuration that
    carries no seat comfort code at all, the model-based entity set is kept, so
    an incomplete capability response never removes working entities.
    """
    if capabilities is None:
        return True
    seats = getattr(capabilities, "seats", None) or {}
    if not any(
        getattr(seat, "heating", False) or getattr(seat, "ventilation", False)
        for seat in seats.values()
    ):
        return True
    seat = seats.get(position)
    return bool(seat and getattr(seat, function, False))


def uses_s05_charge_enum(vehicle: Any, condition: Any) -> bool:
    """Return whether a condition reports the S05 CA-broker charge enum.

    The enum rule applies to S05 telemetry read from the CA broker, including a
    payload whose charge group was omitted and whose state was retained from the
    previous S05 report. The SDA broker, the REST condition and other models
    keep their own charging-status semantics.
    """
    if vehicle is None or not is_s05(vehicle):
        return False
    return (getattr(condition, "condition_source", None) or "") == "legacy-mqtt"


def supports_charge_limit(vehicle: Any, capabilities: Any) -> bool:
    """Return whether the vehicle supports the charge-limit sensor and control.

    Capability-first: a vehicle whose function configuration reports a
    charge-limit code gets the control even when its model is otherwise
    excluded. The S05 PHEV is the exception: its function configuration
    advertises the code but the condition never returns `maxSocPercent`, so the
    entities would always be unknown and the optimistic value would expire.
    They stay disabled until a readable PHEV source is verified. The S05 keeps
    losing the control when the capabilities are unavailable or report no
    charge-limit code, because the signed charge_max command is accepted
    without changing the limit on that model (verified on the S05 EV). Every
    other model keeps the control, so a missing capability list never removes
    it.
    """
    if is_s05_phev(vehicle):
        return False
    if capabilities is not None and getattr(capabilities, "has_charge_limit", False):
        return True
    return not is_s05(vehicle)
