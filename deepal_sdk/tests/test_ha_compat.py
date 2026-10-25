"""Home Assistant integration regression tests (2026.8 baseline).

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
    UnitOfVolume,
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
from custom_components.deepal.coordinator import WakeResult
from custom_components.deepal.const import (
    CONF_ACCESS_TOKEN,
    CONF_CONTROL_PIN,
    CONF_VEHICLE_ID,
)
from custom_components.deepal.deepal import (
    DeepalAPIError,
    DeepalAuthError,
    DeepalError,
    DeepalIntlClient,
    DeepalRateLimitError,
    VehicleCapabilities,
)
from custom_components.deepal.vehicle_model import (
    is_bev,
    is_s05,
    supports_charge_limit,
    supports_fuel,
)
from deepal.models import Vehicle, VehicleCondition

from homeassistant.components.diagnostics.const import REDACTED
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
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
        data={
            DATA_ASYNC_CLIENT: {
                (False, SSL_ALPN_HTTP11): SimpleNamespace(),
                (True, SSL_ALPN_HTTP11): SimpleNamespace(),
            }
        },
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
        car_platform=None,
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
            sensor.DeepalChargeStatusSensor(coordinator, vehicle),
            sensor.DeepalPowerStatusSensor(coordinator, vehicle),
            sensor.DeepalChargeModeSensor(coordinator, vehicle),
            *(
                sensor.DeepalSensor(coordinator, vehicle, description)
                for description in sensor.SENSORS
                if description.key != "charge_status"
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


@pytest.mark.asyncio
async def test_refresh_button_skips_the_full_poll_after_a_fresh_wake() -> None:
    coordinator = FakeCoordinator()
    vehicle = _fake_vehicle()
    refresh = button.DeepalRefreshButton(coordinator, vehicle)
    calls: list[str] = []

    async def refresh_vehicle(car_id: str) -> WakeResult:
        calls.append("refresh")
        return WakeResult.FRESH

    async def request_refresh() -> None:
        calls.append("poll")

    coordinator.async_refresh_vehicle = refresh_vehicle
    coordinator.async_request_refresh = request_refresh

    await refresh.async_press()

    assert calls == ["refresh"]


@pytest.mark.asyncio
async def test_refresh_button_does_not_inquire_when_the_wake_is_not_needed() -> None:
    coordinator = FakeCoordinator()
    vehicle = _fake_vehicle()
    refresh = button.DeepalRefreshButton(coordinator, vehicle)
    calls: list[str] = []

    async def refresh_vehicle(car_id: str) -> WakeResult:
        calls.append("refresh")
        return WakeResult.NOT_NEEDED

    async def condition_inquiry(car_id: str) -> None:
        calls.append("inquiry")

    async def request_refresh() -> None:
        calls.append("poll")

    coordinator.async_refresh_vehicle = refresh_vehicle
    coordinator.async_condition_inquiry = condition_inquiry
    coordinator.async_request_refresh = request_refresh

    await refresh.async_press()

    assert calls == ["refresh", "poll"]


@pytest.mark.asyncio
async def test_refresh_button_falls_back_after_a_failed_wake() -> None:
    coordinator = FakeCoordinator()
    vehicle = _fake_vehicle()
    refresh = button.DeepalRefreshButton(coordinator, vehicle)
    calls: list[str] = []

    async def refresh_vehicle(car_id: str) -> WakeResult:
        calls.append("refresh")
        return WakeResult.FAILED

    async def condition_inquiry(car_id: str) -> None:
        calls.append("inquiry")

    async def request_refresh() -> None:
        calls.append("poll")

    coordinator.async_refresh_vehicle = refresh_vehicle
    coordinator.async_condition_inquiry = condition_inquiry
    coordinator.async_request_refresh = request_refresh

    await refresh.async_press()

    assert calls == ["refresh", "inquiry", "poll"]


@pytest.mark.asyncio
async def test_refresh_button_falls_back_when_the_wake_is_throttled() -> None:
    coordinator = FakeCoordinator()
    vehicle = _fake_vehicle()
    refresh = button.DeepalRefreshButton(coordinator, vehicle)
    calls: list[str] = []

    async def refresh_vehicle(car_id: str) -> WakeResult:
        calls.append("refresh")
        return WakeResult.THROTTLED

    async def condition_inquiry(car_id: str) -> None:
        calls.append("inquiry")

    async def request_refresh() -> None:
        calls.append("poll")

    coordinator.async_refresh_vehicle = refresh_vehicle
    coordinator.async_condition_inquiry = condition_inquiry
    coordinator.async_request_refresh = request_refresh

    await refresh.async_press()

    assert calls == ["refresh", "inquiry", "poll"]


@pytest.mark.asyncio
async def test_refresh_button_reports_no_fresh_report() -> None:
    coordinator = FakeCoordinator()
    vehicle = _fake_vehicle()
    refresh = button.DeepalRefreshButton(coordinator, vehicle)

    async def refresh_vehicle(car_id: str) -> WakeResult:
        return WakeResult.NO_REPORT

    coordinator.async_refresh_vehicle = refresh_vehicle

    with pytest.raises(HomeAssistantError) as err:
        await refresh.async_press()

    assert err.value.translation_key == "wake_no_fresh_report"


def test_hacs_metadata_declares_supported_baseline() -> None:
    metadata = json.loads(HACS_METADATA.read_text(encoding="utf-8"))
    assert metadata["name"] == "Deepal Alternative"
    assert metadata["homeassistant"] == "2026.8.0"
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


def test_build_client_without_access_token_requests_reauth() -> None:
    entry = SimpleNamespace(data={}, options={})

    with pytest.raises(ConfigEntryAuthFailed):
        deepal_integration._build_client(SimpleNamespace(), entry)


def test_build_client_drops_an_unusable_private_key(monkeypatch) -> None:
    shared = object()
    monkeypatch.setattr(deepal_integration, "get_async_client", lambda hass: shared)
    entry = SimpleNamespace(
        entry_id="entry-1",
        data={
            "platform": "intl",
            "access_token": "test_token_123",
            "private_key": "not-a-pem",
            "public_key": "test-public-key",
        },
        options={},
    )

    client = deepal_integration._build_client(SimpleNamespace(), entry)

    assert client.private_key_pem is None
    assert client.public_key is None


@pytest.mark.asyncio
async def test_unload_uses_the_platforms_recorded_at_setup() -> None:
    from homeassistant.const import Platform

    captured: dict[str, list[Platform]] = {}
    closed: list[bool] = []

    async def unload_platforms(entry, platforms):
        captured["platforms"] = list(platforms)
        return True

    async def close() -> None:
        closed.append(True)

    platforms = [
        Platform.SENSOR,
        Platform.BINARY_SENSOR,
        Platform.IMAGE,
        Platform.DEVICE_TRACKER,
    ]
    entry = SimpleNamespace(
        entry_id="entry-1",
        data={"platform": "intl", "private_key": "test-private-key"},
        options={"enable_location": False},
        runtime_data=SimpleNamespace(
            platforms=platforms,
            client=SimpleNamespace(close=close),
            coordinator=SimpleNamespace(model_assets=None),
            model_assets=None,
        ),
    )
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_unload_platforms=unload_platforms)
    )

    assert await deepal_integration.async_unload_entry(hass, entry) is True
    assert captured["platforms"] == platforms
    assert closed == [True]


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
    hass = SimpleNamespace(data={})

    deepal_integration._remove_stale_vehicle_registry(hass, entry, coordinator, now=0.0)

    assert removed_entities == []
    assert removed_devices == []

    deepal_integration._remove_stale_vehicle_registry(
        hass, entry, coordinator, now=deepal_integration.VEHICLE_REMOVAL_GRACE
    )

    assert removed_entities == ["sensor.stale"]
    assert removed_devices == ["dev-stale"]


def test_setup_reconciliation_clears_the_grace_when_the_vehicle_returns(
    monkeypatch,
) -> None:
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
                unique_id="deepal_car-9_battery_soc", entity_id="sensor.stale"
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
            SimpleNamespace(id="dev-9", identifiers={("deepal", "car-9")}),
        ],
    )
    entry = SimpleNamespace(entry_id="entry-1")
    hass = SimpleNamespace(data={})
    missing = SimpleNamespace(vehicles=[SimpleNamespace(car_id="car-1")])
    returned = SimpleNamespace(
        vehicles=[SimpleNamespace(car_id="car-1"), SimpleNamespace(car_id="car-9")]
    )

    deepal_integration._remove_stale_vehicle_registry(
        hass, entry, missing, now=0.0
    )
    deepal_integration._remove_stale_vehicle_registry(
        hass, entry, returned, now=10.0
    )

    assert removed_entities == []
    assert removed_devices == []
    assert hass.data[deepal_integration.DOMAIN].get(
        deepal_integration.DATA_PENDING_VEHICLE_REMOVALS
    ) == {}


@pytest.mark.asyncio
async def test_delayed_registry_cleanup_removes_after_the_grace(monkeypatch) -> None:
    removed_entities: list[str] = []
    removed_devices: list[str] = []
    reloads: list[str] = []

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
                unique_id="deepal_car-9_battery_soc", entity_id="sensor.stale"
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
            SimpleNamespace(id="dev-9", identifiers={("deepal", "car-9")}),
        ],
    )
    monkeypatch.setattr(deepal_integration._time, "monotonic", lambda: 2000.0)
    coordinator = SimpleNamespace(
        vehicles=[SimpleNamespace(car_id="car-1")]
    )
    entry = SimpleNamespace(
        entry_id="entry-1",
        runtime_data=SimpleNamespace(coordinator=coordinator),
    )
    hass = SimpleNamespace(
        data={
            deepal_integration.DOMAIN: {
                deepal_integration.DATA_PENDING_VEHICLE_REMOVALS: {
                    "entry-1": {"car-9": 0.0}
                }
            }
        },
        config_entries=SimpleNamespace(
            async_schedule_reload=reloads.append
        ),
    )

    await deepal_integration._async_remove_stale_after_grace(hass, entry)

    assert removed_entities == ["sensor.stale"]
    assert removed_devices == ["dev-9"]
    assert reloads == ["entry-1"]
    assert deepal_integration._has_pending_vehicle_removals(hass, entry) is False


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
        SimpleNamespace(data={}), entry, coordinator
    )

    assert removed_entities == []
    assert removed_devices == []


def test_setup_reconciliation_keeps_everything_with_empty_vehicle_list(monkeypatch) -> None:
    """An empty freshly fetched list is an anomaly, never a removal event."""
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

    coordinator = SimpleNamespace(vehicles=[])
    entry = SimpleNamespace(entry_id="entry-1")

    deepal_integration._remove_stale_vehicle_registry(
        SimpleNamespace(data={}), entry, coordinator
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


def test_sda_unique_id_falls_back_to_an_opaque_token_digest() -> None:
    import hashlib

    token = "tok123456789"
    expected = "sda_token_" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]

    unique_id = config_flow._sda_unique_id("", [], token)

    assert unique_id == expected
    assert token[:10] not in unique_id


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


def test_retired_entities_are_removed() -> None:
    keys = {description.key for description in binary_sensor.BINARY_SENSORS}
    assert {"warning_airbag", "warning_coolant_temperature"} <= keys
    assert {
        "defrost",
        "driver_door_unlocked",
        "passenger_door_unlocked",
    }.isdisjoint(keys)

    removed: list[str] = []

    class _Registry:
        def async_get_entity_id(self, platform, domain, unique_id):
            assert (platform, domain) == ("binary_sensor", "deepal")
            return f"binary_sensor.{unique_id}"

        def async_remove(self, entity_id):
            removed.append(entity_id)

    binary_sensor._remove_retired_entities(
        _Registry(), SimpleNamespace(car_id="car-1")
    )

    assert sorted(removed) == [
        "binary_sensor.deepal_car-1_defrost",
        "binary_sensor.deepal_car-1_driver_door_unlocked",
        "binary_sensor.deepal_car-1_passenger_door_unlocked",
    ]


def test_ac_gun_binary_sensor_follows_the_model() -> None:
    coordinator = FakeCoordinator()
    condition = VehicleCondition(car_id="car-1", vin="test-vin")
    coordinator.data["car-1"] = condition
    descriptions = {description.key: description for description in binary_sensor.BINARY_SENSORS}
    entity = binary_sensor.DeepalBinarySensor(
        coordinator, _fake_vehicle(), descriptions["ac_gun_connected"]
    )

    assert entity._attr_unique_id == "deepal_car-1_ac_gun_connected"
    assert entity._attr_translation_key == "ac_gun_connected"
    assert entity.device_class is binary_sensor.BinarySensorDeviceClass.PLUG

    condition.battery.ac_gun_connected = True
    assert entity.is_on is True
    condition.battery.ac_gun_connected = False
    assert entity.is_on is False
    condition.battery.ac_gun_connected = None
    assert entity.is_on is None


def test_new_telemetry_entities_are_created() -> None:
    sensor_keys = {description.key for description in sensor.SENSORS}
    assert {
        "climate_target_temperature",
        "fan_level",
        "outside_temperature",
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
        "ac_gun_connected",
        "dc_gun_connected",
    } <= binary_keys


def test_restored_warning_entities_are_enabled_diagnostics() -> None:
    coordinator = FakeCoordinator()
    condition = VehicleCondition(
        car_id="car-1",
        vin="test-vin",
        warnings={"airbag": True, "coolant_temperature": False},
    )
    coordinator.data["car-1"] = condition
    vehicle = _fake_vehicle()
    descriptions = {d.key: d for d in binary_sensor.BINARY_SENSORS}

    airbag = binary_sensor.DeepalBinarySensor(
        coordinator, vehicle, descriptions["warning_airbag"]
    )
    coolant = binary_sensor.DeepalBinarySensor(
        coordinator, vehicle, descriptions["warning_coolant_temperature"]
    )

    assert airbag.unique_id == "deepal_car-1_warning_airbag"
    assert coolant.unique_id == "deepal_car-1_warning_coolant_temperature"
    assert airbag.entity_registry_enabled_default is True
    assert coolant.entity_registry_enabled_default is True
    assert (
        descriptions["warning_airbag"].entity_category
        is binary_sensor.EntityCategory.DIAGNOSTIC
    )
    assert (
        descriptions["warning_coolant_temperature"].entity_category
        is binary_sensor.EntityCategory.DIAGNOSTIC
    )
    assert airbag.is_on is True
    assert coolant.is_on is False


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


def test_charge_limit_is_not_offered_on_the_s05_without_the_capability() -> None:
    s05 = _model_vehicle(
        "car-1",
        series_name="S05",
        series_code="C857-EU",
        model_code="SC6464AAKBEV",
    )
    s05_by_code = _model_vehicle("car-2", series_code="c857-eu")
    s05_by_name = _model_vehicle("car-3", model_name="Deepal S05")
    no_code = VehicleCapabilities.from_codes(["#battery", "#chargingInfo"])

    assert supports_charge_limit(s05, None) is False
    assert supports_charge_limit(s05_by_code, None) is False
    assert supports_charge_limit(s05_by_name, None) is False
    assert supports_charge_limit(s05, no_code) is False
    assert supports_charge_limit(s05_by_code, no_code) is False


def test_charge_limit_is_offered_on_the_s05_phev_by_capabilities() -> None:
    phev = _model_vehicle("car-1", series_name="Deepal S05 PHEV", series_code="C857-EU")
    phev_by_code = _model_vehicle("car-2", series_code="c857-phev")
    capabilities = VehicleCapabilities.from_codes(["#oilMileage", "#chargeSet"])

    assert supports_charge_limit(phev, capabilities) is True
    assert supports_charge_limit(phev_by_code, capabilities) is True


def test_charge_limit_is_kept_for_other_and_unknown_models() -> None:
    s07 = _model_vehicle("car-1", series_name="S07", series_code="C673-EU")
    unknown = _model_vehicle("car-2", series_name="Deepal X")
    missing = _model_vehicle("car-3")
    no_code = VehicleCapabilities.from_codes(["#ota"])

    assert supports_charge_limit(s07, None) is True
    assert supports_charge_limit(unknown, None) is True
    assert supports_charge_limit(missing, None) is True
    assert supports_charge_limit(s07, no_code) is True
    assert supports_charge_limit(unknown, no_code) is True


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


def test_build_control_numbers_include_the_charge_limit_on_the_s05_phev() -> None:
    coordinator = FakeCoordinator()
    coordinator.capabilities["car-1"] = VehicleCapabilities.from_codes(
        ["#oilMileage", "#chargeSet"]
    )
    phev = _model_vehicle("car-1", series_name="Deepal S05 PHEV", series_code="C857-EU")

    phev_ids = [
        entity.unique_id
        for entity in number.build_control_numbers(coordinator, phev)
    ]

    assert "deepal_car-1_charge_limit" in phev_ids
    assert len(phev_ids) == 5


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

    s05_entities = sensor.build_sensors(coordinator, s05)
    s07_entities = sensor.build_sensors(coordinator, s07)
    s05_keys = {entity.translation_key for entity in s05_entities}
    s07_keys = {entity.translation_key for entity in s07_entities}

    assert sensor.S05_UNSUPPORTED_SENSOR_KEYS.isdisjoint(s05_keys)
    assert sensor.S05_UNSUPPORTED_SENSOR_KEYS <= s07_keys
    assert "inside_temperature" in s05_keys
    assert "outside_temperature" in s05_keys
    assert "outside_temperature" in s07_keys
    assert {"mileage_yesterday", "trip_mileage"}.isdisjoint(s05_keys)
    assert {"mileage_yesterday", "trip_mileage"} <= s07_keys
    rear_seats = {"seat_heating_level_rear_left", "seat_heating_level_rear_right"}
    assert rear_seats.isdisjoint(s05_keys)
    assert rear_seats <= s07_keys
    assert "power_status" in s05_keys and "power_status" in s07_keys
    assert "charge_mode" in s05_keys
    assert "charge_mode" not in s07_keys
    assert isinstance(
        next(
            entity
            for entity in s05_entities
            if entity.translation_key == "charge_status"
        ),
        sensor.DeepalChargeStatusSensor,
    )
    assert type(
        next(
            entity
            for entity in s07_entities
            if entity.translation_key == "charge_status"
        )
    ) is sensor.DeepalSensor


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
        "car-1": VehicleCapabilities.from_codes(["#oilMileage", "#chargeSet"]),
        "car-2": VehicleCapabilities.from_codes(["#oilMileage"]),
        "car-3": VehicleCapabilities.from_codes(["#ota"]),
    }
    phev = _model_vehicle("car-1", series_name="S05", model_code="SC6464AAKPHEV")
    bev = _model_vehicle("car-2", series_name="S05", model_code="SC6464AAKBEV")
    electric_without_codes = _model_vehicle("car-3", series_name="Deepal S07")
    s05_without_codes = _model_vehicle("car-4", series_name="S05", series_code="C857-EU")

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
    s05_keys = {
        entity.translation_key
        for entity in sensor.build_sensors(coordinator, s05_without_codes)
    }

    assert sensor.FUEL_SENSOR_KEYS <= phev_keys
    assert sensor.FUEL_SENSOR_KEYS.isdisjoint(bev_keys)
    assert sensor.FUEL_SENSOR_KEYS.isdisjoint(electric_keys)
    assert "charge_limit" in phev_keys
    assert "charge_limit" not in bev_keys
    assert "charge_limit" not in s05_keys


def test_fuel_volume_sensor_exposes_litres() -> None:
    coordinator = FakeCoordinator()
    condition = VehicleCondition(car_id="car-1", vin="test-vin")
    condition.fuel.volume_l = 28.5
    coordinator.data["car-1"] = condition
    vehicle = _fake_vehicle()
    descriptions = {description.key: description for description in sensor.SENSORS}
    entity = sensor.DeepalSensor(
        coordinator, vehicle, descriptions["fuel_volume"]
    )

    assert entity.native_value == 28.5
    assert entity._attr_unique_id == "deepal_car-1_fuel_volume"
    assert entity._attr_device_class is sensor.SensorDeviceClass.VOLUME_STORAGE
    assert entity._attr_state_class is sensor.SensorStateClass.MEASUREMENT
    assert entity._attr_native_unit_of_measurement is UnitOfVolume.LITERS


def test_fuel_tank_capacity_uses_stored_volume_semantics() -> None:
    descriptions = {description.key: description for description in sensor.SENSORS}
    description = descriptions["fuel_tank_capacity"]

    assert description.device_class is sensor.SensorDeviceClass.VOLUME_STORAGE
    assert description.state_class is None
    assert description.native_unit_of_measurement is UnitOfVolume.LITERS


def test_sensor_descriptions_use_valid_ha_state_classes() -> None:
    from homeassistant.components.sensor.const import DEVICE_CLASS_STATE_CLASSES

    for description in sensor.SENSORS:
        if description.device_class is None or description.state_class is None:
            continue
        allowed = DEVICE_CLASS_STATE_CLASSES.get(description.device_class)
        assert allowed is None or description.state_class in allowed, (
            f"{description.key} uses {description.state_class} with "
            f"{description.device_class}"
        )


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
    assert icons["binary_sensor"]["hood"]["default"] == "mdi:car-select"
    assert icons["cover"]["trunk"]["default"] == "mdi:car-select"
    assert icons["binary_sensor"]["high_beam"]["default"] == "mdi:car-light-high"
    assert icons["binary_sensor"]["low_beam"]["default"] == "mdi:car-light-dimmed"
    assert (
        icons["binary_sensor"]["left_turn_signal"]["default"]
        == "mdi:car-arrow-left"
    )
    assert (
        icons["binary_sensor"]["right_turn_signal"]["default"]
        == "mdi:car-arrow-right"
    )
    assert (
        icons["binary_sensor"]["climate_on"]["default"]
        == icons["climate"]["cabin_climate"]["default"]
        == "mdi:air-conditioner"
    )
    assert (
        icons["binary_sensor"]["front_left_seat_heating"]["default"]
        == "mdi:car-seat-heater"
    )
    assert (
        icons["binary_sensor"]["front_right_seat_heating"]["default"]
        == "mdi:car-seat-heater"
    )
    assert (
        icons["binary_sensor"]["front_left_seat_ventilation"]["default"]
        == "mdi:car-seat-cooler"
    )
    assert (
        icons["binary_sensor"]["front_right_seat_ventilation"]["default"]
        == "mdi:car-seat-cooler"
    )
    assert (
        icons["sensor"]["seat_heating_level_front_left"]["default"]
        == "mdi:car-seat-heater"
    )
    assert (
        icons["sensor"]["seat_heating_level_front_right"]["default"]
        == "mdi:car-seat-heater"
    )
    assert (
        icons["sensor"]["seat_ventilation_level_front_left"]["default"]
        == "mdi:car-seat-cooler"
    )
    assert (
        icons["sensor"]["seat_ventilation_level_front_right"]["default"]
        == "mdi:car-seat-cooler"
    )
    assert icons["number"]["charge_limit"]["default"] == "mdi:battery-heart"
    assert (
        icons["sensor"]["climate_target_temperature"]["default"]
        == "mdi:snowflake-variant"
    )
    assert icons["sensor"]["tire_pressure_front_left"]["default"] == "mdi:tire"
    assert {
        icons["binary_sensor"][key]["default"]
        for key in (
            "tire_alarm_front_left",
            "tire_alarm_front_right",
            "tire_alarm_rear_left",
            "tire_alarm_rear_right",
        )
    } == {"mdi:car-tire-alert"}
    assert not any(
        key.startswith("window_open_") for key in icons["binary_sensor"]
    )


def test_device_tracker_platform_is_gated_by_the_option() -> None:
    from homeassistant.const import Platform

    from custom_components.deepal import _platforms
    from custom_components.deepal.const import (
        CONF_ENABLE_LOCATION,
        CONF_PRIVATE_KEY,
        CONF_PLATFORM,
        PLATFORM_INTL,
    )

    entry = SimpleNamespace(
        data={CONF_PLATFORM: PLATFORM_INTL, CONF_PRIVATE_KEY: "key"},
        options={},
    )
    assert Platform.DEVICE_TRACKER not in _platforms(entry)

    entry.options = {CONF_ENABLE_LOCATION: True}
    assert Platform.DEVICE_TRACKER in _platforms(entry)


def test_location_tracker_exposes_the_condition_coordinates() -> None:
    from custom_components.deepal import device_tracker as tracker_platform

    coordinator = FakeCoordinator()
    condition = VehicleCondition(
        car_id="car-1", vin="test-vin", latitude=41.65, longitude=-0.89
    )
    coordinator.data["car-1"] = condition

    entity = tracker_platform.DeepalLocationTracker(coordinator, _fake_vehicle())

    assert entity.unique_id == "deepal_car-1_location"
    assert entity.translation_key == "location"
    assert entity.source_type is tracker_platform.SourceType.GPS
    assert entity.latitude == 41.65
    assert entity.longitude == -0.89

    condition.latitude = None
    condition.longitude = None
    assert entity.latitude is None
    assert entity.longitude is None


def test_tire_alarm_sensors_are_diagnostic() -> None:
    from homeassistant.const import EntityCategory

    coordinator = FakeCoordinator()
    coordinator.data["car-1"] = VehicleCondition(car_id="car-1", vin="test-vin")

    entity = binary_sensor.DeepalTireAlarmBinarySensor(
        coordinator, _fake_vehicle(), "front_left"
    )

    assert entity.entity_category is EntityCategory.DIAGNOSTIC
    assert entity.unique_id == "deepal_car-1_tire_front_left_alarm"


def test_climate_on_binary_sensor_mirrors_the_climate_state() -> None:
    coordinator = FakeCoordinator()
    condition = VehicleCondition(
        car_id="car-1", vin="test-vin", climate={"power_on": True}
    )
    coordinator.data["car-1"] = condition
    descriptions = {
        description.key: description for description in binary_sensor.BINARY_SENSORS
    }

    entity = binary_sensor.DeepalBinarySensor(
        coordinator, _fake_vehicle(), descriptions["climate_on"]
    )

    assert entity.is_on is True

    condition.climate.power_on = False
    assert entity.is_on is False

    condition.climate.power_on = None
    assert entity.is_on is None


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
    assert data["entity"]["binary_sensor"]["tire_alarm_front_left"]["name"] == (
        "Testigo de presión neumático delantero izquierdo"
    )
    assert data["entity"]["binary_sensor"]["tire_alarm_rear_right"]["name"] == (
        "Testigo de presión neumático trasero derecho"
    )
    assert data["entity"]["binary_sensor"]["warning_brake"]["name"] == (
        "Testigo de frenos"
    )
    assert data["entity"]["binary_sensor"]["warning_eps"]["name"] == (
        "Testigo de dirección asistida"
    )
    assert data["entity"]["binary_sensor"]["rear_fog_lamp"]["name"] == (
        "Luz antiniebla trasera"
    )
    assert data["entity"]["binary_sensor"]["window_open_front_left"]["name"] == (
        "Ventanilla delantera izquierda"
    )
    assert data["entity"]["binary_sensor"]["doors_lock_state"]["name"] == (
        "Cierre centralizado"
    )
    assert data["entity"]["climate"]["cabin_climate"]["name"] == "Climatización"
    assert data["entity"]["sensor"]["charge_mode"]["state"] == {
        "ac": "CA",
        "dc": "CC",
    }


def test_diagnostic_telemetry_is_categorized() -> None:
    from homeassistant.const import EntityCategory

    descriptions = {d.key: d for d in binary_sensor.BINARY_SENSORS}
    assert descriptions["connected"].entity_category is EntityCategory.DIAGNOSTIC
    assert descriptions["hood"].entity_category is None

    entity = sensor.DeepalSeatLevelSensor(
        FakeCoordinator(), _fake_vehicle(), "front_left", "heating_level"
    )
    assert entity.entity_category is EntityCategory.DIAGNOSTIC

    for key in (
        "front_left_seat_heating",
        "front_right_seat_heating",
        "front_left_seat_ventilation",
        "front_right_seat_ventilation",
    ):
        assert descriptions[key].entity_category is EntityCategory.DIAGNOSTIC

    steering = binary_sensor.DeepalSteeringWheelHeaterBinarySensor(
        FakeCoordinator(), _fake_vehicle()
    )
    assert steering.entity_category is EntityCategory.DIAGNOSTIC


def test_engine_binary_sensor_uses_the_power_device_class() -> None:
    descriptions = {d.key: d for d in binary_sensor.BINARY_SENSORS}
    assert (
        descriptions["engine"].device_class
        is binary_sensor.BinarySensorDeviceClass.POWER
    )


def test_steering_wheel_heater_level_sensor_is_retired() -> None:
    assert sensor.REMOVED_SENSOR_KEYS == frozenset({"steering_wheel_heater_level"})
    assert "steering_wheel_heater_level" not in {
        description.key for description in sensor.SENSORS
    }

    coordinator = FakeCoordinator()
    coordinator.client = object.__new__(DeepalIntlClient)
    keys = {
        entity.translation_key
        for entity in sensor.build_sensors(
            coordinator, _model_vehicle("car-1", series_name="Deepal S07")
        )
    }
    assert "steering_wheel_heater_level" not in keys

    removed: list[str] = []

    class _Registry:
        def async_get_entity_id(self, platform, domain, unique_id):
            assert (platform, domain) == ("sensor", "deepal")
            return f"sensor.{unique_id}"

        def async_remove(self, entity_id):
            removed.append(entity_id)

    sensor._remove_retired_entities(
        _Registry(), SimpleNamespace(car_id="car-1")
    )

    assert removed == ["sensor.deepal_car-1_steering_wheel_heater_level"]


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
        for section in init.get("sections", {}).values():
            assert section.get("name") and section.get("description")
            assert set(section.get("data", {})) == set(
                section.get("data_description", {})
            )


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

    def __init__(
        self, vehicles, conditions, capabilities, attempts=None, wakes=None
    ) -> None:
        self.vehicles = vehicles
        self.data = conditions
        self._capabilities = capabilities
        self._attempts = attempts or {}
        self._wakes = wakes or {}

    def vehicle_capabilities(self, car_id: str):
        return self._capabilities.get(car_id)

    def mqtt_attempt(self, car_id: str):
        return self._attempts.get(car_id)

    def wake_result(self, car_id: str):
        return self._wakes.get(car_id)


def _diagnostics_entry(coordinator) -> SimpleNamespace:
    return SimpleNamespace(
        data={
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
            "cac_token": "test-cac-token",
            "user_id": "test-user-1",
            "private_key": "test-private-key",
            "public_key": "PUBKEY-BODY-BASE64-ABC",
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
        car_platform=2,
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
        {
            "car-1": {
                "result": "fresh",
                "wake_sent": True,
                "timeout_s": 30.0,
            }
        },
    )

    report = await diagnostics.async_get_config_entry_diagnostics(
        None, _diagnostics_entry(coordinator)
    )

    assert report["vehicles"][0]["car_platform"] == 2
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
    assert report["wake_results"]["car-1"]["result"] == "fresh"
    assert report["wake_results"]["car-1"]["wake_sent"] is True
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
    condition = _mqtt_condition()
    condition.raw_data["secretKey"] = "secret-mqtt-token"
    condition.mqtt_raw_data["smsCode"] = "sms-123456"
    coordinator = _DiagnosticsCoordinator(
        [vehicle], {"car-1": condition}, {"car-1": None}
    )

    report = await diagnostics.async_get_config_entry_diagnostics(
        None, _diagnostics_entry(coordinator)
    )
    serialized = json.dumps(report)

    assert "VIN-REAL-1" not in serialized
    assert "test-access-token" not in serialized
    assert "test-private-key" not in serialized
    assert "PUBKEY-BODY-BASE64-ABC" not in serialized
    assert "secret-mqtt-token" not in serialized
    assert "sms-123456" not in serialized
    assert "1234" not in json.dumps(report["config_entry_data"])
    assert "600000000" not in serialized
    assert "1234-ABC" not in serialized
    assert report["vehicles"][0]["vin"] == REDACTED
    assert report["vehicles"][0]["license_plate"] == REDACTED
    assert report["config_entry_data"]["access_token"] == REDACTED
    assert report["config_entry_data"]["public_key"] == REDACTED
    assert report["raw_rest"]["car-1"]["secretKey"] == REDACTED
    assert report["raw_mqtt"]["car-1"]["smsCode"] == REDACTED
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


def test_login_client_discards_an_unusable_stored_key() -> None:
    from custom_components.deepal.const import CONF_PRIVATE_KEY, CONF_PUBLIC_KEY

    flow = object.__new__(config_flow.DeepalConfigFlow)
    flow._reauth_identity = {
        CONF_PRIVATE_KEY: "not-a-pem",
        CONF_PUBLIC_KEY: "test-public-key",
    }

    client = flow._intl_login_client("ES")

    assert client.private_key_pem is None
    assert client.public_key is None


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


def test_options_schema_exposes_the_location_toggle() -> None:
    from custom_components.deepal.const import (
        CONF_ENABLE_LOCATION,
        CONF_ENVIRONMENT,
        DEFAULT_ENABLE_LOCATION,
    )

    flow = object.__new__(config_flow.DeepalOptionsFlow)
    schema = flow._options_schema({CONF_ENVIRONMENT: "release_eu"})

    location_keys = [
        key for key in schema.schema if key.schema == CONF_ENABLE_LOCATION
    ]
    assert len(location_keys) == 1
    assert location_keys[0].default() == DEFAULT_ENABLE_LOCATION
    assert DEFAULT_ENABLE_LOCATION is False
    assert schema({CONF_ENABLE_LOCATION: True})[CONF_ENABLE_LOCATION] is True


@pytest.mark.asyncio
async def test_options_flow_without_runtime_data_skips_the_pin_check() -> None:
    flow = object.__new__(config_flow.DeepalOptionsFlow)
    flow.handler = "entry-1"
    flow.hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_get_known_entry=lambda entry_id: SimpleNamespace(
                options={CONF_CONTROL_PIN: "old-pin"},
                data={},
            )
        )
    )

    errors = await flow._async_validate_control_pin({CONF_CONTROL_PIN: "new-pin"})

    assert errors == {}


@pytest.mark.asyncio
async def test_reauth_accepts_the_configured_vehicle_anywhere_in_the_list() -> None:
    from homeassistant.config_entries import SOURCE_REAUTH

    flow = object.__new__(config_flow.DeepalConfigFlow)
    flow.context = {"source": SOURCE_REAUTH}
    entry = SimpleNamespace(data={CONF_VEHICLE_ID: "car-2"})
    flow._get_reauth_entry = lambda: entry
    captured: dict[str, Any] = {}

    def _update_reload_and_abort(entry_arg, *, data_updates, reason):
        captured["entry"] = entry_arg
        captured["vehicle_id"] = data_updates[CONF_VEHICLE_ID]
        captured["reason"] = reason
        return FlowResultType.ABORT

    flow.async_update_reload_and_abort = _update_reload_and_abort

    class _FlowClient:
        private_key_pem = "test-private-key"
        public_key = "test-public-key"
        device_id = "test-device-id"
        user_id = "test-user-1"

        async def get_vehicles(self):
            return [
                Vehicle(car_id="car-1", vin="VIN-PLACEHOLDER-1"),
                Vehicle(car_id="car-2", vin="VIN-PLACEHOLDER-2"),
            ]

        async def close(self):
            pass

    token = SimpleNamespace(
        access_token="test-access-token",
        refresh_token="test-refresh-token",
        cac_token="test-cac-token",
        user_id="test-user-1",
    )

    result = await flow._async_finish_intl_login(
        _FlowClient(), token, {}
    )

    assert result == FlowResultType.ABORT
    assert captured["entry"] is entry
    assert captured["vehicle_id"] == "car-2"
    assert captured["reason"] == "reauth_successful"


@pytest.mark.asyncio
async def test_reauth_rejects_a_different_stored_user_id() -> None:
    from homeassistant.config_entries import SOURCE_REAUTH

    from custom_components.deepal.const import CONF_USER_ID

    flow = object.__new__(config_flow.DeepalConfigFlow)
    flow.context = {"source": SOURCE_REAUTH}
    entry = SimpleNamespace(
        data={CONF_USER_ID: "user-a", CONF_VEHICLE_ID: "car-1"}
    )
    flow._get_reauth_entry = lambda: entry

    class _FlowClient:
        private_key_pem = "test-private-key"
        public_key = "test-public-key"
        device_id = "test-device-id"
        user_id = "user-b"

        async def get_vehicles(self):
            return [Vehicle(car_id="car-1", vin="VIN-PLACEHOLDER-1")]

        async def close(self):
            pass

    token = SimpleNamespace(
        access_token="test-access-token",
        refresh_token="test-refresh-token",
        cac_token="test-cac-token",
        user_id="user-b",
    )

    result = await flow._async_finish_intl_login(
        _FlowClient(), token, {}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"


@pytest.mark.asyncio
async def test_reauth_accepts_a_replaced_vehicle_for_the_same_user() -> None:
    from homeassistant.config_entries import SOURCE_REAUTH

    from custom_components.deepal.const import CONF_USER_ID

    flow = object.__new__(config_flow.DeepalConfigFlow)
    flow.context = {"source": SOURCE_REAUTH}
    entry = SimpleNamespace(
        data={CONF_USER_ID: "user-a", CONF_VEHICLE_ID: "car-old"}
    )
    flow._get_reauth_entry = lambda: entry
    captured: dict[str, Any] = {}

    def _update_reload_and_abort(entry_arg, *, data_updates, reason):
        captured["entry"] = entry_arg
        captured["vehicle_id"] = data_updates[CONF_VEHICLE_ID]
        captured["reason"] = reason
        return FlowResultType.ABORT

    flow.async_update_reload_and_abort = _update_reload_and_abort

    class _FlowClient:
        private_key_pem = "test-private-key"
        public_key = "test-public-key"
        device_id = "test-device-id"
        user_id = "user-a"

        async def get_vehicles(self):
            return [
                Vehicle(car_id="car-1", vin="VIN-PLACEHOLDER-1"),
                Vehicle(car_id="car-2", vin="VIN-PLACEHOLDER-2"),
            ]

        async def close(self):
            pass

    token = SimpleNamespace(
        access_token="test-access-token",
        refresh_token="test-refresh-token",
        cac_token="test-cac-token",
        user_id="user-a",
    )

    result = await flow._async_finish_intl_login(
        _FlowClient(), token, {}
    )

    assert result == FlowResultType.ABORT
    assert captured["entry"] is entry
    assert captured["vehicle_id"] == "car-1"
    assert captured["reason"] == "reauth_successful"


@pytest.mark.asyncio
async def test_reauth_aborts_when_the_vehicle_list_fails_after_login() -> None:
    from homeassistant.config_entries import SOURCE_REAUTH

    flow = object.__new__(config_flow.DeepalConfigFlow)
    flow.context = {"source": SOURCE_REAUTH}

    class _FlowClient:
        private_key_pem = "test-private-key"
        public_key = "test-public-key"
        device_id = "test-device-id"
        user_id = "user-a"

        async def get_vehicles(self):
            raise DeepalAPIError("gateway down")

        async def close(self):
            pass

    token = SimpleNamespace(
        access_token="test-access-token",
        refresh_token="test-refresh-token",
        cac_token="test-cac-token",
        user_id="user-a",
    )

    result = await flow._async_finish_intl_login(
        _FlowClient(), token, {}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


@pytest.mark.asyncio
async def test_sda_reauth_rejects_a_mismatched_vehicle(monkeypatch) -> None:
    from homeassistant.config_entries import SOURCE_REAUTH

    flow = object.__new__(config_flow.DeepalConfigFlow)
    flow.context = {"source": SOURCE_REAUTH}
    entry = SimpleNamespace(data={CONF_VEHICLE_ID: "car-9"})
    flow._get_reauth_entry = lambda: entry

    class _SdaClient:
        def __init__(self, access_token: str) -> None:
            self.access_token = access_token

        async def get_vehicles(self):
            return [Vehicle(car_id="car-1", vin="VIN-PLACEHOLDER-1")]

        async def close(self):
            pass

    monkeypatch.setattr(config_flow, "DeepalClient", _SdaClient)

    result = await flow.async_step_sda_reauth({CONF_ACCESS_TOKEN: "new-token"})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"


@pytest.mark.asyncio
async def test_sda_reauth_keeps_a_matching_vehicle(monkeypatch) -> None:
    from homeassistant.config_entries import SOURCE_REAUTH

    flow = object.__new__(config_flow.DeepalConfigFlow)
    flow.context = {"source": SOURCE_REAUTH}
    entry = SimpleNamespace(data={CONF_VEHICLE_ID: "car-1"})
    flow._get_reauth_entry = lambda: entry
    captured: dict[str, Any] = {}

    def _update_reload_and_abort(entry_arg, *, data_updates, reason):
        captured["entry"] = entry_arg
        captured["token"] = data_updates[CONF_ACCESS_TOKEN]
        captured["reason"] = reason
        return FlowResultType.ABORT

    flow.async_update_reload_and_abort = _update_reload_and_abort

    class _SdaClient:
        def __init__(self, access_token: str) -> None:
            self.access_token = access_token

        async def get_vehicles(self):
            return [Vehicle(car_id="car-1", vin="VIN-PLACEHOLDER-1")]

        async def close(self):
            pass

    monkeypatch.setattr(config_flow, "DeepalClient", _SdaClient)

    result = await flow.async_step_sda_reauth({CONF_ACCESS_TOKEN: "new-token"})

    assert result == FlowResultType.ABORT
    assert captured["entry"] is entry
    assert captured["token"] == "new-token"
    assert captured["reason"] == "reauth_successful"


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


def test_charge_status_sensor_maps_the_s05_states() -> None:
    coordinator = FakeCoordinator()
    condition = VehicleCondition(car_id="car-1", vin="test-vin")
    coordinator.data["car-1"] = condition
    entity = sensor.DeepalChargeStatusSensor(coordinator, _fake_vehicle())

    assert entity._attr_unique_id == "deepal_car-1_charge_status"
    assert entity._attr_device_class is sensor.SensorDeviceClass.ENUM
    assert entity._attr_options == list(sensor.CHARGE_STATUS_OPTIONS)

    expected = {
        "0": "not_charging",
        "1": "connected_ac",
        "2": "connected_dc",
        "3": "charging_ac",
        "4": "charging_dc",
        "5": "charge_stopped",
    }
    for raw, option in expected.items():
        condition.battery.charging_status = raw
        assert entity.native_value == option
        assert entity.extra_state_attributes == {"raw_charge_status": raw}

    condition.battery.charging_status = "9"
    assert entity.native_value is None
    assert entity.extra_state_attributes == {"raw_charge_status": "9"}

    condition.battery.charging_status = None
    assert entity.native_value is None
    assert entity.extra_state_attributes is None


def test_power_status_sensor_maps_the_verified_values() -> None:
    coordinator = FakeCoordinator()
    condition = VehicleCondition(car_id="car-1", vin="test-vin")
    coordinator.data["car-1"] = condition
    entity = sensor.DeepalPowerStatusSensor(coordinator, _fake_vehicle())

    assert entity._attr_unique_id == "deepal_car-1_power_status"
    assert entity._attr_options == list(sensor.POWER_STATUS_OPTIONS)

    condition.power_status = 0
    assert entity.native_value == "off"
    condition.power_status = 2
    assert entity.native_value == "on"
    assert entity.extra_state_attributes == {"raw_power_status": 2}
    condition.power_status = 1
    assert entity.native_value is None
    assert entity.extra_state_attributes == {"raw_power_status": 1}
    condition.power_status = None
    assert entity.native_value is None
    assert entity.extra_state_attributes is None


def test_charge_mode_sensor_derives_the_type() -> None:
    coordinator = FakeCoordinator()
    condition = VehicleCondition(car_id="car-1", vin="test-vin")
    coordinator.data["car-1"] = condition
    entity = sensor.DeepalChargeModeSensor(coordinator, _fake_vehicle())

    assert entity._attr_unique_id == "deepal_car-1_charge_mode"
    for raw, option in (("1", "ac"), ("3", "ac"), ("2", "dc"), ("4", "dc")):
        condition.battery.charging_status = raw
        assert entity.native_value == option
    for raw in ("0", "5", "9", None):
        condition.battery.charging_status = raw
        assert entity.native_value is None

    condition.battery.charging_status = "5"
    condition.battery.ac_gun_connected = True
    assert entity.native_value == "ac"
    condition.battery.ac_gun_connected = False
    condition.battery.dc_gun_connected = True
    assert entity.native_value == "dc"
    condition.battery.dc_gun_connected = False
    assert entity.native_value is None


def test_charge_enum_states_are_translated_in_every_language() -> None:
    for path in TRANSLATION_FILES:
        data = json.loads(path.read_text(encoding="utf-8"))
        states = data["entity"]["sensor"]["charge_status"]["state"]
        assert set(states) == set(sensor.CHARGE_STATUS_OPTIONS), path.name
        power_states = data["entity"]["sensor"]["power_status"]["state"]
        assert set(power_states) == set(sensor.POWER_STATUS_OPTIONS), path.name
        mode_states = data["entity"]["sensor"]["charge_mode"]["state"]
        assert set(mode_states) == {"ac", "dc"}, path.name


def test_options_schema_exposes_the_diagnostics_section() -> None:
    from custom_components.deepal.const import (
        CONF_DIAGNOSTICS_ACTION,
        CONF_DIAGNOSTICS_CONFIRM_DELETE,
        CONF_ENABLE_DIAGNOSTICS_CAPTURE,
        DIAGNOSTICS_ACTION_NONE,
    )

    flow = object.__new__(config_flow.DeepalOptionsFlow)
    schema = flow._options_schema({config_flow.CONF_ENVIRONMENT: "release_eu"})
    diagnostics_key = next(
        key for key in schema.schema if str(key) == config_flow.DIAGNOSTICS_SECTION
    )
    diagnostics_schema = schema.schema[diagnostics_key].schema

    assert diagnostics_schema({}) == {
        CONF_ENABLE_DIAGNOSTICS_CAPTURE: False,
        CONF_DIAGNOSTICS_ACTION: DIAGNOSTICS_ACTION_NONE,
        CONF_DIAGNOSTICS_CONFIRM_DELETE: False,
    }
    assert diagnostics_schema(
        {
            CONF_ENABLE_DIAGNOSTICS_CAPTURE: True,
            CONF_DIAGNOSTICS_ACTION: "new",
            CONF_DIAGNOSTICS_CONFIRM_DELETE: True,
        }
    ) == {
        CONF_ENABLE_DIAGNOSTICS_CAPTURE: True,
        CONF_DIAGNOSTICS_ACTION: "new",
        CONF_DIAGNOSTICS_CONFIRM_DELETE: True,
    }


def test_options_flow_splits_the_diagnostics_section() -> None:
    from custom_components.deepal.const import (
        CONF_DIAGNOSTICS_ACTION,
        CONF_DIAGNOSTICS_CONFIRM_DELETE,
        CONF_ENABLE_DIAGNOSTICS_CAPTURE,
        DIAGNOSTICS_ACTION_DELETE,
    )

    data, action, confirm = config_flow.DeepalOptionsFlow._split_diagnostics(
        {
            config_flow.DIAGNOSTICS_SECTION: {
                CONF_ENABLE_DIAGNOSTICS_CAPTURE: True,
                CONF_DIAGNOSTICS_ACTION: DIAGNOSTICS_ACTION_DELETE,
                CONF_DIAGNOSTICS_CONFIRM_DELETE: True,
            },
            "scan_interval": 60,
        }
    )

    assert data == {
        CONF_ENABLE_DIAGNOSTICS_CAPTURE: True,
        "scan_interval": 60,
    }
    assert action == DIAGNOSTICS_ACTION_DELETE
    assert confirm is True


def test_options_flow_rejects_an_unknown_diagnostics_action() -> None:
    data, action, confirm = config_flow.DeepalOptionsFlow._split_diagnostics(
        {
            config_flow.DIAGNOSTICS_SECTION: {
                "diagnostics_action": "not-an-action",
            }
        }
    )

    assert action == "none"
    assert confirm is False
    assert data == {}
