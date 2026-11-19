"""Tests for the Deepal charge-schedule service."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from homeassistant.exceptions import ServiceValidationError

from custom_components.deepal import services
from custom_components.deepal.deepal import (
    CommandResult,
    CommandResultStatus,
    DeepalIntlClient,
    VehicleCondition,
)
from custom_components.deepal.runtime_data import DeepalRuntimeData


class FakeClient(DeepalIntlClient):
    """Command double recording the model-aware service calls."""

    def __init__(self) -> None:
        self.deleted: list[tuple[str, str]] = []
        self.added: list[tuple] = []
        self.modified: list[tuple] = []
        self.fresh_condition = None

    async def get_vehicle_condition(self, car_id, vin=None, *, model_code=None):
        return self.fresh_condition

    async def control_charge_plan_delete(self, car_id: str, plan_id: str) -> str:
        self.deleted.append((car_id, plan_id))
        return "delete-command"

    async def control_charge_plan_add(
        self,
        car_id: str,
        start_time: str,
        end_time: str,
        end_switch: int,
        plan_type: int,
        time_format: int,
        time_zone: str,
    ) -> str:
        self.added.append(
            (car_id, start_time, end_time, end_switch, plan_type, time_format, time_zone)
        )
        return "add-command"

    async def control_charge_schedule(
        self,
        car_id: str,
        plan_id: str,
        start_time: str,
        end_time: str,
        enabled: bool,
        plan_type: int,
        time_format: int,
        time_zone: str,
    ) -> str:
        self.modified.append(
            (
                car_id,
                plan_id,
                start_time,
                end_time,
                enabled,
                plan_type,
                time_format,
                time_zone,
            )
        )
        return "modify-command"

    async def control_result_status(self, car_id: str, command_id: str):
        return CommandResult(status=CommandResultStatus.SUCCESS, code=0)


class FakeCoordinator:
    def __init__(self, vehicle, condition) -> None:
        self.vehicles = [vehicle]
        self.data = {vehicle.car_id: condition}
        self.commands: list[str] = []
        self.execute_kwargs: list[dict] = []
        self.refreshes = 0

    async def async_execute_command(self, car_id, send_command, **kwargs):
        self.commands.append(await send_command())
        self.execute_kwargs.append({"car_id": car_id, **kwargs})

    async def async_request_refresh(self) -> None:
        self.refreshes += 1


def _vehicle(model_code: str, series_name: str = "S05", series_code: str = "C857-EU"):
    return SimpleNamespace(
        car_id="car-1",
        series_name=series_name,
        series_code=series_code,
        model_name=None,
        model_code=model_code,
    )


def _condition(plans, plan_id: str = "1"):
    condition = VehicleCondition(car_id="car-1", vin="test-vin")
    condition.battery.charge_plan_id = plan_id
    condition.battery.charge_schedule_start = "0000"
    condition.battery.charge_schedule_end = "0100"
    condition.battery.charge_schedule_enabled = False
    condition.battery.charge_plan_valid = False
    condition.raw_data = {"charge": {"chargePlanList": plans}}
    return condition


def _call(hass, **data):
    return SimpleNamespace(hass=hass, data=data)


def _hass(vehicle, condition, client):
    coordinator = FakeCoordinator(vehicle, condition)
    coordinator.client = client
    client.fresh_condition = condition
    runtime = DeepalRuntimeData(client=client, coordinator=coordinator)
    entry = SimpleNamespace(entry_id="entry-1", runtime_data=runtime)
    hass = SimpleNamespace(
        config=SimpleNamespace(time_zone="Europe/Madrid"),
        config_entries=SimpleNamespace(async_entries=lambda domain: [entry]),
    )
    return hass, coordinator


@pytest.mark.asyncio
async def test_bev_enable_deletes_the_active_plan_and_adds_a_new_one() -> None:
    client = FakeClient()
    plans = [
        {"planId": 1, "isValid": 0, "startTime": "0000", "endTime": "0100"},
        {"planId": 99, "isValid": 1, "startTime": "0000", "endTime": "0100"},
    ]
    hass, coordinator = _hass(
        _vehicle("SC6464AAKBEV"), _condition(plans, plan_id="99"), client
    )

    response = await services._async_handle_set_charge_schedule(
        _call(hass, start_time="00:00", end_time="01:00", enabled=True)
    )

    assert response["strategy"] == "add-plan"
    assert response["vehicle_id"] == "car-1"
    assert client.deleted == [("car-1", "99")]
    assert len(client.added) == 1
    assert client.added[0][1:3] == ("0000", "0100")
    assert client.added[0][3] == 1
    assert client.added[0][6] in ("GMT+01:00", "GMT+02:00")
    assert coordinator.commands == ["delete-command", "add-command"]


@pytest.mark.asyncio
async def test_bev_disable_deletes_the_active_plan_without_adding() -> None:
    client = FakeClient()
    plans = [
        {"planId": 99, "isValid": 1, "startTime": "0000", "endTime": "0100"},
    ]
    hass, coordinator = _hass(
        _vehicle("SC6464AAKBEV"), _condition(plans, plan_id="99"), client
    )

    response = await services._async_handle_set_charge_schedule(
        _call(hass, start_time="0000", end_time="0100", enabled=False)
    )

    assert response["strategy"] == "delete-plan"
    assert client.deleted == [("car-1", "99")]
    assert client.added == []
    assert coordinator.commands == ["delete-command"]


@pytest.mark.asyncio
async def test_phev_updates_the_existing_plan() -> None:
    client = FakeClient()
    plans = [{"planId": 1, "isValid": 0, "startTime": "0000", "endTime": "0100"}]
    hass, coordinator = _hass(
        _vehicle("SC6460AAAA7HEV"), _condition(plans), client
    )

    response = await services._async_handle_set_charge_schedule(
        _call(hass, start_time="0000", end_time="0100", enabled=True)
    )

    assert response["strategy"] == "modify-plan"
    assert client.deleted == []
    assert client.added == []
    assert client.modified[0][0:2] == ("car-1", "1")
    assert client.modified[0][4] is True
    assert coordinator.commands == ["modify-command"]


def test_invalid_time_is_rejected() -> None:
    with pytest.raises(ServiceValidationError):
        services._normalize_time("2460")


@pytest.mark.asyncio
async def test_non_s05_is_rejected() -> None:
    client = FakeClient()
    hass, _ = _hass(
        _vehicle("SC6501ABABEV", series_name="S07", series_code="C673-EU"),
        _condition([]),
        client,
    )

    with pytest.raises(ServiceValidationError):
        await services._async_handle_set_charge_schedule(
            _call(hass, start_time="0000", end_time="0100", enabled=True)
        )


@pytest.mark.asyncio
async def test_service_registration_is_idempotent() -> None:
    class FakeServices:
        def __init__(self) -> None:
            self.registered: dict[str, tuple] = {}

        def has_service(self, domain: str, name: str) -> bool:
            return name in self.registered

        def async_register(self, domain: str, name: str, handler, **kwargs) -> None:
            self.registered[name] = (handler, kwargs)

    hass = SimpleNamespace(services=FakeServices())

    await services.async_register_services(hass)
    await services.async_register_services(hass)

    assert set(hass.services.registered) == {services.SERVICE_SET_CHARGE_SCHEDULE}


@pytest.mark.asyncio
async def test_bev_disable_uses_the_normalized_plan_without_a_raw_plan_list() -> None:
    client = FakeClient()
    condition = _condition([], plan_id="99")
    condition.battery.charge_plan_valid = True
    condition.battery.charge_schedule_start = "0000"
    condition.battery.charge_schedule_end = "0100"
    hass, coordinator = _hass(_vehicle("SC6464AAKBEV"), condition, client)

    response = await services._async_handle_set_charge_schedule(
        _call(hass, start_time="0000", end_time="0100", enabled=False)
    )

    assert response["strategy"] == "delete-plan"
    assert client.deleted == [("car-1", "99")]
    assert coordinator.commands == ["delete-command"]


@pytest.mark.asyncio
async def test_bev_disable_uses_the_fresh_plan_instead_of_the_stale_one() -> None:
    client = FakeClient()
    stored = _condition(
        [{"planId": 1, "isValid": 0, "startTime": "0000", "endTime": "0100"}],
        plan_id="1",
    )
    fresh = _condition(
        [{"planId": 99, "isValid": 1, "startTime": "0000", "endTime": "0100"}],
        plan_id="99",
    )
    fresh.battery.charge_schedule_enabled = True
    fresh.battery.charge_plan_valid = True
    hass, coordinator = _hass(_vehicle("SC6464AAKBEV"), stored, client)
    client.fresh_condition = fresh

    response = await services._async_handle_set_charge_schedule(
        _call(hass, start_time="0000", end_time="0100", enabled=False)
    )

    assert response["strategy"] == "delete-plan"
    assert client.deleted == [("car-1", "99")]
    assert coordinator.commands == ["delete-command"]


def test_add_plan_optimistic_update_clears_the_stale_plan_id() -> None:
    from custom_components.deepal.charge_schedule import _optimistic_schedule

    condition = _condition(
        [{"planId": 1, "isValid": 1, "startTime": "0000", "endTime": "0100"}],
        plan_id="1",
    )

    updated = _optimistic_schedule("0000", "0100", True, clear_plan=True)(condition)

    assert updated.battery.charge_plan_id is None
    assert updated.battery.charge_plans == []
    assert updated.battery.charge_plan_valid is True


@pytest.mark.asyncio
async def test_service_response_reports_the_plan_timezone() -> None:
    client = FakeClient()
    condition = _condition(
        [{"planId": 1, "isValid": 0, "startTime": "0000", "endTime": "0100"}],
        plan_id="1",
    )
    condition.battery.charge_plan_time_zone = "GMT+02:00"
    vehicle = _vehicle("SC6460AAAA7HEV")
    hass, _ = _hass(vehicle, condition, client)

    response = await services._async_handle_set_charge_schedule(
        _call(hass, start_time="0000", end_time="0100", enabled=True)
    )

    assert response["time_zone"] == "GMT+02:00"
    assert client.modified[-1][7] == "GMT+02:00"


@pytest.mark.asyncio
async def test_schedule_controls_use_the_plan_timezone(monkeypatch) -> None:
    from datetime import time as dt_time

    from custom_components.deepal import switch, time as time_platform

    client = FakeClient()
    condition = _condition(
        [{"planId": 1, "isValid": 0, "startTime": "0000", "endTime": "0100"}],
        plan_id="1",
    )
    condition.battery.charge_plan_time_zone = "GMT+02:00"
    vehicle = _vehicle("SC6460AAAA7HEV")
    hass, coordinator = _hass(vehicle, condition, client)
    monkeypatch.setattr(switch, "ha_gmt_offset", lambda hass: "GMT+01:00")
    monkeypatch.setattr(time_platform, "ha_gmt_offset", lambda hass: "GMT+01:00")

    schedule_switch = switch.DeepalChargeScheduleSwitch(coordinator, vehicle)
    await schedule_switch.async_turn_on()
    assert client.modified[-1][1] == "1"
    assert client.modified[-1][7] == "GMT+02:00"

    schedule_time = time_platform.DeepalChargeScheduleTime(
        coordinator, vehicle, "charge_schedule_start", "start"
    )
    assert schedule_time.extra_state_attributes == {"time_zone": "GMT+02:00"}
    await schedule_time.async_set_value(dt_time(2, 30))
    assert client.modified[-1][2] == "0230"
    assert client.modified[-1][7] == "GMT+02:00"
