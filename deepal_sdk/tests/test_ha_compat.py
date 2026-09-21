"""Home Assistant integration regression tests (2026.3 baseline).

The tests exercise units, device information, unique ids and the
duplicate-vehicle guard without starting a Home Assistant runtime.
"""

import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("homeassistant")

from homeassistant.const import (
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    PERCENTAGE,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from custom_components.deepal import (
    binary_sensor,
    button,
    climate,
    config_flow,
    cover,
    diagnostics,
    image,
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
    VehicleCapabilities,
)
from deepal.models import Vehicle, VehicleCondition

from homeassistant.components.diagnostics.const import REDACTED
from homeassistant.helpers.httpx_client import DATA_ASYNC_CLIENT
from homeassistant.util.ssl import SSL_ALPN_HTTP11

INTEGRATION_DIR = REPO_ROOT / "custom_components" / "deepal"
HACS_METADATA = REPO_ROOT / "hacs.json"
TRANSLATION_FILES = [
    INTEGRATION_DIR / "strings.json",
    INTEGRATION_DIR / "translations" / "en.json",
    INTEGRATION_DIR / "translations" / "es.json",
    INTEGRATION_DIR / "translations" / "de.json",
    INTEGRATION_DIR / "translations" / "fr.json",
    INTEGRATION_DIR / "translations" / "it.json",
    INTEGRATION_DIR / "translations" / "pt.json",
]

ALLOWED_DEVICE_INFO_FIELDS = {"identifiers", "name", "manufacturer", "model"}


def _fake_hass() -> SimpleNamespace:
    """Minimal hass double for entities that initialize their HTTP client."""

    async def async_add_executor_job(func, *args):
        return func(*args)

    return SimpleNamespace(
        data={DATA_ASYNC_CLIENT: {(False, SSL_ALPN_HTTP11): SimpleNamespace()}},
        async_add_executor_job=async_add_executor_job,
    )


class FakeCoordinator:
    """Minimal coordinator double for entity construction."""

    def __init__(self) -> None:
        self.data: dict = {}
        self.update_interval = None
        self.client = None
        self.hass = _fake_hass()


def _fake_vehicle() -> SimpleNamespace:
    return SimpleNamespace(
        car_id="car-1",
        series_name="Deepal S05 Max",
        car_name=None,
        model_name=None,
        thumbnail_url=None,
    )


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
            sensor.DeepalTirePressureSensor(coordinator, vehicle, "front_left"),
            sensor.DeepalSeatLevelSensor(
                coordinator, vehicle, "front_left", "heating_level"
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
                coordinator, vehicle, "front_left"
            ),
            binary_sensor.DeepalWindowBinarySensor(
                coordinator, vehicle, "front_left_open"
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
        "switch": [
            switch.DeepalChargeScheduleSwitch(coordinator, vehicle),
            switch.DeepalSteeringWheelHeatSwitch(coordinator, vehicle),
        ],
        "number": [
            number.DeepalChargeLimitNumber(coordinator, vehicle),
            number.DeepalSeatLevelNumber(
                coordinator, vehicle, "front_left", "heating"
            ),
            number.DeepalSeatLevelNumber(
                coordinator, vehicle, "front_left", "ventilation"
            ),
            number.DeepalSeatLevelNumber(
                coordinator, vehicle, "front_right", "heating"
            ),
            number.DeepalSeatLevelNumber(
                coordinator, vehicle, "front_right", "ventilation"
            ),
        ],
        "time": [
            time_platform.DeepalChargeScheduleTime(
                coordinator,
                vehicle,
                "charge_schedule_start",
                "start",
            )
        ],
        "image": [image.DeepalVehicleImage(coordinator, vehicle)],
    }


def test_hacs_metadata_declares_supported_baseline() -> None:
    metadata = json.loads(HACS_METADATA.read_text(encoding="utf-8"))
    assert metadata["name"] == "Deepal Alternative"
    assert metadata["homeassistant"] == "2026.3.0"
    assert "ES" in metadata["country"]


def test_percentage_entities_use_ratio_enumerator() -> None:
    coordinator = FakeCoordinator()
    vehicle = _fake_vehicle()
    battery = sensor.DeepalBatterySocSensor(coordinator, vehicle)
    charge_limit = number.DeepalChargeLimitNumber(coordinator, vehicle)
    descriptions = {description.key: description for description in sensor.SENSORS}

    assert battery._attr_native_unit_of_measurement is PERCENTAGE
    assert charge_limit._attr_native_unit_of_measurement is PERCENTAGE
    assert (
        descriptions["cabin_humidity"].native_unit_of_measurement
        is PERCENTAGE
    )
    assert (
        descriptions["charge_limit"].native_unit_of_measurement
        is PERCENTAGE
    )


def test_density_entity_uses_density_enumerator() -> None:
    descriptions = {description.key: description for description in sensor.SENSORS}
    assert (
        descriptions["inside_pm25"].native_unit_of_measurement
        is CONCENTRATION_MICROGRAMS_PER_CUBIC_METER
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
        def async_get_devices(self, identifiers):
            if identifiers == {("deepal", "car-1")}:
                return [FakeDevice()]
            return []

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


def test_duplicate_vehicle_guard_supports_the_2026_3_registry(monkeypatch) -> None:
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

    assert config_flow._vehicle_device_entry(hass, "car-1") is owner_entry
    assert config_flow._vehicle_device_entry(hass, "car-unknown") is None


def test_duplicate_vehicle_guard_supports_the_2026_3_registry(monkeypatch) -> None:
    owner_entry = SimpleNamespace(entry_id="entry-1")

    class FakeDevice:
        primary_config_entry = "entry-1"

    class FakeRegistry:
        def async_get_device(self, *, identifiers):
            if identifiers == {("deepal", "car-1")}:
                return FakeDevice()
            return None

    class FakeConfigEntries:
        def async_get_entry(self, entry_id):
            assert entry_id == "entry-1"
            return owner_entry

    monkeypatch.setattr(config_flow.dr, "async_get", lambda hass: FakeRegistry())
    hass = SimpleNamespace(config_entries=FakeConfigEntries())

    assert config_flow._vehicle_device_entry(hass, "car-1") is owner_entry
    assert config_flow._vehicle_device_entry(hass, "car-unknown") is None


def test_odometer_and_mileage_sensor_names() -> None:
    coordinator = FakeCoordinator()
    vehicle = _fake_vehicle()
    odometer = sensor.DeepalOdometerSensor(coordinator, vehicle)
    yesterday = sensor.DeepalMileageYesterdaySensor(coordinator, vehicle)
    trip = sensor.DeepalTripMileageSensor(coordinator, vehicle)

    assert odometer._attr_has_entity_name is True
    assert odometer._attr_translation_key == "total_odometer"
    assert odometer._attr_unique_id == "deepal_car-1_total_odometer"
    assert yesterday._attr_translation_key == "mileage_yesterday"
    assert yesterday._attr_unique_id == "deepal_car-1_mileage_yesterday"
    assert yesterday._attr_state_class is sensor.SensorStateClass.TOTAL
    assert trip._attr_translation_key == "trip_mileage"
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


def test_seat_and_steering_entity_contract() -> None:
    coordinator = FakeCoordinator()
    vehicle = _fake_vehicle()
    driver_heat = number.DeepalSeatLevelNumber(
        coordinator, vehicle, "front_left", "heating"
    )
    passenger_wind = number.DeepalSeatLevelNumber(
        coordinator, vehicle, "front_right", "ventilation"
    )
    steering = switch.DeepalSteeringWheelHeatSwitch(coordinator, vehicle)

    assert driver_heat._attr_unique_id == (
        "deepal_car-1_seat_front_left_heating_control"
    )
    assert driver_heat._attr_translation_key == "seat_heating_level_front_left"
    assert driver_heat._attr_native_min_value == 0
    assert driver_heat._attr_native_max_value == 3
    assert driver_heat._attr_native_step == 1
    assert passenger_wind._attr_unique_id == (
        "deepal_car-1_seat_front_right_ventilation_control"
    )
    assert passenger_wind._attr_translation_key == (
        "seat_ventilation_level_front_right"
    )
    assert steering._attr_unique_id == "deepal_car-1_steering_wheel_heating"
    assert steering._attr_translation_key == "steering_wheel_heating"


class _FakeCommandClient:
    """Capture the comfort commands sent by the entities."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.control_pin: str | None = None
        self.rc_token: str | None = None

    async def control_seats_heat(self, vehicle_id: str, **kwargs: Any) -> str:
        self.calls.append(("heat", vehicle_id, kwargs))
        return "cmd-1"

    async def control_seats_wind(self, vehicle_id: str, **kwargs: Any) -> str:
        self.calls.append(("wind", vehicle_id, kwargs))
        return "cmd-1"

    async def control_steering_wheel_heat(
        self, vehicle_id: str, open_value: bool
    ) -> str:
        self.calls.append(("steer", vehicle_id, open_value))
        return "cmd-1"


class _FakeCommandCoordinator(FakeCoordinator):
    """Run commands synchronously and apply the optimistic update."""

    def __init__(self, condition) -> None:
        super().__init__()
        self.data = {condition.car_id: condition}
        self.client = _FakeCommandClient()

    async def async_execute_command(
        self,
        vehicle_id,
        send_command,
        *,
        is_done=None,
        optimistic_update=None,
        timeout=None,
        interval=None,
    ) -> None:
        await send_command()
        if optimistic_update is not None:
            current = self.data.get(vehicle_id)
            if current is not None:
                self.data[vehicle_id] = optimistic_update(current)


@pytest.mark.asyncio
async def test_seat_and_steering_controls_send_app_payloads() -> None:
    condition = VehicleCondition(car_id="car-1", vin="test-vin")
    coordinator = _FakeCommandCoordinator(condition)
    vehicle = _fake_vehicle()
    driver_heat = number.DeepalSeatLevelNumber(
        coordinator, vehicle, "front_left", "heating"
    )
    passenger_wind = number.DeepalSeatLevelNumber(
        coordinator, vehicle, "front_right", "ventilation"
    )
    steering = switch.DeepalSteeringWheelHeatSwitch(coordinator, vehicle)

    await driver_heat.async_set_native_value(2)
    await passenger_wind.async_set_native_value(0)
    await steering.async_turn_on()

    assert coordinator.client.calls[0] == (
        "heat",
        "car-1",
        {"master_switch": 1, "master_level": 2},
    )
    assert coordinator.client.calls[1] == (
        "wind",
        "car-1",
        {"copilot_switch": 0, "copilot_level": None},
    )
    assert coordinator.client.calls[2] == ("steer", "car-1", True)
    assert condition.seats.front_left.heating_level == 2
    assert condition.seats.front_right.ventilation_level == 0
    assert condition.climate.steering_wheel_heater_on is True


def test_entity_icons() -> None:
    coordinator = FakeCoordinator()
    vehicle = _fake_vehicle()
    charge_limit = number.DeepalChargeLimitNumber(coordinator, vehicle)
    tire = sensor.DeepalTirePressureSensor(coordinator, vehicle, "front_left")
    alarm = binary_sensor.DeepalTireAlarmBinarySensor(
        coordinator, vehicle, "front_left"
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


def test_every_entity_translation_key_ships_in_every_language() -> None:
    languages = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in TRANSLATION_FILES
    }
    entities = _entities_by_platform()

    for platform, platform_entities in entities.items():
        for entity in platform_entities:
            assert entity.has_entity_name is True, f"{platform}: entity naming disabled"
            key = entity.translation_key
            assert key, f"{platform}: entity without a translation key"
            for name, data in languages.items():
                translated = data.get("entity", {}).get(platform, {}).get(key)
                assert translated and translated.get(
                    "name"
                ), f"{name}:{platform}.{key}"


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
    assert "UnitOfRatio" not in source


class _DiagnosticsCoordinator:
    """Coordinator double for the diagnostics report."""

    def __init__(self, vehicles, conditions, capabilities) -> None:
        self.vehicles = vehicles
        self.data = conditions
        self._capabilities = capabilities

    def vehicle_capabilities(self, car_id: str):
        return self._capabilities.get(car_id)


def _diagnostics_entry(coordinator) -> SimpleNamespace:
    return SimpleNamespace(
        data={
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
            "cac_token": "test-cac-token",
            "user_id": "test-user-1",
            "private_key": "test-private-key",
            "phone": "600000000",
            "email": "test.user@example.com",
            "device_id": "test-device-id",
            "control_pin": "1234",
            "vehicle_id": "car-1",
        },
        options={"scan_interval": 120, "control_pin": "1234"},
        runtime_data=SimpleNamespace(coordinator=coordinator),
    )


def _mqtt_condition() -> VehicleCondition:
    condition = VehicleCondition(car_id="car-1", vin="VIN-REAL-1")
    condition.battery.soc_percentage = 71
    condition.raw_data = {"vehicleStatus": {"soc": 71, "latitude": 40.4}}
    condition.mqtt_raw_data = {
        "soc": 71,
        "chargeCoverStatus": 3,
        "latitude": 40.4,
    }
    return condition


@pytest.mark.asyncio
async def test_diagnostics_report_lists_capabilities_and_unmapped_keys() -> None:
    vehicle = Vehicle(
        car_id="car-1",
        vin="VIN-REAL-1",
        series_name="Deepal S05",
        model_name="S05 Max",
        model_code="CD701GR1501",
        protocol_type="MQTT",
    )
    capabilities = VehicleCapabilities.from_codes(["#driverSeatVent"])
    coordinator = _DiagnosticsCoordinator(
        [vehicle], {"car-1": _mqtt_condition()}, {"car-1": capabilities}
    )

    report = await diagnostics.async_get_config_entry_diagnostics(
        None, _diagnostics_entry(coordinator)
    )

    assert report["capabilities"]["car-1"]["trim_hint"] == "max"
    assert report["mapped_telemetry"]["car-1"]["battery"]["soc_percentage"] == 71
    assert "raw_data" not in report["mapped_telemetry"]["car-1"]
    assert "mqtt_raw_data" not in report["mapped_telemetry"]["car-1"]
    assert report["raw_rest"]["car-1"]["vehicleStatus"]["soc"] == 71
    assert report["raw_mqtt"]["car-1"]["chargeCoverStatus"] == 3
    assert report["unmapped_mqtt_keys"]["car-1"] == [
        "chargeCoverStatus",
        "latitude",
    ]


@pytest.mark.asyncio
async def test_diagnostics_report_redacts_credentials_and_locations() -> None:
    vehicle = Vehicle(
        car_id="car-1", vin="VIN-REAL-1", thumbnail_url="https://example.invalid/car.png"
    )
    coordinator = _DiagnosticsCoordinator(
        [vehicle], {"car-1": _mqtt_condition()}, {"car-1": None}
    )

    report = await diagnostics.async_get_config_entry_diagnostics(
        None, _diagnostics_entry(coordinator)
    )
    serialized = json.dumps(report)

    assert "VIN-REAL-1" not in serialized
    assert "test-access-token" not in serialized
    assert "test-private-key" not in serialized
    assert "1234" not in json.dumps(report["config_entry_data"])
    assert "600000000" not in serialized
    assert report["vehicles"][0]["vin"] == REDACTED
    assert report["config_entry_data"]["access_token"] == REDACTED
    assert report["raw_mqtt"]["car-1"]["latitude"] == REDACTED
    assert report["capabilities"]["car-1"] is None


@pytest.mark.asyncio
async def test_diagnostics_report_survives_an_empty_entry() -> None:
    coordinator = _DiagnosticsCoordinator([], {}, {})

    report = await diagnostics.async_get_config_entry_diagnostics(
        None, _diagnostics_entry(coordinator)
    )

    assert report["vehicles"] == []
    assert report["mapped_telemetry"] == {}
    assert report["raw_mqtt"] == {}
    assert report["unmapped_mqtt_keys"] == {}


def test_config_flow_defaults_to_the_international_platform() -> None:
    assert config_flow.DEFAULT_PLATFORM == config_flow.PLATFORM_INTL
    assert next(iter(config_flow.PLATFORM_OPTIONS)) == config_flow.PLATFORM_INTL
    assert set(config_flow.PLATFORM_OPTIONS) == {
        config_flow.PLATFORM_INTL,
        config_flow.PLATFORM_SDA,
    }


def test_integration_platforms_include_image() -> None:
    from homeassistant.const import Platform

    from custom_components.deepal import _platforms

    intl_entry = SimpleNamespace(
        data={"platform": "intl", "private_key": "test-private-key"}
    )
    sda_entry = SimpleNamespace(data={})
    assert Platform.IMAGE in _platforms(intl_entry)
    assert Platform.IMAGE in _platforms(sda_entry)



