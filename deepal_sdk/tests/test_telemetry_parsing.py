"""Regression tests for numeric and flag parsing of vehicle telemetry.

These cover shared parsing helpers: a numeric value that arrives as a string,
a non-finite number or an impossible percentage must produce an unknown value
(or the right value), never a wrong state and never an exception that aborts
the whole coordinator refresh.
"""

import math
import sys
import types

import pytest

try:  # pragma: no cover - the stub only exists for minimal environments
    import httpx  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover
    _stub = types.ModuleType("httpx")
    for _name in (
        "AsyncClient",
        "Response",
        "Request",
        "Timeout",
        "Limits",
        "HTTPError",
        "TimeoutException",
        "ConnectError",
        "HTTPStatusError",
        "TransportError",
        "RequestError",
    ):
        setattr(_stub, _name, type(_name, (Exception,), {}))
    sys.modules["httpx"] = _stub

from deepal import DeepalIntlClient  # noqa: E402
from deepal import intl, mqtt  # noqa: E402


def _parse(raw, model_code=None):
    # parse_condition only reads its arguments, so no network client is needed.
    client = DeepalIntlClient.__new__(DeepalIntlClient)
    return client.parse_condition(raw, "car-1", model_code=model_code)


@pytest.mark.parametrize("helper", [intl._as_int, mqtt._as_int])
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (85, 85),
        ("85", 85),
        ("85.0", 85),
        ("85.7", 85),
        (85.7, 85),
        (0, 0),
        ("0", 0),
        (" 12 ", 12),
        (None, None),
        ("", None),
        ("abc", None),
        ([], None),
        (float("nan"), None),
        (float("inf"), None),
        ("inf", None),
        ("nan", None),
        (10**20, 10**20),
    ],
)
def test_as_int_helpers_agree(helper, raw, expected):
    assert helper(raw) == expected


@pytest.mark.parametrize("helper", [intl._as_float, mqtt._as_float])
@pytest.mark.parametrize(
    ("raw", "expected"),
    [("12.5", 12.5), (0, 0.0), ("0", 0.0), (None, None), ("x", None)],
)
def test_as_float_helpers(helper, raw, expected):
    assert helper(raw) == expected


@pytest.mark.parametrize("raw", [float("nan"), float("inf"), "NaN", "Infinity"])
def test_as_float_rejects_non_finite_values(raw):
    assert intl._as_float(raw) is None
    assert mqtt._as_float(raw) is None


def test_intl_and_mqtt_share_the_same_numeric_helpers():
    assert intl._as_int is mqtt._as_int
    assert intl._as_float is mqtt._as_float


def test_decimal_string_soc_is_not_dropped():
    condition = _parse({"vehicleStatus": {"soc": "85.0", "drvMileage": "312"}})

    assert condition.battery.soc_percentage == 85
    assert condition.battery.remaining_range_km == 312


def test_zero_soc_and_zero_range_are_values_not_missing():
    condition = _parse({"vehicleStatus": {"soc": 0, "drvMileage": 0, "totalMileage": 0}})

    assert condition.battery.soc_percentage == 0
    assert condition.battery.remaining_range_km == 0
    assert condition.total_odometer_km == 0.0


@pytest.mark.parametrize("soc", [101, 255, -1, "300"])
def test_out_of_range_soc_is_unknown_and_does_not_abort_the_parse(soc):
    condition = _parse({"vehicleStatus": {"soc": soc, "totalMileage": "100.5"}})

    assert condition.battery.soc_percentage is None
    # Unrelated telemetry in the same payload is still parsed.
    assert condition.total_odometer_km == 100.5


@pytest.mark.parametrize("limit", [101, -5, 255])
def test_out_of_range_charge_limit_is_unknown(limit):
    condition = _parse({"charge": {"maxSocPercent": limit}})

    assert condition.battery.charge_limit_percent is None


def test_valid_charge_limit_is_kept():
    assert _parse({"charge": {"maxSocPercent": "80"}}).battery.charge_limit_percent == 80
    assert _parse({"charge": {"maxSocPercent": 0}}).battery.charge_limit_percent == 0


def test_string_zero_flags_mean_closed_off_and_locked():
    condition = _parse(
        {
            "door": {
                "doors": ["0", "0", "0", "0"],
                "trunk": "0",
                "hood": "0",
                "driverLock": "0",
                "passengerLock": "0",
            },
            "window": {"windows": ["0", "0", "0", "0"]},
            "lamp": {
                "highBeam": "0",
                "lowBeam": "0",
                "positionLamp": "0",
                "frontFoglamp": "0",
                "rearFoglamp": "0",
                "leftTurn": "0",
                "rightTurn": "0",
            },
            "tire": {"leftFront": {"pressure": "250", "alarm": "0"}},
        }
    )

    doors = condition.doors
    assert not any(
        (
            doors.driver_door_open,
            doors.passenger_door_open,
            doors.rear_left_door_open,
            doors.rear_right_door_open,
            doors.trunk_open,
            doors.hood_open,
        )
    )
    assert doors.locked is True
    assert doors.driver_locked is True
    assert doors.passenger_locked is True
    windows = condition.windows
    assert not any(
        (
            windows.front_left_open,
            windows.front_right_open,
            windows.rear_left_open,
            windows.rear_right_open,
        )
    )
    lamps = condition.lamps
    assert not any(
        (
            lamps.high_beam,
            lamps.low_beam,
            lamps.position_lamp,
            lamps.front_fog,
            lamps.rear_fog,
            lamps.left_turn,
            lamps.right_turn,
        )
    )
    assert condition.tires.front_left.alarm is False
    assert condition.tires.front_left.pressure_bar == 2.5


def test_string_one_flags_mean_open_on_and_unlocked():
    condition = _parse(
        {
            "door": {"doors": ["1", 0, 0, 0], "trunk": "1", "driverLock": "1"},
            "window": {"windows": ["1"]},
            "lamp": {"highBeam": "1"},
            "tire": {"leftFront": {"alarm": "1"}},
        }
    )

    assert condition.doors.driver_door_open is True
    assert condition.doors.trunk_open is True
    assert condition.doors.driver_locked is False
    assert condition.doors.locked is False
    assert condition.windows.front_left_open is True
    assert condition.lamps.high_beam is True
    assert condition.tires.front_left.alarm is True


def test_numeric_flags_keep_their_previous_meaning():
    condition = _parse(
        {
            "door": {"doors": [1, 0, 0, 2], "trunk": 0, "driverLock": 0},
            "lamp": {"lowBeam": 1, "highBeam": 0},
        }
    )

    assert condition.doors.driver_door_open is True
    assert condition.doors.rear_right_door_open is True
    assert condition.doors.passenger_door_open is False
    assert condition.doors.trunk_open is False
    assert condition.doors.locked is True
    assert condition.lamps.low_beam is True
    assert condition.lamps.high_beam is False


def test_charge_schedule_and_connection_accept_numeric_strings():
    condition = _parse(
        {
            "vehicleStatus": {"connectStatus": "1"},
            "charge": {
                "chargePlanList": [
                    {"startSwitch": "1", "endSwitch": "1", "startTime": "22:00"}
                ]
            },
        }
    )

    assert condition.connected is True
    assert condition.battery.charge_schedule_enabled is True


def test_empty_and_partial_payloads_parse_without_error():
    empty = _parse({})
    assert empty.battery.soc_percentage is None
    assert empty.total_odometer_km is None
    assert empty.latitude is None
    assert empty.climate.inside_temperature_c is None

    partial = _parse({"vehicleStatus": None, "door": None, "hvac": {"insideTemp": None}})
    assert partial.climate.inside_temperature_c is None


def test_temperature_tenths_with_string_values():
    condition = _parse({"hvac": {"insideTemp": "215", "outsideTemp": "-35"}})

    assert condition.climate.inside_temperature_c == 21.5
    assert condition.climate.outside_temperature_c == -3.5


def test_nested_null_sections_are_unknown_not_zero():
    condition = _parse(
        {"vehicleStatus": {"soc": None, "drvMileage": None, "totalMileage": None}}
    )

    assert condition.battery.soc_percentage is None
    assert condition.battery.remaining_range_km is None
    assert condition.total_odometer_km is None


def test_normalize_s05_params_survives_non_finite_values():
    normalized = mqtt.normalize_s05_params(
        {
            "soc": float("inf"),
            "remainedPowerMile": "nan",
            "totalOdometer": float("nan"),
            "vehicleTemperature": float("inf"),
            "BattACChrgInCurr": float("inf"),
        }
    )

    assert normalized["vehicleStatus"]["soc"] is None
    assert normalized["vehicleStatus"]["drvMileage"] is None
    assert normalized["vehicleStatus"]["totalMileage"] is None
    assert normalized["hvac"]["insideTemp"] is None
    assert not math.isnan(normalized["charge"].get("chargeCurrent") or 0.0)


def test_normalize_s05_params_keeps_zero_values():
    normalized = mqtt.normalize_s05_params(
        {"soc": 0, "remainedPowerMile": 0, "totalOdometer": 0, "vehicleTemperature": 0}
    )

    assert normalized["vehicleStatus"]["soc"] == 0
    assert normalized["vehicleStatus"]["drvMileage"] == 0
    assert normalized["vehicleStatus"]["totalMileage"] == 0.0
    assert normalized["hvac"]["insideTemp"] == 0.0


def test_s05_mqtt_payload_round_trips_through_parse_condition():
    normalized = mqtt.normalize_s05_params(
        {"soc": "64", "remainedPowerMile": "180", "totalOdometer": "9876.5",
         "driverDoor": "0", "driverDoorLock": "0", "ChrgSts": "0"}
    )
    condition = _parse(normalized, model_code=None)

    assert condition.battery.soc_percentage == 64
    assert condition.battery.remaining_range_km == 180
    assert condition.total_odometer_km == 9876.5
    assert condition.doors.driver_door_open is False
    assert condition.doors.driver_locked is True


# --- Sanitized real captures (S05 PHEV, EU, 2026-11-10/11; no identifiers) -----

REAL_S05_PHEV_MQTT_PARKED = {
    "soc": 93,
    "socDsp": 93,
    "remainPower": "93",
    "remainedPowerMile": 112,
    "totalResidualMileage": "607",
    "remainedOilMile": 495,
    "remainingFuel": "53",
    "fuelLeftover": "27",
    "totalOdometer": 2846.0,
    "vehicleTemperature": 19.0,
    "airConditioningSetTemperature": 25.5,
    "innerHumidity": 153.0,
    "ChrgSts": 0,
    "acChargeGunConnectionState": 1,
    "dcChargeGunConnectionState": 0,
    "BattACChrgInCurr": 0.0,
    "BattDCChrgInCurr": 0.0,
    "chargDeltMins": 8191,
    "driverDoor": "0",
    "passengerDoor": "0",
    "leftRearDoor": 0,
    "rightRearDoor": 0,
    "trunk": "0",
    "hoodStatus": "0",
    "driverDoorLock": 0,
    "passengerDoorLock": 0,
    "engineStatus": "0",
    "powerStatusFeedBack": "0",
    "lfTyrePressure": 292.449,
    "lfPressureWarning": "0",
    "latestDate": "2026-11-11T06:17:32Z",
}

REAL_S05_PHEV_REST = {
    "vehicleId": "car-1",
    "lastUpdatedAt": "1794412842000",
    "vehicleStatus": {
        "lastUpdatedAt": 1794412842000,
        "powerStatus": 0,
        "soc": 93,
        "drvMileage": 112,
        "totalMileage": 2846,
        "steeringWheelHeater": 0,
    },
    "locationGeo": {"hashCode": -1713896299},
    "door": {"driverLock": 0, "passengerLock": 0, "doors": [0, 0, 0, 0]},
    "window": {"windows": [0, 0, 0, 0], "openDegree": [0, 0, 0, 0]},
    "tire": {
        "leftFront": {"status": 0, "pressure": 292.0},
        "rightFront": {"status": 0, "pressure": 293.0},
    },
    "seat": {
        "leftFront": {"mode": 0, "heatStatus": -1, "ventStatus": -1},
        "leftBack": {"mode": 0},
    },
    "lamp": {"lowBeam": 0, "highBeam": 0, "leftTurn": 0, "rightTurn": 0},
    "charge": {
        "soc": 93,
        "chargeConStatus": 3,
        "remainChargeTime": 8191.0,
        "chargePlanList": [{"planId": 1, "isValid": 0, "startTime": "0000", "startSwitch": 1}],
    },
    "hvac": {"insideTemp": 210, "insideHumidity": 0.0, "remoteTemp": 250},
}


def test_real_s05_phev_mqtt_capture_maps_every_sensor():
    normalized = mqtt.normalize_s05_params(
        REAL_S05_PHEV_MQTT_PARKED, model_code="SC6460AAAA7HEV"
    )
    condition = _parse(normalized, model_code="SC6460AAAA7HEV")

    assert condition.battery.soc_percentage == 93
    assert condition.battery.remaining_range_km == 112  # electric, not the 607 total
    assert condition.fuel.level_percent == 53
    assert condition.fuel.remaining_range_km == 495
    assert condition.fuel.volume_l == 27.0
    assert condition.total_odometer_km == 2846.0
    assert condition.climate.inside_temperature_c == 19.0
    assert condition.climate.target_temperature_c == 25.5
    assert condition.climate.humidity == 15.3
    assert condition.tires.front_left.pressure_bar == 2.92
    assert condition.tires.front_left.alarm is False
    assert condition.doors.locked is True
    assert condition.doors.driver_door_open is False
    assert condition.doors.trunk_open is False
    assert condition.battery.charger_connected is False  # stale AC gun latch ignored
    assert condition.battery.remaining_charge_time_min is None  # 8191 sentinel
    assert condition.engine_on is False
    # The outside temperature is not reported by this vehicle: unknown, not 0.
    assert condition.climate.outside_temperature_c is None


def test_zero_humidity_placeholder_is_unknown_not_zero_percent():
    for raw in (0, 0.0):
        params = dict(REAL_S05_PHEV_MQTT_PARKED, innerHumidity=raw)
        condition = _parse(mqtt.normalize_s05_params(params))
        assert condition.climate.humidity is None
    assert _parse({"hvac": {"insideHumidity": 0.0}}).climate.humidity is None
    assert _parse({"hvac": {"insideHumidity": 136.0}}).climate.humidity == 13.6


def test_real_rest_condition_of_a_sleeping_s05_phev():
    condition = _parse(REAL_S05_PHEV_REST, model_code="SC6460AAAA7HEV")

    assert condition.battery.soc_percentage == 93
    assert condition.battery.remaining_range_km == 112
    assert condition.total_odometer_km == 2846.0
    assert condition.climate.inside_temperature_c == 21.0
    assert condition.climate.target_temperature_c == 25.0
    assert condition.climate.humidity is None
    assert condition.last_updated_timestamp == 1794412842
    # chargeConStatus 3 is a stale latch on the S05: the cable stays unplugged.
    assert condition.battery.charger_connected is False
    # -1 / absent seat levels are unknown, not a level.
    assert condition.seats.front_left.heating_level is None
    assert condition.seats.front_left.ventilation_level is None
    assert condition.seats.rear_left.heating_level is None
    assert condition.tires.front_left.pressure_bar == 2.92
    assert condition.latitude is None and condition.longitude is None
    # No fuel group in this REST payload: unknown, not 0.
    assert condition.fuel.level_percent is None


def test_fuel_volume_is_unknown_when_the_car_does_not_report_it():
    params = {k: v for k, v in REAL_S05_PHEV_MQTT_PARKED.items() if k != "fuelLeftover"}
    condition = _parse(mqtt.normalize_s05_params(params))

    assert condition.fuel.volume_l is None
    assert condition.fuel.level_percent == 53
