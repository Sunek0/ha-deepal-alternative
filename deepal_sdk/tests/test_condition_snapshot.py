"""Tests for the stored last-known condition used after a restart."""

import importlib.util
import json
import pathlib
import sys
import types

import pytest

try:  # pragma: no cover - minimal environments only
    import httpx  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover
    _stub = types.ModuleType("httpx")
    for _name in ("AsyncClient", "Response", "Request", "Timeout", "Limits", "HTTPError",
                  "TimeoutException", "ConnectError", "HTTPStatusError", "TransportError",
                  "RequestError"):
        setattr(_stub, _name, type(_name, (Exception,), {}))
    sys.modules["httpx"] = _stub

from deepal.models import VehicleCondition  # noqa: E402
from deepal.mqtt import charge_is_active  # noqa: E402

_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "custom_components" / "deepal" / "snapshot.py"
)
_spec = importlib.util.spec_from_file_location("deepal_snapshot_under_test", _PATH)
snapshot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(snapshot)


def _condition() -> VehicleCondition:
    condition = VehicleCondition(car_id="car-1", vin="SECRETVIN", raw_data={"x": 1})
    condition.latitude = 37.5
    condition.longitude = 23.7
    condition.warnings.abs = False
    condition.warnings.battery_12v = True
    condition.battery.charge_schedule_start = "0000"
    condition.battery.soc_percentage = 93
    condition.total_odometer_km = 2846.0
    condition.fuel.volume_l = 27.0
    return condition


def test_snapshot_round_trip_keeps_last_known_state():
    stored = json.loads(json.dumps(snapshot.conditions_to_snapshot({"car-1": _condition()})))

    restored = snapshot.conditions_from_snapshot(VehicleCondition, stored)["car-1"]

    assert restored.warnings.abs is False
    assert restored.warnings.battery_12v is True
    assert restored.warnings.tpms is None  # never reported stays unknown, not False
    assert (restored.latitude, restored.longitude) == (37.5, 23.7)
    assert restored.battery.charge_schedule_start == "0000"
    assert restored.battery.charge_schedule_end is None
    assert restored.total_odometer_km == 2846.0
    assert restored.fuel.volume_l == 27.0


def test_snapshot_does_not_store_identifiers_or_raw_payloads():
    text = json.dumps(snapshot.conditions_to_snapshot({"car-1": _condition()}))

    assert "SECRETVIN" not in text
    assert "raw_data" not in text and "mqtt_raw_data" not in text


@pytest.mark.parametrize("stored", [None, [], "x", {}, {"conditions": None}, {"conditions": []}])
def test_missing_or_malformed_store_restores_nothing(stored):
    assert snapshot.conditions_from_snapshot(VehicleCondition, stored) == {}


def test_corrupt_entry_is_skipped_without_losing_the_others():
    stored = snapshot.conditions_to_snapshot({"car-1": _condition()})
    stored["conditions"]["car-2"] = {"battery": {"soc_percentage": 300}}
    stored["conditions"]["car-3"] = "nope"

    restored = snapshot.conditions_from_snapshot(VehicleCondition, stored)

    assert set(restored) == {"car-1"}


def test_empty_conditions_snapshot():
    assert snapshot.conditions_to_snapshot(None) == {"conditions": {}}


@pytest.mark.parametrize(
    ("state", "expected"),
    [("0", False), ("1", False), ("2", False), ("5", False), ("3", True), ("4", True),
     ("9", None), (None, None)],
)
def test_charge_is_active_for_the_not_charging_text(state, expected):
    assert charge_is_active(state) is expected
