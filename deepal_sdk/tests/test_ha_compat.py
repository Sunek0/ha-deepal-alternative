"""Home Assistant 2026.9 compatibility regression tests.

The tests exercise units, device information, unique ids and the
duplicate-vehicle guard without starting a Home Assistant runtime.
"""

import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from homeassistant.const import UnitOfDensity, UnitOfRatio

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from custom_components.deepal import (
    binary_sensor,
    button,
    climate,
    config_flow,
    cover,
    lock,
    number,
    sensor,
    switch,
)
from custom_components.deepal import time as time_platform
from custom_components.deepal.deepal import (
    DeepalAPIError,
    DeepalAuthError,
    DeepalRateLimitError,
)

INTEGRATION_DIR = REPO_ROOT / "custom_components" / "deepal"
HACS_METADATA = REPO_ROOT / "hacs.json"
TRANSLATION_FILES = [
    INTEGRATION_DIR / "strings.json",
    INTEGRATION_DIR / "translations" / "en.json",
    INTEGRATION_DIR / "translations" / "es.json",
]

ALLOWED_DEVICE_INFO_FIELDS = {"identifiers", "name", "manufacturer", "model"}


class FakeCoordinator:
    """Minimal coordinator double for entity construction."""

    def __init__(self) -> None:
        self.data: dict = {}
        self.update_interval = None
        self.client = None


def _fake_vehicle() -> SimpleNamespace:
    return SimpleNamespace(car_id="car-1", series_name="Deepal S05 Max")


def _entities_by_platform() -> dict[str, list]:
    coordinator = FakeCoordinator()
    vehicle = _fake_vehicle()
    return {
        "sensor": [
            sensor.DeepalBatterySocSensor(coordinator, vehicle),
            sensor.DeepalRemainingRangeSensor(coordinator, vehicle),
            sensor.DeepalOdometerSensor(coordinator, vehicle),
            sensor.DeepalMileageYesterdaySensor(coordinator, vehicle),
            sensor.DeepalTripMileageSensor(coordinator, vehicle),
            sensor.DeepalTirePressureSensor(
                coordinator, vehicle, "front_left", "Front Left"
            ),
            sensor.DeepalSeatLevelSensor(
                coordinator, vehicle, "front_left", "heating_level", "Front Left", "Heating"
            ),
            sensor.DeepalSteeringWheelHeaterLevelSensor(coordinator, vehicle),
            *(
                sensor.DeepalSensor(coordinator, vehicle, description)
                for description in sensor.SENSORS
            ),
        ],
        "binary_sensor": [
            binary_sensor.DeepalChargerPluggedBinarySensor(coordinator, vehicle),
            binary_sensor.DeepalDoorsLockedBinarySensor(coordinator, vehicle),
            binary_sensor.DeepalTireAlarmBinarySensor(
                coordinator, vehicle, "front_left", "Front Left"
            ),
            binary_sensor.DeepalWindowBinarySensor(
                coordinator, vehicle, "front_left_open", "Front Left"
            ),
            binary_sensor.DeepalSteeringWheelHeaterBinarySensor(coordinator, vehicle),
            *(
                binary_sensor.DeepalBinarySensor(coordinator, vehicle, description)
                for description in binary_sensor.BINARY_SENSORS
            ),
        ],
        "climate": [climate.DeepalCabinClimateEntity(coordinator, vehicle)],
        "button": [
            button.DeepalRefreshButton(coordinator, vehicle),
            button.DeepalFlashLightsButton(coordinator, vehicle),
            button.DeepalHonkHornButton(coordinator, vehicle),
        ],
        "lock": [lock.DeepalDoorsLock(coordinator, vehicle)],
        "cover": [
            cover.DeepalWindowsCover(coordinator, vehicle),
            cover.DeepalTrunkCover(coordinator, vehicle),
        ],
        "switch": [switch.DeepalChargeScheduleSwitch(coordinator, vehicle)],
        "number": [number.DeepalChargeLimitNumber(coordinator, vehicle)],
        "time": [
            time_platform.DeepalChargeScheduleTime(
                coordinator,
                vehicle,
                "charge_schedule_start",
                "Charge Schedule Start",
                "start",
            )
        ],
    }


def test_hacs_metadata_declares_supported_baseline() -> None:
    metadata = json.loads(HACS_METADATA.read_text(encoding="utf-8"))
    assert metadata["name"] == "Deepal Alternative"
    assert metadata["homeassistant"] == "2026.9.0"
    assert "ES" in metadata["country"]


def test_percentage_entities_use_ratio_enumerator() -> None:
    coordinator = FakeCoordinator()
    vehicle = _fake_vehicle()
    battery = sensor.DeepalBatterySocSensor(coordinator, vehicle)
    charge_limit = number.DeepalChargeLimitNumber(coordinator, vehicle)
    descriptions = {description.key: description for description in sensor.SENSORS}

    assert battery._attr_native_unit_of_measurement is UnitOfRatio.PERCENTAGE
    assert charge_limit._attr_native_unit_of_measurement is UnitOfRatio.PERCENTAGE
    assert (
        descriptions["cabin_humidity"].native_unit_of_measurement
        is UnitOfRatio.PERCENTAGE
    )
    assert (
        descriptions["charge_limit"].native_unit_of_measurement
        is UnitOfRatio.PERCENTAGE
    )


def test_density_entity_uses_density_enumerator() -> None:
    descriptions = {description.key: description for description in sensor.SENSORS}
    assert (
        descriptions["inside_pm25"].native_unit_of_measurement
        is UnitOfDensity.MICROGRAMS_PER_CUBIC_METER
    )


def test_entities_only_expose_allowed_device_info_fields() -> None:
    for platform, entities in _entities_by_platform().items():
        for entity in entities:
            info = entity.device_info
            assert set(info) <= ALLOWED_DEVICE_INFO_FIELDS, platform
            assert info["identifiers"] == {("deepal", "car-1")}


def test_entities_have_distinct_unique_ids_per_platform() -> None:
    for platform, entities in _entities_by_platform().items():
        unique_ids = [entity._attr_unique_id for entity in entities]
        assert all(unique_ids), platform
        assert len(unique_ids) == len(set(unique_ids)), platform


def test_duplicate_vehicle_guard_returns_owning_entry(monkeypatch) -> None:
    owner_entry = SimpleNamespace(entry_id="entry-1")

    class FakeDevice:
        primary_config_entry = "entry-1"

    class FakeRegistry:
        def async_get_device(self, identifiers):
            if identifiers == {("deepal", "car-1")}:
                return FakeDevice()
            return None

    class FakeConfigEntries:
        def async_get_entry(self, entry_id):
            assert entry_id == "entry-1"
            return owner_entry

    monkeypatch.setattr(config_flow.dr, "async_get", lambda hass: FakeRegistry())
    hass = SimpleNamespace(config_entries=FakeConfigEntries())

    owner = config_flow._vehicle_device_entry(hass, "car-1")
    assert owner is owner_entry
    assert owner.entry_id != "current-entry"
    assert config_flow._vehicle_device_entry(hass, "car-unknown") is None


def test_odometer_and_mileage_sensor_names() -> None:
    coordinator = FakeCoordinator()
    vehicle = _fake_vehicle()
    odometer = sensor.DeepalOdometerSensor(coordinator, vehicle)
    yesterday = sensor.DeepalMileageYesterdaySensor(coordinator, vehicle)
    trip = sensor.DeepalTripMileageSensor(coordinator, vehicle)

    assert odometer._attr_name == "Deepal S05 Max Odometer"
    assert odometer._attr_unique_id == "deepal_car-1_total_odometer"
    assert yesterday._attr_name == "Deepal S05 Max Mileage Yesterday"
    assert yesterday._attr_unique_id == "deepal_car-1_mileage_yesterday"
    assert yesterday._attr_state_class is sensor.SensorStateClass.TOTAL
    assert trip._attr_name == "Deepal S05 Max Trip Mileage"
    assert trip._attr_unique_id == "deepal_car-1_trip_mileage"
    assert trip._attr_state_class is sensor.SensorStateClass.TOTAL


def test_entity_description_cached_properties_resolve() -> None:
    coordinator = FakeCoordinator()
    vehicle = _fake_vehicle()
    sensor_entity = sensor.DeepalSensor(
        coordinator, vehicle, sensor.SENSORS[0]
    )
    binary_entity = binary_sensor.DeepalBinarySensor(
        coordinator, vehicle, binary_sensor.BINARY_SENSORS[0]
    )

    assert sensor_entity.entity_registry_enabled_default is True
    assert sensor_entity.entity_registry_visible_default is True
    assert sensor_entity.suggested_unit_of_measurement is None
    assert sensor_entity.force_update is False
    assert binary_entity.entity_registry_enabled_default is True
    assert binary_entity.entity_registry_visible_default is True


def test_entity_icons() -> None:
    coordinator = FakeCoordinator()
    vehicle = _fake_vehicle()
    charge_limit = number.DeepalChargeLimitNumber(coordinator, vehicle)
    tire = sensor.DeepalTirePressureSensor(
        coordinator, vehicle, "front_left", "Front Left"
    )
    alarm = binary_sensor.DeepalTireAlarmBinarySensor(
        coordinator, vehicle, "front_left", "Front Left"
    )
    descriptions = {d.key: d for d in binary_sensor.BINARY_SENSORS}

    assert descriptions["trunk"].icon == "mdi:car-select"
    assert charge_limit._attr_icon == "mdi:battery-heart"
    assert tire._attr_icon == "mdi:tire"
    assert alarm._attr_icon == "mdi:car-tire-alert"


def test_mileage_sensors_are_gated_on_mqtt_vehicles() -> None:
    source = (INTEGRATION_DIR / "sensor.py").read_text(encoding="utf-8")
    assert "vehicle_uses_mqtt" in source
    assert "DeepalMileageYesterdaySensor" in source
    assert "DeepalTripMileageSensor" in source


def _translation_key_tree(data, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    if isinstance(data, dict):
        for key, value in data.items():
            keys.add(prefix + key)
            keys |= _translation_key_tree(value, prefix + key + ".")
    return keys


def test_translation_files_share_the_same_key_tree() -> None:
    trees = [
        _translation_key_tree(json.loads(path.read_text(encoding="utf-8")))
        for path in TRANSLATION_FILES
    ]
    for tree in trees[1:]:
        assert tree == trees[0]


def test_config_and_options_help_is_complete() -> None:
    for path in TRANSLATION_FILES:
        data = json.loads(path.read_text(encoding="utf-8"))
        for step_id, step in data["config"]["step"].items():
            assert step.get("title"), f"{path.name}:{step_id} title"
            assert step.get("description"), f"{path.name}:{step_id} description"
            assert set(step.get("data", {})) == set(
                step.get("data_description", {})
            ), f"{path.name}:{step_id} field help"
        init = data["options"]["step"]["init"]
        assert init.get("title") and init.get("description")
        assert set(init["data"]) == set(init["data_description"])


def test_flow_messages_are_translated() -> None:
    source = (INTEGRATION_DIR / "config_flow.py").read_text(encoding="utf-8")
    step_ids = set(re.findall(r'step_id="(\w+)"', source))
    error_keys = set(re.findall(r'errors\["base"\] = "(\w+)"', source))
    error_keys |= set(re.findall(r'errors=\{"base": "(\w+)"\}', source))
    error_keys |= {
        config_flow._login_error(err)
        for err in (
            DeepalRateLimitError("limit"),
            DeepalAPIError("CAC_1_1_01_024"),
            DeepalAPIError("APP_1_1_07_002"),
            DeepalAuthError("auth"),
            DeepalAPIError("other"),
        )
    }
    abort_keys = set(re.findall(r'reason="(\w+)"', source))

    for path in TRANSLATION_FILES:
        data = json.loads(path.read_text(encoding="utf-8"))
        known_steps = set(data["config"]["step"]) | set(data["options"]["step"])
        assert step_ids <= known_steps, path.name
        assert error_keys <= set(data["config"]["error"]), path.name
        assert abort_keys <= set(data["config"]["abort"]), path.name


def test_integration_has_no_removed_api_references() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(INTEGRATION_DIR.rglob("*.py"))
    )
    assert "hass.data[DOMAIN]" not in source
    assert "CONCENTRATION_" not in source
