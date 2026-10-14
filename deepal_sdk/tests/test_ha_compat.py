"""Home Assistant integration regression tests (2026.3 baseline).

The tests exercise units, device information, unique ids and the
duplicate-vehicle guard without starting a Home Assistant runtime.
"""

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("homeassistant")

from homeassistant.const import (
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    UnitOfRatio,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import custom_components.deepal as deepal_integration
from custom_components.deepal import (
    binary_sensor,
    button,
    climate,
    config_flow,
    cover,
    diagnostics,
    entity,
    image,
    lock,
    number,
    repairs,
    sensor,
    switch,
)
from custom_components.deepal import async_remove_config_entry_device
from custom_components.deepal import time as time_platform
from custom_components.deepal.charging import ChargingSessionManager
from custom_components.deepal.const import CONF_CONTROL_PIN
from custom_components.deepal.deepal import (
    DeepalAPIError,
    DeepalAuthError,
    DeepalError,
    DeepalIntlClient,
    DeepalRateLimitError,
    VehicleCapabilities,
)
from custom_components.deepal.vehicle_model import is_bev, is_s05, supports_fuel
from deepal.models import Vehicle, VehicleCondition

from homeassistant.components.diagnostics.const import REDACTED
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
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
        self.mqtt_vehicles: set[str] = set()
        self.capabilities: dict = {}
        self.entry = SimpleNamespace(options={})

    def vehicle_uses_mqtt(self, car_id: str) -> bool:
        """Return whether the vehicle is marked as MQTT-backed."""
        return car_id in self.mqtt_vehicles

    def vehicle_capabilities(self, car_id: str):
        """Return the cached capabilities for a vehicle, if any."""
        return self.capabilities.get(car_id)


def _fake_vehicle() -> SimpleNamespace:
    return SimpleNamespace(
        car_id="car-1",
        series_name="Deepal S05 Max",
        car_name=None,
        model_name=None,
        thumbnail_url=None,
        license_plate=None,
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
            button.DeepalFlashAndHonkButton(coordinator, vehicle),
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
    assert set(metadata["country"]) == {
        "ES",
        "PT",
        "GB",
        "IE",
        "FR",
        "BE",
        "LU",
        "DE",
        "AT",
        "CH",
        "IT",
        "GR",
    }


def test_manifest_metadata_follows_ha_conventions() -> None:
    manifest = json.loads(
        (INTEGRATION_DIR / "manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["domain"] == "deepal"
    assert manifest["integration_type"] == "hub"
    assert manifest["loggers"] == ["deepal_sdk"]
    assert manifest["version"]
    assert manifest["requirements"] == ["pydantic>=2.0.0"]


def test_country_options_have_dial_codes() -> None:
    assert set(config_flow.COUNTRY_OPTIONS) == set(config_flow.COUNTRY_DIAL_CODES)
    assert config_flow.COUNTRY_OPTIONS["GR"] == "Greece (+30)"
    assert config_flow.COUNTRY_DIAL_CODES["GR"] == "30"


def test_build_client_injects_the_shared_httpx_client(monkeypatch) -> None:
    shared = object()
    monkeypatch.setattr(deepal_integration, "get_async_client", lambda hass: shared)
    hass = SimpleNamespace()

    intl_entry = SimpleNamespace(
        data={"platform": "intl", "access_token": "test_token_123"},
        options={},
    )
    intl_client = deepal_integration._build_client(hass, intl_entry)
    assert intl_client._client is shared
    assert intl_client._external_client is True

    sda_entry = SimpleNamespace(
        data={"platform": "sda", "access_token": "test_token_123"},
        options={},
    )
    sda_client = deepal_integration._build_client(hass, sda_entry)
    assert sda_client._client is shared
    assert sda_client._external_client is True


def _patch_issue_registry(monkeypatch) -> tuple[list[dict], list[str]]:
    created: list[dict] = []
    deleted: list[str] = []
    monkeypatch.setattr(
        deepal_integration.ir,
        "async_create_issue",
        lambda hass, domain, issue_id, **kwargs: created.append(
            {"domain": domain, "issue_id": issue_id, **kwargs}
        ),
    )
    monkeypatch.setattr(
        deepal_integration.ir,
        "async_delete_issue",
        lambda hass, domain, issue_id: deleted.append(issue_id),
    )
    return created, deleted


def test_mqtt_reauth_issue_is_created_without_a_user_id(monkeypatch) -> None:
    created, deleted = _patch_issue_registry(monkeypatch)
    client = object.__new__(DeepalIntlClient)
    client.user_id = None
    coordinator = SimpleNamespace(
        client=client, vehicles=[SimpleNamespace(protocol_type="MQTT")]
    )
    entry = SimpleNamespace(entry_id="entry-1", title="Deepal S05")

    deepal_integration._sync_mqtt_reauth_issue(SimpleNamespace(), entry, coordinator)

    assert deleted == []
    assert created == [
        {
            "domain": "deepal",
            "issue_id": "mqtt_user_id_missing_entry-1",
            "data": {"entry_id": "entry-1"},
            "is_fixable": True,
            "severity": deepal_integration.ir.IssueSeverity.WARNING,
            "translation_key": "mqtt_user_id_missing",
            "translation_placeholders": {"name": "Deepal S05"},
        }
    ]


def test_mqtt_reauth_issue_is_cleared_with_a_user_id(monkeypatch) -> None:
    created, deleted = _patch_issue_registry(monkeypatch)
    client = object.__new__(DeepalIntlClient)
    client.user_id = "user-1"
    coordinator = SimpleNamespace(
        client=client, vehicles=[SimpleNamespace(protocol_type="MQTT")]
    )
    entry = SimpleNamespace(entry_id="entry-1", title="Deepal S05")

    deepal_integration._sync_mqtt_reauth_issue(SimpleNamespace(), entry, coordinator)

    assert created == []
    assert deleted == ["mqtt_user_id_missing_entry-1"]


def test_mqtt_reauth_issue_is_not_created_for_sda_entries(monkeypatch) -> None:
    created, deleted = _patch_issue_registry(monkeypatch)
    client = object.__new__(deepal_integration.DeepalClient)
    coordinator = SimpleNamespace(
        client=client, vehicles=[SimpleNamespace(protocol_type="MQTT")]
    )
    entry = SimpleNamespace(entry_id="entry-1", title="Deepal S05")

    deepal_integration._sync_mqtt_reauth_issue(SimpleNamespace(), entry, coordinator)

    assert created == []
    assert deleted == ["mqtt_user_id_missing_entry-1"]


def test_mqtt_reauth_issue_is_not_created_without_mqtt_vehicles(monkeypatch) -> None:
    created, deleted = _patch_issue_registry(monkeypatch)
    client = object.__new__(DeepalIntlClient)
    client.user_id = None
    coordinator = SimpleNamespace(
        client=client, vehicles=[SimpleNamespace(protocol_type=None)]
    )
    entry = SimpleNamespace(entry_id="entry-1", title="Deepal S05")

    deepal_integration._sync_mqtt_reauth_issue(SimpleNamespace(), entry, coordinator)

    assert created == []
    assert deleted == ["mqtt_user_id_missing_entry-1"]


@pytest.mark.asyncio
async def test_mqtt_repair_flow_starts_the_reauth_flow() -> None:
    started: list[str] = []

    class FakeEntry:
        entry_id = "entry-1"

        def async_start_reauth(self, hass) -> None:
            started.append(self.entry_id)

    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_get_entry=lambda entry_id: FakeEntry())
    )
    flow = repairs.MqttReauthRepairFlow()
    flow.hass = hass
    flow.data = {"entry_id": "entry-1"}
    flow.flow_id = "test-flow"
    flow.handler = "deepal"

    result = await flow.async_step_init({})

    assert started == ["entry-1"]
    assert result["type"] is FlowResultType.CREATE_ENTRY


def _removal_entry(car_ids: list[str]):
    vehicles = [SimpleNamespace(car_id=car_id) for car_id in car_ids]
    return SimpleNamespace(
        runtime_data=SimpleNamespace(
            coordinator=SimpleNamespace(vehicles=vehicles)
        )
    )


@pytest.mark.asyncio
async def test_remove_device_allows_stale_vehicles() -> None:
    entry = _removal_entry([])

    assert (
        await async_remove_config_entry_device(
            object(), entry, SimpleNamespace(identifiers={("deepal", "car-1")})
        )
        is True
    )


@pytest.mark.asyncio
async def test_remove_device_rejects_active_vehicles() -> None:
    entry = _removal_entry(["car-1", "car-2"])

    assert (
        await async_remove_config_entry_device(
            object(), entry, SimpleNamespace(identifiers={("deepal", "car-1")})
        )
        is False
    )


@pytest.mark.asyncio
async def test_remove_device_allows_devices_without_a_deepal_identifier() -> None:
    entry = _removal_entry(["car-1"])
    device = SimpleNamespace(identifiers={("other_domain", "thing")})

    assert await async_remove_config_entry_device(object(), entry, device) is True


@pytest.mark.asyncio
async def test_remove_device_allows_entries_without_runtime_data() -> None:
    entry = SimpleNamespace()

    assert (
        await async_remove_config_entry_device(
            object(), entry, SimpleNamespace(identifiers={("deepal", "car-1")})
        )
        is True
    )


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


def test_platforms_declare_no_parallel_update_limit() -> None:
    platforms = (
        binary_sensor,
        button,
        climate,
        cover,
        image,
        lock,
        number,
        sensor,
        switch,
        time_platform,
    )

    for platform in platforms:
        assert platform.PARALLEL_UPDATES == 0, platform.__name__


def test_density_entity_uses_density_enumerator() -> None:
    descriptions = {description.key: description for description in sensor.SENSORS}
    assert (
        descriptions["inside_pm25"].native_unit_of_measurement
        is CONCENTRATION_MICROGRAMS_PER_CUBIC_METER
    )


def test_setup_reconciliation_removes_stale_entities_and_devices(monkeypatch) -> None:
    removed_entities: list[str] = []
    removed_devices: list[str] = []

    class FakeEntityRegistry:
        def async_remove(self, entity_id):
            removed_entities.append(entity_id)

    class FakeDeviceRegistry:
        def async_remove_device(self, device_id):
            removed_devices.append(device_id)

    monkeypatch.setattr(
        deepal_integration.er, "async_get", lambda hass: FakeEntityRegistry()
    )
    monkeypatch.setattr(
        deepal_integration.er,
        "async_entries_for_config_entry",
        lambda registry, entry_id: [
            SimpleNamespace(
                unique_id="deepal_car-1_battery_soc", entity_id="sensor.keep"
            ),
            SimpleNamespace(
                unique_id="deepal_car-9_battery_soc", entity_id="sensor.stale"
            ),
            SimpleNamespace(unique_id="other_unique_id", entity_id="sensor.foreign"),
        ],
    )
    monkeypatch.setattr(
        deepal_integration.dr, "async_get", lambda hass: FakeDeviceRegistry()
    )
    monkeypatch.setattr(
        deepal_integration.dr,
        "async_entries_for_config_entry",
        lambda registry, entry_id: [
            SimpleNamespace(id="dev-keep", identifiers={("deepal", "car-1")}),
            SimpleNamespace(id="dev-stale", identifiers={("deepal", "car-9")}),
            SimpleNamespace(id="dev-foreign", identifiers={("other", "thing")}),
        ],
    )

    coordinator = SimpleNamespace(vehicles=[SimpleNamespace(car_id="car-1")])
    entry = SimpleNamespace(entry_id="entry-1")

    deepal_integration._remove_stale_vehicle_registry(
        SimpleNamespace(), entry, coordinator
    )

    assert removed_entities == ["sensor.stale"]
    assert removed_devices == ["dev-stale"]


def test_setup_reconciliation_keeps_current_entities_and_devices(monkeypatch) -> None:
    removed_entities: list[str] = []
    removed_devices: list[str] = []

    class FakeEntityRegistry:
        def async_remove(self, entity_id):
            removed_entities.append(entity_id)

    class FakeDeviceRegistry:
        def async_remove_device(self, device_id):
            removed_devices.append(device_id)

    monkeypatch.setattr(
        deepal_integration.er, "async_get", lambda hass: FakeEntityRegistry()
    )
    monkeypatch.setattr(
        deepal_integration.er,
        "async_entries_for_config_entry",
        lambda registry, entry_id: [
            SimpleNamespace(
                unique_id="deepal_car-1_battery_soc", entity_id="sensor.keep"
            ),
        ],
    )
    monkeypatch.setattr(
        deepal_integration.dr, "async_get", lambda hass: FakeDeviceRegistry()
    )
    monkeypatch.setattr(
        deepal_integration.dr,
        "async_entries_for_config_entry",
        lambda registry, entry_id: [
            SimpleNamespace(id="dev-keep", identifiers={("deepal", "car-1")}),
        ],
    )

    coordinator = SimpleNamespace(vehicles=[SimpleNamespace(car_id="car-1")])
    entry = SimpleNamespace(entry_id="entry-1")

    deepal_integration._remove_stale_vehicle_registry(
        SimpleNamespace(), entry, coordinator
    )

    assert removed_entities == []
    assert removed_devices == []


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
        # Deliberately no primary_config_entry: the modern lookup must not read
        # the deprecated compatibility property.
        config_entry_id = "entry-1"

    class FakeRegistry:
        def async_get_devices(self, *, identifiers):
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


def test_sda_unique_id_prefers_the_digit_only_phone() -> None:
    vehicles = [SimpleNamespace(vin="VIN-1")]

    unique_id = config_flow._sda_unique_id(
        " +34 600-000-000 ", vehicles, "tok123456789"
    )

    assert unique_id == "sda_phone_34600000000"


def test_sda_unique_id_falls_back_to_a_vin() -> None:
    vehicles = [SimpleNamespace(vin=""), SimpleNamespace(vin="VIN-2")]

    assert config_flow._sda_unique_id("", vehicles, "tok123456789") == "sda_vin_VIN-2"
    assert (
        config_flow._sda_unique_id("not-a-number", vehicles, "tok123456789")
        == "sda_vin_VIN-2"
    )


def test_sda_unique_id_falls_back_to_the_token_fragment() -> None:
    token = "tok123456789"

    assert config_flow._sda_unique_id("", [], token) == token[:10]


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


def test_charging_binary_sensor_exposes_the_session_attributes() -> None:
    class _Store:
        async def async_load(self):
            return None

        def async_delay_save(self, data, delay):
            pass

        async def async_remove(self):
            pass

    coordinator = FakeCoordinator()
    vehicle = _fake_vehicle()
    manager = ChargingSessionManager(_Store())
    coordinator.charging = manager
    manager.apply("car-1", True, 40, 210, datetime(2026, 10, 13, 12, 0, tzinfo=UTC))

    descriptions = {d.key: d for d in binary_sensor.BINARY_SENSORS}
    charging = binary_sensor.DeepalBinarySensor(
        coordinator, vehicle, descriptions["charging"]
    )

    assert charging._attr_unique_id == "deepal_car-1_charging"
    assert charging.device_class is binary_sensor.BinarySensorDeviceClass.BATTERY_CHARGING
    assert charging.extra_state_attributes["current_charge"]["start_level"] == 40

    other = binary_sensor.DeepalBinarySensor(
        coordinator, vehicle, descriptions["front_left_seat_heating"]
    )
    assert other.extra_state_attributes is None


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


def test_seat_level_unknown_and_out_of_range_are_hidden() -> None:
    coordinator = FakeCoordinator()
    condition = VehicleCondition(car_id="car-1", vin="test-vin")
    condition.seats.front_left.heating_level = None
    condition.seats.front_right.ventilation_level = 6
    coordinator.data["car-1"] = condition
    vehicle = _fake_vehicle()

    driver_heat = number.DeepalSeatLevelNumber(
        coordinator, vehicle, "front_left", "heating"
    )
    passenger_wind = number.DeepalSeatLevelNumber(
        coordinator, vehicle, "front_right", "ventilation"
    )
    descriptions = {d.key: d for d in binary_sensor.BINARY_SENSORS}
    heating_binary = binary_sensor.DeepalBinarySensor(
        coordinator, vehicle, descriptions["front_left_seat_heating"]
    )
    ventilation_binary = binary_sensor.DeepalBinarySensor(
        coordinator, vehicle, descriptions["front_right_seat_ventilation"]
    )

    assert driver_heat.native_value is None
    assert passenger_wind.native_value is None
    assert heating_binary.is_on is None
    assert ventilation_binary.is_on is None


def test_defrost_entity_is_retired() -> None:
    keys = {description.key for description in binary_sensor.BINARY_SENSORS}
    assert "defrost" not in keys

    removed: list[str] = []

    class _Registry:
        def async_get_entity_id(self, platform, domain, unique_id):
            assert (platform, domain) == ("binary_sensor", "deepal")
            assert unique_id == "deepal_car-1_defrost"
            return "binary_sensor.deepal_defrost"

        def async_remove(self, entity_id):
            removed.append(entity_id)

    binary_sensor._remove_retired_entities(
        _Registry(), SimpleNamespace(car_id="car-1")
    )

    assert removed == ["binary_sensor.deepal_defrost"]


def test_new_telemetry_entities_are_created() -> None:
    sensor_keys = {description.key for description in sensor.SENSORS}
    assert {
        "climate_target_temperature",
        "fan_level",
        "license_plate",
        "window_opening_front_left",
        "window_opening_front_right",
        "window_opening_rear_left",
        "window_opening_rear_right",
    } <= sensor_keys

    binary_keys = {description.key for description in binary_sensor.BINARY_SENSORS}
    assert {
        "key_battery_low",
        "air_recirculation",
        "rear_fog_lamp",
        "warning_12v_battery",
        "warning_tpms",
        "warning_abs",
        "warning_airbag",
        "warning_brake_fluid",
        "warning_brake",
        "warning_eps",
        "warning_power_limit",
        "warning_power_system",
        "warning_traction_battery_low",
        "warning_coolant_temperature",
    } <= binary_keys


def test_window_opening_sensors_are_disabled_by_default() -> None:
    coordinator = FakeCoordinator()
    vehicle = _fake_vehicle()
    descriptions = {description.key: description for description in sensor.SENSORS}

    opening = sensor.DeepalSensor(
        coordinator, vehicle, descriptions["window_opening_front_left"]
    )
    target = sensor.DeepalSensor(
        coordinator, vehicle, descriptions["climate_target_temperature"]
    )

    assert opening.entity_registry_enabled_default is False
    assert opening.unique_id == "deepal_car-1_window_opening_front_left"
    assert target.entity_registry_enabled_default is True
    assert target.unique_id == "deepal_car-1_climate_target_temperature"


def test_warning_entities_stay_unknown_when_not_reported() -> None:
    coordinator = FakeCoordinator()
    condition = VehicleCondition(car_id="car-1", vin="test-vin")
    coordinator.data["car-1"] = condition
    vehicle = _fake_vehicle()
    descriptions = {description.key: description for description in binary_sensor.BINARY_SENSORS}

    warning = binary_sensor.DeepalBinarySensor(
        coordinator, vehicle, descriptions["warning_tpms"]
    )
    key_battery = binary_sensor.DeepalBinarySensor(
        coordinator, vehicle, descriptions["key_battery_low"]
    )

    assert warning.is_on is None
    assert key_battery.is_on is None


def _model_vehicle(car_id: str, **fields) -> SimpleNamespace:
    values = {
        "car_id": car_id,
        "vin": "test-vin",
        "series_name": None,
        "series_code": None,
        "model_name": None,
        "model_code": None,
        "car_name": None,
        "thumbnail_url": None,
    }
    values.update(fields)
    return SimpleNamespace(**values)


def test_charge_limit_is_not_offered_on_the_s05() -> None:
    s05 = _model_vehicle(
        "car-1",
        series_name="S05",
        series_code="C857-EU",
        model_code="SC6464AAKBEV",
    )
    s05_by_code = _model_vehicle("car-2", series_code="c857-eu")
    s05_by_name = _model_vehicle("car-3", model_name="Deepal S05")

    assert number.supports_charge_limit(s05) is False
    assert number.supports_charge_limit(s05_by_code) is False
    assert number.supports_charge_limit(s05_by_name) is False


def test_charge_limit_is_kept_for_other_and_unknown_models() -> None:
    s07 = _model_vehicle("car-1", series_name="S07", series_code="C673-EU")
    unknown = _model_vehicle("car-2", series_name="Deepal X")
    missing = _model_vehicle("car-3")

    assert number.supports_charge_limit(s07) is True
    assert number.supports_charge_limit(unknown) is True
    assert number.supports_charge_limit(missing) is True


def test_build_control_numbers_skips_the_charge_limit_on_the_s05() -> None:
    coordinator = FakeCoordinator()
    s05 = _model_vehicle("car-1", series_name="S05", series_code="C857-EU")
    s07 = _model_vehicle("car-2", series_name="S07", series_code="C673-EU")

    s05_ids = [
        entity.unique_id
        for entity in number.build_control_numbers(coordinator, s05)
    ]
    s07_ids = [
        entity.unique_id
        for entity in number.build_control_numbers(coordinator, s07)
    ]

    assert "deepal_car-1_charge_limit" not in s05_ids
    assert len(s05_ids) == 4
    assert any(uid.endswith("seat_front_left_heating_control") for uid in s05_ids)
    assert "deepal_car-2_charge_limit" in s07_ids
    assert len(s07_ids) == 5


def test_is_s05_matches_name_and_code() -> None:
    assert is_s05(_model_vehicle("car-1", series_name="S05")) is True
    assert is_s05(_model_vehicle("car-2", series_code="c857-eu")) is True
    assert is_s05(_model_vehicle("car-3", model_name="Deepal S05")) is True
    assert (
        is_s05(_model_vehicle("car-4", series_name="S07", series_code="C673-EU"))
        is False
    )
    assert is_s05(_model_vehicle("car-5")) is False


def test_build_sensors_skips_s05_unsupported_entities() -> None:
    coordinator = FakeCoordinator()
    coordinator.client = object.__new__(DeepalIntlClient)
    coordinator.mqtt_vehicles = {"car-1", "car-2"}
    s05 = _model_vehicle("car-1", series_name="S05", series_code="C857-EU")
    s07 = _model_vehicle("car-2", series_name="S07", series_code="C673-EU")

    s05_keys = {
        entity.translation_key for entity in sensor.build_sensors(coordinator, s05)
    }
    s07_keys = {
        entity.translation_key for entity in sensor.build_sensors(coordinator, s07)
    }

    assert sensor.S05_UNSUPPORTED_SENSOR_KEYS.isdisjoint(s05_keys)
    assert sensor.S05_UNSUPPORTED_SENSOR_KEYS <= s07_keys
    assert "inside_temperature" in s05_keys
    assert {"mileage_yesterday", "trip_mileage"}.isdisjoint(s05_keys)
    assert {"mileage_yesterday", "trip_mileage"} <= s07_keys
    rear_seats = {"seat_heating_level_rear_left", "seat_heating_level_rear_right"}
    assert rear_seats.isdisjoint(s05_keys)
    assert rear_seats <= s07_keys


def test_is_bev_matches_the_model_token() -> None:
    assert (
        is_bev(_model_vehicle("car-1", model_code="SC6464AAKBEV", series_name="S05"))
        is True
    )
    assert (
        is_bev(_model_vehicle("car-2", model_code="SC6464AAKPHEV", series_name="S05"))
        is False
    )
    assert is_bev(_model_vehicle("car-3", series_name="Deepal S07")) is False


def test_supports_fuel_requires_capability_and_non_bev_model() -> None:
    phev = _model_vehicle("car-1", series_name="S05", model_code="SC6464AAKPHEV")
    bev = _model_vehicle("car-2", series_name="S05", model_code="SC6464AAKBEV")
    unknown = _model_vehicle("car-3", series_name="Deepal X")
    fuel_capabilities = VehicleCapabilities.from_codes(["#oilMileage"])
    no_fuel_capabilities = VehicleCapabilities.from_codes(["#ota"])

    assert fuel_capabilities.has_fuel is True
    assert no_fuel_capabilities.has_fuel is False
    assert supports_fuel(phev, fuel_capabilities) is True
    assert supports_fuel(unknown, fuel_capabilities) is True
    assert supports_fuel(bev, fuel_capabilities) is False
    assert supports_fuel(phev, no_fuel_capabilities) is False
    assert supports_fuel(phev, None) is False


def test_build_sensors_adds_fuel_only_for_fuel_vehicles() -> None:
    coordinator = FakeCoordinator()
    coordinator.client = object.__new__(DeepalIntlClient)
    coordinator.capabilities = {
        "car-1": VehicleCapabilities.from_codes(["#oilMileage"]),
        "car-2": VehicleCapabilities.from_codes(["#oilMileage"]),
        "car-3": VehicleCapabilities.from_codes(["#ota"]),
    }
    phev = _model_vehicle("car-1", series_name="S05", model_code="SC6464AAKPHEV")
    bev = _model_vehicle("car-2", series_name="S05", model_code="SC6464AAKBEV")
    electric_without_codes = _model_vehicle("car-3", series_name="Deepal S07")

    phev_keys = {
        entity.translation_key for entity in sensor.build_sensors(coordinator, phev)
    }
    bev_keys = {
        entity.translation_key for entity in sensor.build_sensors(coordinator, bev)
    }
    electric_keys = {
        entity.translation_key
        for entity in sensor.build_sensors(coordinator, electric_without_codes)
    }

    assert sensor.FUEL_SENSOR_KEYS <= phev_keys
    assert sensor.FUEL_SENSOR_KEYS.isdisjoint(bev_keys)
    assert sensor.FUEL_SENSOR_KEYS.isdisjoint(electric_keys)


def test_build_binary_sensors_skips_s05_unsupported_entities() -> None:
    coordinator = FakeCoordinator()
    coordinator.client = object.__new__(DeepalIntlClient)
    s05 = _model_vehicle("car-1", series_name="S05", series_code="C857-EU")
    s07 = _model_vehicle("car-2", series_name="S07", series_code="C673-EU")

    s05_keys = {
        entity.translation_key
        for entity in binary_sensor.build_binary_sensors(coordinator, s05)
    }
    s07_keys = {
        entity.translation_key
        for entity in binary_sensor.build_binary_sensors(coordinator, s07)
    }

    assert binary_sensor.S05_UNSUPPORTED_BINARY_SENSOR_KEYS.isdisjoint(s05_keys)
    assert binary_sensor.S05_UNSUPPORTED_BINARY_SENSOR_KEYS <= s07_keys
    assert "front_left_seat_heating" in s05_keys
    assert "front_left_seat_heating" in s07_keys


def _control_client(control_pin: str | None) -> DeepalIntlClient:
    client = object.__new__(DeepalIntlClient)
    client.private_key_pem = "test-private-key"
    client.control_pin = control_pin
    return client


@pytest.mark.parametrize(
    ("control_pin", "requires_pin", "expected"),
    [
        (None, True, 0),
        (None, False, 1),
        ("1234", True, 1),
    ],
)
def test_control_entities_require_the_control_pin(
    control_pin: str | None, requires_pin: bool, expected: int
) -> None:
    coordinator = FakeCoordinator()
    coordinator.client = _control_client(control_pin)
    coordinator.vehicles = [_fake_vehicle()]
    entry = SimpleNamespace(runtime_data=SimpleNamespace(coordinator=coordinator))
    added: list = []

    entity.async_setup_control_entities(
        None,
        entry,
        added.extend,
        lambda coordinator, vehicle: [object()],
        requires_control_pin=requires_pin,
    )

    assert len(added) == expected


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

    async def control_doors(self, vehicle_id: str, open_value: bool) -> str:
        self.calls.append(("doors", vehicle_id, open_value))
        return "cmd-1"

    async def control_windows(self, vehicle_id: str, open_value: bool) -> str:
        self.calls.append(("windows", vehicle_id, open_value))
        return "cmd-1"

    async def control_trunk(self, vehicle_id: str, open_value: bool) -> str:
        self.calls.append(("trunk", vehicle_id, open_value))
        return "cmd-1"

    async def control_air_conditioner(
        self, vehicle_id: str, enabled: bool, target_temp_c: float
    ) -> str:
        self.calls.append(("air", vehicle_id, enabled, target_temp_c))
        return "cmd-1"


class _FakeCommandCoordinator(FakeCoordinator):
    """Run commands synchronously and apply the optimistic update."""

    def __init__(self, condition) -> None:
        super().__init__()
        self.data = {condition.car_id: condition}
        self.client = _FakeCommandClient()
        self.last_wake_first: bool | None = None

    async def async_execute_command(
        self,
        vehicle_id,
        send_command,
        *,
        is_done=None,
        optimistic_update=None,
        cooldown_key=None,
        wake_first=None,
        timeout=None,
        interval=None,
    ) -> None:
        self.last_cooldown_key = cooldown_key
        self.last_wake_first = wake_first
        await send_command()
        if optimistic_update is not None:
            current = self.data.get(vehicle_id)
            if current is not None:
                self.data[vehicle_id] = optimistic_update(current)


@pytest.mark.asyncio
async def test_entity_command_failures_are_translated() -> None:
    class FailingCoordinator(_FakeCommandCoordinator):
        async def async_execute_command(self, *args, **kwargs):
            raise DeepalError("boom")

    condition = VehicleCondition(car_id="car-1", vin="test-vin")
    coordinator = FailingCoordinator(condition)
    doors = lock.DeepalDoorsLock(coordinator, _fake_vehicle())

    with pytest.raises(HomeAssistantError) as err:
        await doors.async_lock()

    assert err.value.translation_domain == "deepal"
    assert err.value.translation_key == "command_failed"
    assert err.value.translation_placeholders == {"error": "boom"}


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
    assert coordinator.last_cooldown_key is None

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


@pytest.mark.asyncio
async def test_climate_clamps_the_target_to_the_supported_range() -> None:
    condition = VehicleCondition(car_id="car-1", vin="test-vin")
    condition.climate.target_temperature_c = 17.0
    coordinator = _FakeCommandCoordinator(condition)
    entity = climate.DeepalCabinClimateEntity(coordinator, _fake_vehicle())

    assert entity.min_temp == 18.0
    assert entity.max_temp == 32.0
    await entity.async_turn_on()

    assert coordinator.client.calls == [("air", "car-1", True, 18.0)]
    assert condition.climate.target_temperature_c == 18.0

    await entity.async_set_temperature(temperature=16.0)
    assert coordinator.client.calls[-1] == ("air", "car-1", True, 18.0)

    await entity.async_set_temperature(temperature=31.0)
    assert coordinator.client.calls[-1] == ("air", "car-1", True, 31.0)

    await entity.async_set_temperature(temperature=33.0)
    assert coordinator.client.calls[-1] == ("air", "car-1", True, 32.0)


@pytest.mark.asyncio
async def test_pin_entities_request_a_wake_before_the_command() -> None:
    condition = VehicleCondition(car_id="car-1", vin="test-vin")
    coordinator = _FakeCommandCoordinator(condition)
    vehicle = _fake_vehicle()
    doors = lock.DeepalDoorsLock(coordinator, vehicle)
    windows = cover.DeepalWindowsCover(coordinator, vehicle)
    trunk = cover.DeepalTrunkCover(coordinator, vehicle)

    await doors.async_unlock()
    assert coordinator.last_wake_first is True

    await windows.async_open_cover()
    assert coordinator.last_wake_first is True

    await trunk.async_open_cover()
    assert coordinator.last_wake_first is True

    assert [call[0] for call in coordinator.client.calls] == [
        "doors",
        "windows",
        "trunk",
    ]


def test_icons_are_translated() -> None:
    icons = json.loads(
        (INTEGRATION_DIR / "icons.json").read_text(encoding="utf-8")
    )["entity"]

    assert icons["binary_sensor"]["trunk"]["default"] == "mdi:car-select"
    assert icons["number"]["charge_limit"]["default"] == "mdi:battery-heart"
    assert icons["sensor"]["tire_pressure_front_left"]["default"] == "mdi:tire"
    assert (
        icons["binary_sensor"]["tire_alarm_front_left"]["default"]
        == "mdi:car-tire-alert"
    )


def test_entities_have_no_hardcoded_icons() -> None:
    for platform, entities in _entities_by_platform().items():
        for entity in entities:
            assert entity.icon is None, f"{platform}:{entity.translation_key}"


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


def test_exception_translations_are_complete() -> None:
    languages = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in TRANSLATION_FILES
    }
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(INTEGRATION_DIR.rglob("*.py"))
    )
    keys = set(re.findall(r'translation_key="(\w+)"', source))

    assert keys
    for name, data in languages.items():
        exceptions = data.get("exceptions", {})
        for key in keys:
            message = exceptions.get(key, {}).get("message")
            assert message, f"{name}:exceptions.{key}"


def test_spanish_entity_names_are_corrected() -> None:
    data = json.loads(
        (INTEGRATION_DIR / "translations" / "es.json").read_text(encoding="utf-8")
    )
    assert (
        data["entity"]["button"]["flash_lights"]["name"]
        == "Encender luces de emergencia"
    )
    assert data["entity"]["sensor"]["total_odometer"]["name"] == "Kilometraje total"


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


def test_intl_code_menu_options_are_implemented() -> None:
    data = json.loads((INTEGRATION_DIR / "strings.json").read_text(encoding="utf-8"))
    menu = data["config"]["step"]["intl_code_menu"]
    options = menu["menu_options"]

    assert set(options) == {
        "intl_email_code",
        "intl_sms_code",
        "intl_code_resend",
        "intl_email_change",
        "intl_sms_change",
    }
    for option in options:
        assert hasattr(
            config_flow.DeepalConfigFlow, f"async_step_{option}"
        ), option
    assert "{destination}" in menu["description"]


def test_sms_step_warns_about_the_delivery_failure() -> None:
    data = json.loads((INTEGRATION_DIR / "strings.json").read_text(encoding="utf-8"))
    description = data["config"]["step"]["intl_phone"]["description"]

    assert "not delivering SMS" in description
    assert "email" in description


def test_repair_issue_translations_are_fixable_or_described() -> None:
    """An issue entry accepts a description or a fix_flow, never both.

    hassfest builds two exclusive groups that share the "fixable" key, so the
    three keys end up in one exclusion group: an issue carrying a description
    and a fix_flow fails the translation check and hassfest rejects the file.
    """
    paths = [INTEGRATION_DIR / "strings.json"] + sorted(
        (INTEGRATION_DIR / "translations").glob("*.json")
    )

    for path in paths:
        issues = json.loads(path.read_text(encoding="utf-8")).get("issues", {})
        for key, node in issues.items():
            assert "title" in node, (path.name, key)
            has_description = "description" in node
            has_fix_flow = "fix_flow" in node
            assert has_description or has_fix_flow, (path.name, key)
            assert not (has_description and has_fix_flow), (path.name, key)


def test_readme_documents_removal_and_automation_examples() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "## Automation examples" in readme
    assert "## Removal" in readme
    for language in ("en", "es", "de", "fr", "it", "pt"):
        assert f"guides/installation-guide.{language}.md" in readme


def test_integration_has_no_removed_api_references() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(INTEGRATION_DIR.rglob("*.py"))
    )
    assert "hass.data[DOMAIN]" not in source


class _DiagnosticsCoordinator:
    """Coordinator double for the diagnostics report."""

    def __init__(self, vehicles, conditions, capabilities, attempts=None) -> None:
        self.vehicles = vehicles
        self.data = conditions
        self._capabilities = capabilities
        self._attempts = attempts or {}

    def vehicle_capabilities(self, car_id: str):
        return self._capabilities.get(car_id)

    def mqtt_attempt(self, car_id: str):
        return self._attempts.get(car_id)


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
    condition.condition_source = "sda-mqtt"
    condition.mqtt_variants = {
        "sda-mqtt": {"soc": 71},
        "sda-mqtt-sections": {},
    }
    condition.sda_plan = {
        "device_did": "plan-did",
        "service_code": "CarCondition",
        "command_code": "Get_CarCondition",
        "property_codes": ["carCondition"],
        "strategy_codes": [],
        "strategy_ids": [],
    }
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
        [vehicle],
        {"car-1": _mqtt_condition()},
        {"car-1": capabilities},
        {
            "car-1": {
                "source": None,
                "variants": {"sda-mqtt": {}, "sda-mqtt-sections": {}},
                "plan": {"device_did": "plan-did"},
            }
        },
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
    assert report["condition_sources"]["car-1"] == "sda-mqtt"
    assert report["raw_mqtt_variants"]["car-1"] == {
        "sda-mqtt": {"soc": 71},
        "sda-mqtt-sections": {},
    }
    assert report["sda_plans"]["car-1"]["device_did"] == REDACTED
    assert report["sda_plans"]["car-1"]["property_codes"] == ["carCondition"]
    assert report["mqtt_attempts"]["car-1"]["variants"]["sda-mqtt"] == {}
    assert report["mqtt_attempts"]["car-1"]["plan"] == {"device_did": REDACTED}
    assert "mqtt_variants" not in report["mapped_telemetry"]["car-1"]
    assert "sda_plan" not in report["mapped_telemetry"]["car-1"]
    assert report["unmapped_mqtt_keys"]["car-1"] == [
        "chargeCoverStatus",
        "latitude",
    ]


@pytest.mark.asyncio
async def test_diagnostics_report_redacts_credentials_and_locations() -> None:
    vehicle = Vehicle(
        car_id="car-1",
        vin="VIN-REAL-1",
        license_plate="1234-ABC",
        thumbnail_url="https://example.invalid/car.png",
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
    assert "1234-ABC" not in serialized
    assert report["vehicles"][0]["vin"] == REDACTED
    assert report["vehicles"][0]["license_plate"] == REDACTED
    assert report["config_entry_data"]["access_token"] == REDACTED
    assert report["raw_mqtt"]["car-1"]["latitude"] == REDACTED
    assert report["capabilities"]["car-1"] is None


@pytest.mark.asyncio
async def test_diagnostics_report_redacts_case_insensitively_and_masks_topics() -> None:
    vehicle = Vehicle(car_id="car-1", vin="VIN-REAL-1")
    condition = _mqtt_condition()
    condition.raw_data = {
        "vehicleStatus": {
            "soc": 55,
            "Lat": 12.3456,
            "Lng": -98.7654,
            "nested": [{"plateNumber": "0000-ZZZ", "totalOdometer": 4321}],
        }
    }
    condition.mqtt_raw_data = {"soc": 55, "Lat": 12.3456}
    coordinator = _DiagnosticsCoordinator(
        [vehicle],
        {"car-1": condition},
        {},
        {
            "car-1": {
                "source": None,
                "variants": {"sda-mqtt": {"reqTopic": "$vdp/did-abc123/server/event"}},
                "plan": {"device_did": "did-abc123"},
            }
        },
    )

    report = await diagnostics.async_get_config_entry_diagnostics(
        None, _diagnostics_entry(coordinator)
    )
    serialized = json.dumps(report)

    assert report["raw_rest"]["car-1"]["vehicleStatus"]["Lat"] == REDACTED
    assert report["raw_rest"]["car-1"]["vehicleStatus"]["Lng"] == REDACTED
    assert (
        report["raw_rest"]["car-1"]["vehicleStatus"]["nested"][0]["plateNumber"]
        == REDACTED
    )
    assert report["mqtt_attempts"]["car-1"]["plan"]["device_did"] == REDACTED
    assert "0000-ZZZ" not in serialized
    assert "12.3456" not in serialized
    assert "did-abc123" not in serialized
    assert "$vdp/**REDACTED**/server/event" in serialized
    # The report must keep being usable: structure and innocent values survive.
    assert (
        report["raw_rest"]["car-1"]["vehicleStatus"]["nested"][0]["totalOdometer"]
        == 4321
    )
    assert isinstance(report["unmapped_mqtt_keys"]["car-1"], list)


@pytest.mark.asyncio
async def test_diagnostics_report_survives_an_empty_entry() -> None:
    coordinator = _DiagnosticsCoordinator([], {}, {})

    report = await diagnostics.async_get_config_entry_diagnostics(
        None, _diagnostics_entry(coordinator)
    )

    assert report["vehicles"] == []
    assert report["mapped_telemetry"] == {}
    assert report["raw_mqtt"] == {}
    assert report["condition_sources"] == {}
    assert report["raw_mqtt_variants"] == {}
    assert report["sda_plans"] == {}
    assert report["mqtt_attempts"] == {}
    assert report["unmapped_mqtt_keys"] == {}


def test_login_options_include_australia_and_the_environment() -> None:
    assert config_flow.COUNTRY_OPTIONS["AU"] == "Australia (+61)"
    assert config_flow.COUNTRY_DIAL_CODES["AU"] == "61"

    selector_config = config_flow._environment_selector().config
    values = [option["value"] for option in selector_config["options"]]
    assert values == [
        "release_eu",
        "release_znm",
        "release_ase",
        "release_ase_connect",
    ]


def test_login_client_uses_the_selected_environment() -> None:
    flow = object.__new__(config_flow.DeepalConfigFlow)
    flow._reauth_identity = {}

    client = flow._intl_login_client("AU", "release_ase")

    assert client.environment == "release_ase"
    assert client.base_url == "https://m.iov.changanauto.sg"
    assert client.app_id == "ca"


@pytest.mark.asyncio
async def test_diagnostics_report_keeps_the_raw_sda_payload() -> None:
    vehicle = Vehicle(car_id="car-1", vin="VIN", protocol_type="SDA-MQTT")
    condition = _mqtt_condition()
    condition.condition_source = "sda-rest"
    condition.mqtt_raw_data = {"DrvrDoorLockLogicSts": 2, "VIUSocDisp": 80}
    coordinator = _DiagnosticsCoordinator([vehicle], {"car-1": condition}, {})

    report = await diagnostics.async_get_config_entry_diagnostics(
        None, _diagnostics_entry(coordinator)
    )

    assert report["raw_sda"]["car-1"]["DrvrDoorLockLogicSts"] == 2
    assert report["raw_sda"]["car-1"]["VIUSocDisp"] == 80


def test_options_flow_lists_the_supported_environments() -> None:
    from custom_components.deepal.deepal.endpoints import INTL_ENVIRONMENTS

    labels = [environment.label for environment in INTL_ENVIRONMENTS.values()]
    assert labels == ["Europe", "Latin America", "ASEAN", "ASEAN CONNECT"]


def test_options_schema_exposes_the_wake_toggle() -> None:
    from custom_components.deepal.const import (
        CONF_ENVIRONMENT,
        CONF_WAKE,
        DEFAULT_WAKE,
    )

    flow = object.__new__(config_flow.DeepalOptionsFlow)
    schema = flow._options_schema({CONF_ENVIRONMENT: "release_eu"})

    wake_keys = [key for key in schema.schema if key.schema == CONF_WAKE]
    assert len(wake_keys) == 1
    assert wake_keys[0].default() == DEFAULT_WAKE
    assert schema({CONF_WAKE: False})[CONF_WAKE] is False


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





class _PinClient(DeepalIntlClient):
    """Control-code exchange double for the options PIN check."""

    def __init__(self, error: Exception | None = None) -> None:
        self.private_key_pem = "test-private-key"
        self.error = error
        self.calls: list[str] = []

    async def check_control_code(self, control_pin: str) -> str:
        self.calls.append(control_pin)
        if self.error is not None:
            raise self.error
        return "rc-token"


@pytest.mark.asyncio
async def test_control_pin_validation_error_mapping() -> None:
    client = _PinClient()
    stored = "1234"
    assert await config_flow._control_pin_validation_error(
        stored, {CONF_CONTROL_PIN: "1234"}, client
    ) == {}
    assert await config_flow._control_pin_validation_error(
        stored, {CONF_CONTROL_PIN: ""}, client
    ) == {}
    assert client.calls == []

    assert await config_flow._control_pin_validation_error(
        stored, {CONF_CONTROL_PIN: "9999"}, client
    ) == {}
    assert client.calls == ["9999"]

    client.error = DeepalAPIError("COMMON_1_1_01_005")
    assert await config_flow._control_pin_validation_error(
        stored, {CONF_CONTROL_PIN: "0000"}, client
    ) == {"base": "invalid_pin"}

    client.error = DeepalRateLimitError("no attempts left")
    assert await config_flow._control_pin_validation_error(
        stored, {CONF_CONTROL_PIN: "0000"}, client
    ) == {"base": "pin_rate_limited"}
def test_remaining_charge_time_formatted_sensor() -> None:
    assert sensor.format_hours_minutes(None) is None
    assert sensor.format_hours_minutes(45) == "0:45"
    assert sensor.format_hours_minutes(95) == "1:35"
    assert sensor.format_hours_minutes(-5) == "0:00"

    coordinator = FakeCoordinator()
    condition = VehicleCondition(car_id="car-1", vin="test-vin")
    condition.battery.remaining_charge_time_min = 95
    coordinator.data["car-1"] = condition
    vehicle = _fake_vehicle()
    descriptions = {d.key: d for d in sensor.SENSORS}
    formatted = sensor.DeepalSensor(
        coordinator, vehicle, descriptions["remaining_charge_time_formatted"]
    )
    duration = sensor.DeepalSensor(
        coordinator, vehicle, descriptions["remaining_charge_time"]
    )

    assert formatted.native_value == "1:35"
    assert duration.native_value == 95
    assert duration._attr_device_class is sensor.SensorDeviceClass.DURATION
