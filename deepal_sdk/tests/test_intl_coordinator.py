"""Tests for the Home Assistant coordinator command flow."""

import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from homeassistant.exceptions import HomeAssistantError

from custom_components.deepal.const import (
    CONF_ACCESS_TOKEN,
    CONF_CAC_TOKEN,
    CONF_REFRESH_TOKEN,
)
from custom_components.deepal.coordinator import DeepalDataUpdateCoordinator
from custom_components.deepal.deepal import (
    AuthToken,
    ClimateCondition,
    CommandResult,
    CommandResultStatus,
    DeepalAPIError,
    DeepalAuthError,
    DeepalIntlClient,
    Vehicle,
    VehicleCapabilities,
    VehicleCondition,
)


class _FakeIntlClient(DeepalIntlClient):
    """Fake international client recording the command flow."""

    def __init__(self, results: list[CommandResult]) -> None:
        self.access_token = "test_token_123"
        self.refresh_token: str | None = "test_refresh_123"
        self.private_key_pem = "test_private_key"
        self.user_id = "user-1"
        self.results = list(results)
        self.events: list[str] = []
        self.condition_calls = 0
        self.condition_timestamps: list[int] | None = None
        self.condition_power_on: bool | None = None
        self.http_condition: VehicleCondition | None = None
        self.capabilities_calls = 0
        self.capabilities: VehicleCapabilities | None = None
        self.capabilities_error: Exception | None = None
        self.refresh_calls = 0

    async def refresh_tokens(self, force: bool = False) -> AuthToken:
        self.refresh_calls += 1
        self.access_token = f"refreshed_token_{self.refresh_calls}"
        return AuthToken(
            access_token=self.access_token,
            refresh_token=self.refresh_token,
        )

    async def control_condition_inquiry(self, vehicle_id: str) -> str:
        self.events.append("condition_inquiry")
        return "cmd-inquiry"

    async def control_result_status(
        self, vehicle_id: str, command_id: str
    ) -> CommandResult:
        self.events.append("poll")
        return self.results.pop(0)

    async def get_vehicle_capabilities(
        self, vehicle_id: str, vin: str | None = None
    ) -> VehicleCapabilities | None:
        self.capabilities_calls += 1
        if self.capabilities_error is not None:
            raise self.capabilities_error
        return self.capabilities

    async def get_vehicle_condition(
        self, vehicle_id: str, vin: str | None = None
    ) -> VehicleCondition:
        self.events.append("condition")
        if self.http_condition is not None:
            return self.http_condition
        self.condition_calls += 1
        if self.condition_timestamps:
            timestamp = self.condition_timestamps.pop(0)
        else:
            timestamp = 1000 + self.condition_calls
        return VehicleCondition(
            car_id=vehicle_id,
            vin=vin or "",
            climate=ClimateCondition(power_on=self.condition_power_on),
            last_updated_timestamp=timestamp,
        )


def _coordinator(
    client: _FakeIntlClient,
    data: dict[str, VehicleCondition] | None = None,
) -> tuple[DeepalDataUpdateCoordinator, list[dict[str, VehicleCondition]]]:
    coordinator = object.__new__(DeepalDataUpdateCoordinator)
    coordinator.client = client
    coordinator.vehicles = []
    coordinator.data = data or {}
    coordinator._command_locks = {}
    coordinator._optimistic_holds = {}
    coordinator._background_tasks = set()
    coordinator.entry = SimpleNamespace(
        data={
            CONF_ACCESS_TOKEN: "test_token_123",
            CONF_REFRESH_TOKEN: "test_refresh_123",
            CONF_CAC_TOKEN: "",
        }
    )
    coordinator.hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_update_entry=lambda *args, **kwargs: None)
    )
    updates: list[dict[str, VehicleCondition]] = []

    def _set_updated_data(new_data: dict[str, VehicleCondition]) -> None:
        coordinator.data = new_data
        updates.append(new_data)

    coordinator.async_set_updated_data = _set_updated_data
    return coordinator, updates


@pytest.mark.asyncio
async def test_command_polls_until_terminal_success():
    client = _FakeIntlClient(
        [
            CommandResult(status=CommandResultStatus.PENDING, raw={"resultCode": -100}),
            CommandResult(
                status=CommandResultStatus.SUCCESS, code=0, raw={"resultCode": 0}
            ),
        ]
    )
    coordinator, updates = _coordinator(client)
    sent: list[str] = []

    async def send_command() -> str:
        sent.append("cmd-1")
        return "cmd-1"

    await coordinator.async_execute_command(
        "car-1",
        send_command,
        optimistic_update=lambda condition: condition,
        timeout=1.0,
        interval=0.01,
    )

    assert sent == ["cmd-1"]
    assert client.events.count("poll") == 2
    assert updates
    assert coordinator.data["car-1"].last_updated_timestamp is not None


@pytest.mark.asyncio
async def test_stateless_command_returns_on_acceptance_without_condition_fetch():
    client = _FakeIntlClient(
        [
            CommandResult(status=CommandResultStatus.PENDING, raw={"resultCode": -100}),
            CommandResult(
                status=CommandResultStatus.SUCCESS, code=0, raw={"resultCode": 0}
            ),
        ]
    )
    coordinator, updates = _coordinator(client)

    async def send_command() -> str:
        return "cmd-1"

    await coordinator.async_execute_command(
        "car-1", send_command, timeout=1.0, interval=0.01
    )

    assert client.events.count("poll") == 2
    assert client.events.count("condition_inquiry") == 0
    assert client.events.count("condition") == 0
    assert updates == []


@pytest.mark.asyncio
async def test_stateless_command_failure_raises():
    client = _FakeIntlClient(
        [
            CommandResult(
                status=CommandResultStatus.FAILED,
                code=-1,
                error_message="Operation failed. Network error.",
                raw={"resultCode": -1, "errorMsg": "Operation failed. Network error."},
            )
        ]
    )
    coordinator, _ = _coordinator(client)

    async def send_command() -> str:
        return "cmd-1"

    with pytest.raises(HomeAssistantError) as err:
        await coordinator.async_execute_command(
            "car-1", send_command, timeout=1.0, interval=0.01
        )

    assert "-1" in str(err.value)
    assert "Network error" in str(err.value)


@pytest.mark.asyncio
async def test_stateless_command_pending_returns_without_raising():
    client = _FakeIntlClient(
        [
            CommandResult(status=CommandResultStatus.PENDING, raw={"resultCode": -100})
            for _ in range(10)
        ]
    )
    coordinator, updates = _coordinator(client)

    async def send_command() -> str:
        return "cmd-1"

    await coordinator.async_execute_command(
        "car-1", send_command, timeout=0.05, interval=0.01
    )

    assert client.events.count("poll") >= 3
    assert updates == []


@pytest.mark.asyncio
async def test_optimistic_command_returns_at_the_confirmation_cap(monkeypatch):
    monkeypatch.setattr(
        "custom_components.deepal.coordinator._OPTIMISTIC_CONFIRM_TIMEOUT", 0.05
    )
    client = _FakeIntlClient(
        [
            CommandResult(status=CommandResultStatus.PENDING, raw={"resultCode": -100})
            for _ in range(10)
        ]
    )
    coordinator, _ = _coordinator(client, data={"car-1": _current_condition()})

    async def send_command() -> str:
        return "cmd-1"

    await coordinator.async_execute_command(
        "car-1",
        send_command,
        optimistic_update=_optimistic_power_on(),
        timeout=60.0,
        interval=0.01,
    )

    assert client.events.count("poll") >= 3
    assert coordinator.data["car-1"].climate.power_on is True


@pytest.mark.asyncio
async def test_command_polls_until_failure_raises():
    client = _FakeIntlClient(
        [
            CommandResult(status=CommandResultStatus.PENDING, raw={"resultCode": -100}),
            CommandResult(
                status=CommandResultStatus.FAILED,
                code=-2,
                error_message="gateway rejected",
                raw={"resultCode": -2, "errorMsg": "gateway rejected"},
            ),
        ]
    )
    coordinator, _ = _coordinator(client)

    async def send_command() -> str:
        return "cmd-1"

    with pytest.raises(HomeAssistantError) as err:
        await coordinator.async_execute_command(
            "car-1", send_command, timeout=1.0, interval=0.01
        )

    assert "-2" in str(err.value)
    assert "gateway rejected" in str(err.value)
    assert client.events.count("poll") == 2


@pytest.mark.asyncio
async def test_command_applies_optimistic_update_before_first_poll():
    client = _FakeIntlClient(
        [CommandResult(status=CommandResultStatus.SUCCESS, code=0, raw={})]
    )
    current = VehicleCondition(car_id="car-1", vin="VIN123")
    coordinator, updates = _coordinator(client, data={"car-1": current})
    events = client.events

    async def send_command() -> str:
        events.append("send")
        return "cmd-1"

    def optimistic_update(condition: VehicleCondition) -> VehicleCondition:
        events.append("optimistic")
        condition.engine_on = True
        return condition

    await coordinator.async_execute_command(
        "car-1",
        send_command,
        optimistic_update=optimistic_update,
        timeout=1.0,
        interval=0.01,
    )

    assert events.index("send") < events.index("optimistic")
    assert events.index("optimistic") < events.index("poll")
    assert updates[0]["car-1"].engine_on is True


@pytest.mark.asyncio
async def test_unknown_result_code_raises_with_code_and_message():
    client = _FakeIntlClient(
        [
            CommandResult(
                status=CommandResultStatus.FAILED,
                code=9999,
                error_message="unknown failure",
                raw={"resultCode": 9999, "errorMsg": "unknown failure"},
            )
        ]
    )
    coordinator, _ = _coordinator(client)

    async def send_command() -> str:
        return "cmd-1"

    with pytest.raises(HomeAssistantError) as err:
        await coordinator.async_execute_command(
            "car-1", send_command, timeout=1.0, interval=0.01
        )

    assert "9999" in str(err.value)
    assert "unknown failure" in str(err.value)


@pytest.mark.asyncio
async def test_already_done_stops_when_state_callback_matches():
    client = _FakeIntlClient(
        [
            CommandResult(
                status=CommandResultStatus.ALREADY_DONE,
                code=1015,
                raw={"resultCode": 1015},
            )
        ]
    )
    coordinator, _ = _coordinator(client)

    async def send_command() -> str:
        return "cmd-1"

    await coordinator.async_execute_command(
        "car-1",
        send_command,
        is_done=lambda: True,
        timeout=1.0,
        interval=0.01,
    )

    assert client.events.count("poll") == 1


@pytest.mark.asyncio
async def test_pending_command_times_out_without_raising():
    client = _FakeIntlClient(
        [
            CommandResult(status=CommandResultStatus.PENDING, raw={"resultCode": -100})
            for _ in range(10)
        ]
    )
    coordinator, _ = _coordinator(client)

    async def send_command() -> str:
        return "cmd-1"

    await coordinator.async_execute_command(
        "car-1", send_command, timeout=0.05, interval=0.01
    )

    assert client.events.count("poll") >= 3


def _optimistic_power_on():
    def optimistic(condition: VehicleCondition) -> VehicleCondition:
        condition.climate.power_on = True
        return condition

    return optimistic


def _current_condition(car_id: str = "car-1", timestamp: int = 1000) -> VehicleCondition:
    return VehicleCondition(
        car_id=car_id,
        vin="",
        climate=ClimateCondition(power_on=False),
        last_updated_timestamp=timestamp,
    )


def _success_result() -> CommandResult:
    return CommandResult(status=CommandResultStatus.SUCCESS, code=0, raw={"resultCode": 0})


@pytest.mark.asyncio
async def test_state_sharing_commands_queue_per_vehicle():
    client = _FakeIntlClient([_success_result(), _success_result()])
    coordinator, _ = _coordinator(client, data={"car-1": _current_condition()})
    release = asyncio.Event()
    first_sent = asyncio.Event()
    order: list[str] = []

    async def first_command() -> str:
        order.append("first-start")
        first_sent.set()
        await release.wait()
        order.append("first-end")
        return "cmd-1"

    async def second_command() -> str:
        order.append("second")
        return "cmd-2"

    first = asyncio.create_task(
        coordinator.async_execute_command(
            "car-1",
            first_command,
            optimistic_update=_optimistic_power_on(),
            timeout=1.0,
            interval=0.01,
        )
    )
    await first_sent.wait()
    second = asyncio.create_task(
        coordinator.async_execute_command(
            "car-1",
            second_command,
            optimistic_update=_optimistic_power_on(),
            timeout=1.0,
            interval=0.01,
        )
    )
    await asyncio.sleep(0.01)

    assert order == ["first-start"]

    release.set()
    await asyncio.gather(first, second)

    assert order == ["first-start", "first-end", "second"]


@pytest.mark.asyncio
async def test_stateless_command_bypasses_the_queue():
    client = _FakeIntlClient([_success_result(), _success_result()])
    coordinator, _ = _coordinator(client, data={"car-1": _current_condition()})
    release = asyncio.Event()
    first_sent = asyncio.Event()
    order: list[str] = []

    async def first_command() -> str:
        order.append("first-start")
        first_sent.set()
        await release.wait()
        return "cmd-1"

    async def stateless_command() -> str:
        order.append("stateless")
        return "cmd-2"

    first = asyncio.create_task(
        coordinator.async_execute_command(
            "car-1",
            first_command,
            optimistic_update=_optimistic_power_on(),
            timeout=1.0,
            interval=0.01,
        )
    )
    await first_sent.wait()

    await coordinator.async_execute_command(
        "car-1", stateless_command, timeout=1.0, interval=0.01
    )

    assert order == ["first-start", "stateless"]

    release.set()
    await first


@pytest.mark.asyncio
async def test_command_lock_timeout_raises_without_sending(monkeypatch):
    monkeypatch.setattr(
        "custom_components.deepal.coordinator._COMMAND_LOCK_TIMEOUT", 0.05
    )
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client, data={"car-1": _current_condition()})
    lock = coordinator._vehicle_command_lock("car-1")
    await lock.acquire()
    sent: list[str] = []

    async def send_command() -> str:
        sent.append("cmd-1")
        return "cmd-1"

    try:
        with pytest.raises(HomeAssistantError):
            await coordinator.async_execute_command(
                "car-1", send_command, optimistic_update=_optimistic_power_on()
            )
    finally:
        lock.release()

    assert sent == []


@pytest.mark.asyncio
async def test_commands_for_different_vehicles_are_independent():
    client = _FakeIntlClient([_success_result(), _success_result()])
    coordinator, _ = _coordinator(
        client,
        data={
            "car-1": _current_condition("car-1"),
            "car-2": _current_condition("car-2"),
        },
    )
    release = asyncio.Event()
    first_sent = asyncio.Event()

    async def first_command() -> str:
        first_sent.set()
        await release.wait()
        return "cmd-1"

    async def second_command() -> str:
        return "cmd-2"

    first = asyncio.create_task(
        coordinator.async_execute_command(
            "car-1",
            first_command,
            optimistic_update=_optimistic_power_on(),
            timeout=1.0,
            interval=0.01,
        )
    )
    await first_sent.wait()

    await coordinator.async_execute_command(
        "car-2",
        second_command,
        optimistic_update=_optimistic_power_on(),
        timeout=1.0,
        interval=0.01,
    )

    release.set()
    await first


@pytest.mark.asyncio
async def test_command_send_recovers_from_expired_session():
    client = _FakeIntlClient([_success_result()])
    coordinator, _ = _coordinator(client, data={"car-1": _current_condition()})
    attempts = {"count": 0}

    async def send_command() -> str:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise DeepalAuthError(
                "Authentication failed: APP_1_1_02_004 Operation failed"
            )
        return "cmd-1"

    await coordinator.async_execute_command(
        "car-1",
        send_command,
        optimistic_update=_optimistic_power_on(),
        timeout=1.0,
        interval=0.01,
    )

    assert attempts["count"] == 2
    assert client.refresh_calls == 1


@pytest.mark.asyncio
async def test_result_poll_recovers_from_expired_session():
    client = _FakeIntlClient([_success_result()])
    coordinator, _ = _coordinator(client, data={"car-1": _current_condition()})
    original = client.control_result_status
    attempts = {"count": 0}

    async def flaky_result(vehicle_id: str, command_id: str) -> CommandResult:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise DeepalAuthError("Authentication failed: APP_1_1_02_004")
        return await original(vehicle_id, command_id)

    client.control_result_status = flaky_result

    async def send_command() -> str:
        return "cmd-1"

    await coordinator.async_execute_command(
        "car-1",
        send_command,
        optimistic_update=_optimistic_power_on(),
        timeout=1.0,
        interval=0.01,
    )

    assert attempts["count"] == 2
    assert client.refresh_calls == 1


@pytest.mark.asyncio
async def test_condition_inquiry_recovers_from_expired_session():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    attempts = {"count": 0}

    async def flaky_inquiry(vehicle_id: str) -> str:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise DeepalAuthError("Authentication failed: APP_1_1_02_004")
        return "cmd-inquiry"

    client.control_condition_inquiry = flaky_inquiry

    await coordinator.async_condition_inquiry("car-1")

    assert attempts["count"] == 2
    assert client.refresh_calls == 1


@pytest.mark.asyncio
async def test_condition_inquiry_does_not_delay_command():
    client = _FakeIntlClient([_success_result()])
    coordinator, _ = _coordinator(client, data={"car-1": _current_condition()})
    release = asyncio.Event()
    started = asyncio.Event()

    async def slow_inquiry(vehicle_id: str) -> str:
        client.events.append("condition_inquiry")
        started.set()
        await release.wait()
        return "cmd-inquiry"

    client.control_condition_inquiry = slow_inquiry

    async def send_command() -> str:
        return "cmd-1"

    await coordinator.async_execute_command(
        "car-1",
        send_command,
        optimistic_update=_optimistic_power_on(),
        timeout=1.0,
        interval=0.01,
    )

    await started.wait()

    assert not release.is_set()
    assert coordinator.data["car-1"].climate.power_on is True

    release.set()
    await asyncio.gather(*coordinator._background_tasks)


@pytest.mark.asyncio
async def test_session_recovery_without_refresh_token_raises():
    client = _FakeIntlClient([])
    client.refresh_token = None
    coordinator, _ = _coordinator(client)

    async def send_command() -> str:
        raise DeepalAuthError("Authentication failed: APP_1_1_02_004")

    with pytest.raises(DeepalAuthError):
        await coordinator.async_execute_command("car-1", send_command)

    assert client.refresh_calls == 0


@pytest.mark.asyncio
async def test_stale_condition_does_not_overwrite_optimistic_state():
    client = _FakeIntlClient(
        [
            CommandResult(status=CommandResultStatus.SUCCESS, code=0, raw={"resultCode": 0}),
            CommandResult(status=CommandResultStatus.SUCCESS, code=0, raw={"resultCode": 0}),
            CommandResult(status=CommandResultStatus.SUCCESS, code=0, raw={"resultCode": 0}),
        ]
    )
    client.condition_timestamps = [1000, 1000, 1001]
    client.condition_power_on = False
    optimistic = VehicleCondition(
        car_id="car-1",
        vin="",
        climate=ClimateCondition(power_on=True),
        last_updated_timestamp=1000,
    )
    coordinator, updates = _coordinator(client, {"car-1": optimistic})

    await coordinator._async_poll_command(
        "car-1",
        "cmd-1",
        1000,
        timeout=1.0,
        interval=0.01,
        is_done=lambda: coordinator.data["car-1"].climate.power_on is False,
        condition_interval=0.0,
    )

    assert len(updates) == 1
    assert updates[0]["car-1"].climate.power_on is False
    assert updates[0]["car-1"].last_updated_timestamp == 1001


@pytest.mark.asyncio
async def test_optimistic_command_returns_on_success_without_telemetry():
    client = _FakeIntlClient(
        [
            CommandResult(
                status=CommandResultStatus.SUCCESS, code=0, raw={"resultCode": 0}
            ),
        ]
    )
    client.condition_timestamps = [1000]
    current = VehicleCondition(
        car_id="car-1",
        vin="",
        climate=ClimateCondition(power_on=False),
        last_updated_timestamp=1000,
    )
    coordinator, updates = _coordinator(client, data={"car-1": current})

    async def send_command() -> str:
        return "cmd-1"

    def optimistic(condition: VehicleCondition) -> VehicleCondition:
        condition.climate.power_on = True
        return condition

    await coordinator.async_execute_command(
        "car-1",
        send_command,
        optimistic_update=optimistic,
        timeout=1.0,
        interval=0.01,
    )

    assert client.events.count("poll") == 1
    assert updates[0]["car-1"].climate.power_on is True


@pytest.mark.asyncio
async def test_failed_command_restores_optimistic_state():
    client = _FakeIntlClient(
        [
            CommandResult(
                status=CommandResultStatus.FAILED,
                code=2001,
                error_message="Operation failed\nError code:TBOX_2001",
                raw={"resultCode": 2001},
            ),
        ]
    )
    client.condition_timestamps = [1000]
    current = VehicleCondition(
        car_id="car-1",
        vin="",
        climate=ClimateCondition(power_on=False),
        last_updated_timestamp=1000,
    )
    coordinator, updates = _coordinator(client, data={"car-1": current})

    async def send_command() -> str:
        return "cmd-1"

    def optimistic(condition: VehicleCondition) -> VehicleCondition:
        condition.climate.power_on = True
        return condition

    with pytest.raises(HomeAssistantError) as err:
        await coordinator.async_execute_command(
            "car-1",
            send_command,
            optimistic_update=optimistic,
            timeout=1.0,
            interval=0.01,
        )

    assert "TBOX_2001" in str(err.value)
    assert "offline or busy" in str(err.value)
    assert updates[0]["car-1"].climate.power_on is True
    assert coordinator.data["car-1"].climate.power_on is False


@pytest.mark.asyncio
async def test_optimistic_hold_keeps_value_until_confirmed():
    client = _FakeIntlClient([])
    current = VehicleCondition(car_id="car-1", vin="")
    coordinator, _ = _coordinator(client, data={"car-1": current})

    before = current.model_dump()
    after = current.model_copy(deep=True)
    after.seats.front_left.ventilation_level = 2
    coordinator._register_optimistic_hold("car-1", before, after.model_dump())

    stale = VehicleCondition(car_id="car-1", vin="", last_updated_timestamp=2000)
    applied = coordinator._apply_optimistic_hold("car-1", stale)
    assert applied.seats.front_left.ventilation_level == 2

    confirmed = VehicleCondition(car_id="car-1", vin="", last_updated_timestamp=2001)
    confirmed.seats.front_left.ventilation_level = 2
    applied = coordinator._apply_optimistic_hold("car-1", confirmed)
    assert applied.seats.front_left.ventilation_level == 2
    assert "car-1" not in coordinator._optimistic_holds


@pytest.mark.asyncio
async def test_optimistic_hold_expires():
    client = _FakeIntlClient([])
    current = VehicleCondition(car_id="car-1", vin="")
    coordinator, _ = _coordinator(client, data={"car-1": current})

    before = current.model_dump()
    after = current.model_copy(deep=True)
    after.climate.power_on = True
    coordinator._register_optimistic_hold("car-1", before, after.model_dump())
    coordinator._optimistic_holds["car-1"]["expires"] = 0

    fetched = VehicleCondition(car_id="car-1", vin="", last_updated_timestamp=3000)
    applied = coordinator._apply_optimistic_hold("car-1", fetched)
    assert applied.climate.power_on is None
    assert "car-1" not in coordinator._optimistic_holds


@pytest.mark.asyncio
async def test_optimistic_hold_survives_precommand_report():
    client = _FakeIntlClient(
        [
            CommandResult(
                status=CommandResultStatus.SUCCESS, code=0, raw={"resultCode": 0}
            )
        ]
    )
    client.condition_timestamps = [2000]
    client.condition_power_on = False
    current = VehicleCondition(
        car_id="car-1",
        vin="",
        climate=ClimateCondition(power_on=False),
        last_updated_timestamp=1000,
    )
    coordinator, _ = _coordinator(client, data={"car-1": current})

    async def send_command() -> str:
        return "cmd-1"

    def optimistic(condition: VehicleCondition) -> VehicleCondition:
        condition.climate.power_on = True
        return condition

    await coordinator.async_execute_command(
        "car-1",
        send_command,
        optimistic_update=optimistic,
        timeout=1.0,
        interval=0.01,
    )

    assert coordinator.data["car-1"].climate.power_on is True

    confirmed = VehicleCondition(
        car_id="car-1",
        vin="",
        climate=ClimateCondition(power_on=True),
        last_updated_timestamp=2001,
    )
    client.http_condition = confirmed
    fetched = await coordinator._async_fetch_condition("car-1")
    applied = coordinator._apply_optimistic_hold("car-1", fetched)
    assert applied.climate.power_on is True
    assert "car-1" not in coordinator._optimistic_holds


@pytest.mark.asyncio
async def test_app_comfort_overlay_uses_server_condition():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    vehicle = Vehicle(car_id="car-1", vin="VIN", protocol_type="MQTT")
    coordinator.vehicles = [vehicle]

    app_condition = VehicleCondition(car_id="car-1", vin="VIN")
    app_condition.seats.front_left.ventilation_level = 2
    app_condition.climate.steering_wheel_heater_on = True
    app_condition.climate.steering_wheel_heater_level = 1
    app_condition.raw_data = {
        "seat": {"leftFront": {"ventStatus": 2}},
        "vehicleStatus": {"steeringWheelHeater": 1},
    }
    client.http_condition = app_condition

    mqtt_condition = VehicleCondition(car_id="car-1", vin="VIN")
    mqtt_condition.seats.front_left.ventilation_level = 6
    mqtt_condition.climate.steering_wheel_heater_on = True

    merged = await coordinator._overlay_app_comfort(vehicle, mqtt_condition)
    assert merged.seats.front_left.ventilation_level == 2
    assert merged.climate.steering_wheel_heater_on is True

    client.http_condition = VehicleCondition(car_id="car-1", vin="VIN")
    plain = VehicleCondition(car_id="car-1", vin="VIN")
    plain.seats.front_left.ventilation_level = 6
    merged = await coordinator._overlay_app_comfort(vehicle, plain)
    assert merged.seats.front_left.ventilation_level == 6


@pytest.mark.asyncio
async def test_capabilities_fetched_once_per_vehicle_and_cached():
    client = _FakeIntlClient([])
    client.capabilities = VehicleCapabilities.from_codes(
        ["#driverSeatVent", "#passengerSeatVent"]
    )
    coordinator, _ = _coordinator(client)
    coordinator._capabilities = {}
    vehicle = Vehicle(car_id="car-1", vin="VIN")

    await coordinator._async_maybe_fetch_capabilities(vehicle)
    await coordinator._async_maybe_fetch_capabilities(vehicle)

    assert client.capabilities_calls == 1
    capabilities = coordinator.vehicle_capabilities("car-1")
    assert capabilities is not None
    assert capabilities.trim_hint == "max"


@pytest.mark.asyncio
async def test_capabilities_failure_is_cached_without_raising():
    client = _FakeIntlClient([])
    client.capabilities_error = DeepalAPIError("capabilities endpoint down")
    coordinator, _ = _coordinator(client)
    coordinator._capabilities = {}
    vehicle = Vehicle(car_id="car-1", vin="VIN")

    await coordinator._async_maybe_fetch_capabilities(vehicle)
    await coordinator._async_maybe_fetch_capabilities(vehicle)

    assert client.capabilities_calls == 1
    assert coordinator.vehicle_capabilities("car-1") is None
