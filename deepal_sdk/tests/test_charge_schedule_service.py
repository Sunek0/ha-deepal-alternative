"""Tests for the Deepal charge-schedule service."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.deepal import charge_schedule, services
from custom_components.deepal.deepal import (
    CommandResult,
    CommandResultStatus,
    DeepalAPIError,
    DeepalIntlClient,
    DeepalRateLimitError,
    VehicleCondition,
)
from custom_components.deepal.runtime_data import DeepalRuntimeData


class FakeClient(DeepalIntlClient):
    """Command double recording the model-aware service calls."""

    def __init__(self) -> None:
        self.deleted: list[tuple[str, str]] = []
        self.added: list[tuple] = []
        self.modified: list[tuple] = []
        self.toggled: list[tuple[str, str, bool]] = []
        self.fresh_condition = None
        # Conditions returned by successive get_vehicle_condition calls (the
        # last one repeats), to model a car that drops a plan after a delete.
        self.fresh_sequence: list = []
        self.modify_error: Exception | None = None
        self.validity_error: Exception | None = None
        self.delete_error: Exception | None = None
        self.add_error: Exception | None = None

    async def get_vehicle_condition(self, car_id, vin=None, *, model_code=None):
        if self.fresh_sequence:
            if len(self.fresh_sequence) > 1:
                return self.fresh_sequence.pop(0)
            return self.fresh_sequence[0]
        return self.fresh_condition

    async def control_charge_plan_delete(self, car_id: str, plan_id: str) -> str:
        self.deleted.append((car_id, plan_id))
        if self.delete_error is not None:
            raise self.delete_error
        return "delete-command"

    async def control_charge_plan_validity(
        self, car_id: str, plan_id: str, enabled: bool
    ) -> str:
        self.toggled.append((car_id, plan_id, enabled))
        if self.validity_error is not None:
            raise self.validity_error
        return "validity-command"

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
        if self.add_error is not None:
            raise self.add_error
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
        if self.modify_error is not None:
            raise self.modify_error
        return "modify-command"

    async def control_result_status(self, car_id: str, command_id: str):
        return CommandResult(status=CommandResultStatus.SUCCESS, code=0)


class FakeConfigEntry:
    """Records the background tasks the charge-schedule code starts."""

    def __init__(self) -> None:
        self.tasks: list[tuple[str, object]] = []

    def async_create_background_task(self, hass, target, name, eager_start=True):
        self.tasks.append((name, target))

    def __del__(self) -> None:
        # A task a test never ran must not warn about an un-awaited coroutine.
        for _, target in self.tasks:
            target.close()


class FakeCoordinator:
    def __init__(self, vehicle, condition) -> None:
        self.vehicles = [vehicle]
        self.data = {vehicle.car_id: condition}
        self.commands: list[str] = []
        self.execute_kwargs: list[dict] = []
        self.refreshes = 0
        self.hass = SimpleNamespace()
        self.config_entry = FakeConfigEntry()

    @property
    def background_names(self) -> list[str]:
        return [name for name, _ in self.config_entry.tasks]

    async def run_background(self) -> None:
        """Run the started background tasks in order, as the loop would."""
        tasks, self.config_entry.tasks = self.config_entry.tasks, []
        for _, target in tasks:
            await target

    def async_set_updated_data(self, data) -> None:
        self.data = data

    async def async_execute_command(self, car_id, send_command, **kwargs):
        self.commands.append(await send_command())
        self.execute_kwargs.append({"car_id": car_id, **kwargs})

    async def async_request_refresh(self) -> None:
        self.refreshes += 1


@pytest.fixture(autouse=True)
def _no_plan_delays(monkeypatch):
    """The verify/refresh waits are real seconds in production."""
    monkeypatch.setattr(charge_schedule, "_DELETE_SETTLE_SECONDS", 0)
    monkeypatch.setattr(charge_schedule, "_REFRESH_DELAYS", (0, 0))


PHEV = "SC6460AAAA7HEV"
OLD_PLAN = "2123847911387103234"
NEW_PLAN = "2123847911387103999"
ADDED_PLAN = "2123847911387109999"
PLACEHOLDER = {"planId": "1", "isValid": 0, "startTime": "0100", "endTime": "2300"}


def _real_plan(plan_id: str = OLD_PLAN, valid: int = 1) -> dict:
    return {
        "planId": plan_id,
        "isValid": valid,
        "startTime": "0100",
        "endTime": "0200",
        "timeZone": "GMT+02:00",
    }


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
async def test_phev_on_with_only_the_placeholder_adds_a_plan() -> None:
    client = FakeClient()
    hass, coordinator = _hass(
        _vehicle(PHEV), _condition([PLACEHOLDER]), client
    )

    response = await services._async_handle_set_charge_schedule(
        _call(hass, start_time="00:00", end_time="03:00", enabled=True)
    )

    assert response["strategy"] == "add-plan"
    assert client.added[0][1:4] == ("0000", "0300", 1)
    # The car rejects modify-plan and the validity command, so neither is sent.
    assert client.modified == []
    assert client.toggled == []
    assert coordinator.commands == ["add-command"]
    # The placeholder is not a plan to purge; only the refresh is scheduled.
    assert coordinator.background_names == ["deepal_refresh_after_plan"]
    await coordinator.run_background()
    assert client.deleted == []


@pytest.mark.asyncio
async def test_phev_on_removes_the_older_real_plans_after_adding() -> None:
    client = FakeClient()
    stacked = [_real_plan(NEW_PLAN), _real_plan(OLD_PLAN, valid=0), PLACEHOLDER]
    hass, coordinator = _hass(_vehicle(PHEV), _condition(stacked), client)
    with_added = _condition([_real_plan(ADDED_PLAN), *stacked])
    # The car applies the add late: the first look still shows the old list,
    # the second one lists the new plan, and after the deletes only it is left.
    client.fresh_sequence = [
        _condition(stacked),
        _condition(stacked),
        with_added,
        _condition([_real_plan(ADDED_PLAN), PLACEHOLDER]),
    ]

    response = await services._async_handle_set_charge_schedule(
        _call(hass, start_time="01:00", end_time="02:00", enabled=True)
    )

    assert response["strategy"] == "add-plan"
    assert len(client.added) == 1
    # The purge runs in the background, after the add, and never touches "1".
    assert client.deleted == []
    assert "deepal_purge_charge_plans" in coordinator.background_names
    await coordinator.run_background()
    # The new plan is never deleted, and neither is the placeholder.
    assert client.deleted == [("car-1", NEW_PLAN), ("car-1", OLD_PLAN)]
    # The purge must not publish "schedule off" while the new plan is on: only
    # the add (the first command) carries an optimistic update.
    assert coordinator.execute_kwargs[0]["optimistic_update"] is not None
    assert [k["optimistic_update"] for k in coordinator.execute_kwargs[1:]] == [
        None,
        None,
    ]
    assert client.modified == []
    assert client.toggled == []


@pytest.mark.asyncio
async def test_phev_purge_keeps_the_old_plans_until_the_new_one_is_listed(
    caplog,
) -> None:
    client = FakeClient()
    old_only = _condition([_real_plan(OLD_PLAN), PLACEHOLDER])
    hass, coordinator = _hass(_vehicle(PHEV), old_only, client)
    client.fresh_sequence = [old_only]  # the car never lists the new plan

    await services._async_handle_set_charge_schedule(
        _call(hass, start_time="0100", end_time="0200", enabled=True)
    )
    assert len(client.added) == 1
    with caplog.at_level("WARNING"):
        await coordinator.run_background()

    # Deleting now would leave the car with no plan at all.
    assert client.deleted == []
    assert "did not list the new charge plan" in caplog.text


@pytest.mark.asyncio
async def test_phev_off_deletes_the_real_plan_and_keeps_the_times() -> None:
    client = FakeClient()
    plans = [_real_plan(), PLACEHOLDER]
    condition = _condition(plans, plan_id=OLD_PLAN)
    hass, coordinator = _hass(_vehicle(PHEV), condition, client)
    client.fresh_sequence = [condition, _condition([PLACEHOLDER])]

    response = await services._async_handle_set_charge_schedule(
        _call(hass, start_time="0100", end_time="0200", enabled=False)
    )

    assert response["strategy"] == "delete-plan"
    assert client.deleted == [("car-1", OLD_PLAN)]
    assert client.toggled == []
    assert client.modified == []
    assert client.added == []
    assert coordinator.commands == ["delete-command"]
    # A delete must not write the times: the car reports none afterwards and
    # the coordinator would turn the last chosen ones into unknown.
    probe = _condition(plans)
    probe.battery.charge_schedule_start = "0415"
    probe.battery.charge_schedule_end = "0530"
    coordinator.execute_kwargs[0]["optimistic_update"](probe)
    assert probe.battery.charge_schedule_start == "0415"
    assert probe.battery.charge_schedule_end == "0530"
    assert probe.battery.charge_schedule_enabled is False


@pytest.mark.asyncio
async def test_phev_off_with_only_the_placeholder_sends_nothing() -> None:
    client = FakeClient()
    condition = _condition([PLACEHOLDER])
    hass, coordinator = _hass(_vehicle(PHEV), condition, client)

    response = await services._async_handle_set_charge_schedule(
        _call(hass, start_time="0300", end_time="0400", enabled=False)
    )

    assert response["strategy"] == "noop"
    assert coordinator.commands == []
    assert client.deleted == client.added == client.modified == client.toggled == []
    assert coordinator.background_names == []
    # The chosen times are kept for the next "on".
    battery = coordinator.data["car-1"].battery
    assert (battery.charge_schedule_start, battery.charge_schedule_end) == (
        "0300",
        "0400",
    )
    assert battery.charge_schedule_enabled is False


@pytest.mark.asyncio
async def test_phev_off_retries_a_delete_the_car_ignored() -> None:
    client = FakeClient()
    condition = _condition([_real_plan(), PLACEHOLDER])
    hass, coordinator = _hass(_vehicle(PHEV), condition, client)
    # The first verify still lists the plan, the second one does not.
    client.fresh_sequence = [condition, condition, _condition([PLACEHOLDER])]

    response = await services._async_handle_set_charge_schedule(
        _call(hass, start_time="0100", end_time="0200", enabled=False)
    )

    assert response["strategy"] == "delete-plan"
    assert client.deleted == [("car-1", OLD_PLAN), ("car-1", OLD_PLAN)]


@pytest.mark.asyncio
async def test_phev_off_gives_up_after_three_attempts(caplog) -> None:
    client = FakeClient()
    condition = _condition([_real_plan(), PLACEHOLDER])
    hass, _ = _hass(_vehicle(PHEV), condition, client)
    client.fresh_sequence = [condition]  # the car keeps listing the plan

    with caplog.at_level("WARNING"):
        response = await services._async_handle_set_charge_schedule(
            _call(hass, start_time="0100", end_time="0200", enabled=False)
        )

    assert response["strategy"] == "delete-plan"
    assert client.deleted == [("car-1", OLD_PLAN)] * 3
    assert "still lists" in caplog.text


@pytest.mark.asyncio
async def test_phev_off_raises_when_every_delete_fails() -> None:
    client = FakeClient()
    hass, coordinator = _hass(
        _vehicle(PHEV), _condition([_real_plan(), PLACEHOLDER]), client
    )
    client.delete_error = DeepalAPIError(
        "API Error: HW_1_1_01_001 Operation failed", code="HW_1_1_01_001"
    )

    with pytest.raises(HomeAssistantError) as excinfo:
        await services._async_handle_set_charge_schedule(
            _call(hass, start_time="0100", end_time="0200", enabled=False)
        )

    assert "Could not switch off" in str(excinfo.value)
    # Never fall back to add-plan: the car would turn the new plan on.
    assert client.added == []
    assert client.modified == []
    assert coordinator.background_names == []


@pytest.mark.asyncio
async def test_phev_add_rate_limit_is_reported_and_nothing_is_deleted() -> None:
    client = FakeClient()
    hass, coordinator = _hass(
        _vehicle(PHEV), _condition([_real_plan(), PLACEHOLDER]), client
    )
    client.add_error = DeepalRateLimitError(
        "Too many control-code attempts", code="HW_1_1_01_047"
    )

    with pytest.raises(HomeAssistantError):
        await services._async_handle_set_charge_schedule(
            _call(hass, start_time="0100", end_time="0200", enabled=True)
        )

    # The old plan stays until the new one exists.
    assert client.deleted == []
    assert coordinator.background_names == []


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [True, False])
async def test_phev_refresh_is_scheduled_after_an_add_and_a_delete(enabled) -> None:
    client = FakeClient()
    condition = _condition([_real_plan(), PLACEHOLDER])
    hass, coordinator = _hass(_vehicle(PHEV), condition, client)
    client.fresh_sequence = [condition, _condition([PLACEHOLDER])]

    await services._async_handle_set_charge_schedule(
        _call(hass, start_time="0100", end_time="0200", enabled=enabled)
    )

    assert "deepal_refresh_after_plan" in coordinator.background_names
    assert coordinator.refreshes == 0
    await coordinator.run_background()
    assert coordinator.refreshes == 2  # the two delayed refreshes


@pytest.mark.asyncio
async def test_phev_enabled_none_follows_the_newest_real_plan() -> None:
    client = FakeClient()
    vehicle = _vehicle(PHEV)
    hass, coordinator = _hass(
        vehicle, _condition([_real_plan(NEW_PLAN), PLACEHOLDER]), client
    )

    strategy, _ = await charge_schedule.async_set_charge_schedule(
        coordinator, vehicle, "0230", "0300", None, "GMT+02:00"
    )

    assert strategy == "add-plan"
    assert client.added[0][1:4] == ("0230", "0300", 1)

    # A list with only the placeholder means "no plan": a time edit is kept
    # locally instead of creating an active plan.
    client = FakeClient()
    hass, coordinator = _hass(vehicle, _condition([PLACEHOLDER]), client)
    strategy, _ = await charge_schedule.async_set_charge_schedule(
        coordinator, vehicle, "0230", "0300", None, "GMT+02:00"
    )
    assert strategy == "noop"
    assert client.added == []


@pytest.mark.parametrize("plan_id", ["1", 1])
def test_stale_plan_ids_never_include_the_placeholder(plan_id) -> None:
    plans = [{"planId": plan_id}, {"planId": OLD_PLAN}, {"planId": NEW_PLAN}, {}]

    assert charge_schedule._stale_plan_ids(plans, None) == [OLD_PLAN, NEW_PLAN]
    assert charge_schedule._stale_plan_ids(plans, NEW_PLAN) == [OLD_PLAN]


@pytest.mark.asyncio
async def test_phev_deletes_are_serialized_by_a_lock_on_the_coordinator() -> None:
    client = FakeClient()
    hass, coordinator = _hass(_vehicle(PHEV), _condition([PLACEHOLDER]), client)

    lock = charge_schedule._plan_lock(coordinator)

    assert charge_schedule._plan_lock(coordinator) is lock


def _switch(monkeypatch, coordinator, vehicle):
    from custom_components.deepal import switch

    monkeypatch.setattr(switch, "ha_gmt_offset", lambda hass: "GMT+02:00")
    return switch.DeepalChargeScheduleSwitch(coordinator, vehicle)


@pytest.mark.asyncio
async def test_phev_switch_on_adds_a_plan(monkeypatch) -> None:
    client = FakeClient()
    vehicle = _vehicle(PHEV)
    _, coordinator = _hass(vehicle, _condition([PLACEHOLDER]), client)

    await _switch(monkeypatch, coordinator, vehicle).async_turn_on()

    assert len(client.added) == 1
    assert client.added[0][3] == 1
    assert client.toggled == []
    assert client.modified == []


@pytest.mark.asyncio
async def test_phev_switch_off_deletes_the_real_plans(monkeypatch) -> None:
    client = FakeClient()
    vehicle = _vehicle(PHEV)
    condition = _condition([_real_plan(NEW_PLAN), _real_plan(OLD_PLAN), PLACEHOLDER])
    _, coordinator = _hass(vehicle, condition, client)
    client.fresh_sequence = [condition, _condition([PLACEHOLDER])]

    await _switch(monkeypatch, coordinator, vehicle).async_turn_off()

    assert client.deleted == [("car-1", NEW_PLAN), ("car-1", OLD_PLAN)]
    assert client.toggled == []
    assert client.modified == []
    assert client.added == []


@pytest.mark.asyncio
async def test_phev_switch_off_raises_when_the_delete_fails(monkeypatch) -> None:
    client = FakeClient()
    vehicle = _vehicle(PHEV)
    _, coordinator = _hass(vehicle, _condition([_real_plan(), PLACEHOLDER]), client)
    client.delete_error = DeepalRateLimitError(
        "Too many control-code attempts", code="HW_1_1_01_047"
    )

    with pytest.raises(HomeAssistantError) as excinfo:
        await _switch(monkeypatch, coordinator, vehicle).async_turn_off()

    assert "Could not switch off" in str(excinfo.value)
    assert client.added == []


# Other international models keep the 1.9.0-b4 behaviour: the PHEV plan rules
# (newest plan first, plan id "1" is a placeholder) are not known for them.
S07 = _vehicle("SC6501ABABEV", series_name="S07", series_code="C673-EU")


@pytest.mark.asyncio
async def test_other_model_switch_uses_the_plan_validity_command(monkeypatch) -> None:
    client = FakeClient()
    plans = [{"planId": 1, "isValid": 0, "startTime": "0000", "endTime": "0100"}]
    _, coordinator = _hass(S07, _condition(plans, plan_id="1"), client)

    await _switch(monkeypatch, coordinator, S07).async_turn_on()

    # Plan id "1" is a normal plan here, not the PHEV placeholder.
    assert client.toggled == [("car-1", "1", True)]
    assert client.added == []
    assert coordinator.background_names == []


@pytest.mark.asyncio
async def test_other_model_modify_rejection_falls_back_to_add_plan() -> None:
    client = FakeClient()
    plans = [{"planId": 7, "isValid": 0, "startTime": "0000", "endTime": "0100"}]
    _, coordinator = _hass(S07, _condition(plans, plan_id="7"), client)
    client.modify_error = DeepalAPIError(
        "API Error: HW_1_1_01_001 Operation failed", code="HW_1_1_01_001"
    )

    strategy, _ = await charge_schedule.async_set_charge_schedule(
        coordinator, S07, "0000", "0300", True, "GMT+02:00"
    )

    assert strategy == "add-plan"
    assert len(client.modified) == 1
    assert client.modified[0][1] == "7"
    assert client.added[0][1:4] == ("0000", "0300", 1)
    assert client.deleted == []
    assert coordinator.background_names == []


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
    condition = _condition([_real_plan(), PLACEHOLDER], plan_id=OLD_PLAN)
    condition.battery.charge_plan_time_zone = "GMT+02:00"
    vehicle = _vehicle(PHEV)
    hass, _ = _hass(vehicle, condition, client)

    response = await services._async_handle_set_charge_schedule(
        _call(hass, start_time="0000", end_time="0100", enabled=True)
    )

    assert response["time_zone"] == "GMT+02:00"
    assert client.added[-1][6] == "GMT+02:00"


@pytest.mark.asyncio
async def test_schedule_controls_use_the_plan_timezone(monkeypatch) -> None:
    from datetime import time as dt_time

    from custom_components.deepal import switch, time as time_platform

    client = FakeClient()
    condition = _condition([_real_plan(), PLACEHOLDER], plan_id=OLD_PLAN)
    condition.battery.charge_plan_time_zone = "GMT+02:00"
    condition.battery.charge_schedule_enabled = True
    vehicle = _vehicle(PHEV)
    hass, coordinator = _hass(vehicle, condition, client)
    monkeypatch.setattr(switch, "ha_gmt_offset", lambda hass: "GMT+01:00")
    monkeypatch.setattr(time_platform, "ha_gmt_offset", lambda hass: "GMT+01:00")

    schedule_switch = switch.DeepalChargeScheduleSwitch(coordinator, vehicle)
    await schedule_switch.async_turn_on()
    assert client.added[-1][6] == "GMT+02:00"

    schedule_time = time_platform.DeepalChargeScheduleTime(
        coordinator, vehicle, "charge_schedule_start", "start"
    )
    assert schedule_time.extra_state_attributes == {"time_zone": "GMT+02:00"}
    await schedule_time.async_set_value(dt_time(2, 30))
    # A time edit keeps the plan on (enabled=None) and writes it as a new plan.
    assert client.added[-1][1] == "0230"
    assert client.added[-1][6] == "GMT+02:00"
    assert client.modified == []
