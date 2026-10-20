"""Tests for the Home Assistant coordinator command flow."""

import asyncio
import math
import time
from datetime import timedelta
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.deepal.charging import ChargingSessionManager
from custom_components.deepal.const import (
    CONF_ACCESS_TOKEN,
    CONF_CAC_TOKEN,
    CONF_REFRESH_TOKEN,
)
from custom_components.deepal.coordinator import DeepalDataUpdateCoordinator, WakeResult
from custom_components.deepal.deepal import (
    AuthToken,
    ClimateCondition,
    CommandResult,
    CommandResultStatus,
    DeepalAPIError,
    DeepalAuthError,
    DeepalConnectionError,
    DeepalIntlClient,
    DeepalRateLimitError,
    Vehicle,
    VehicleCapabilities,
    VehicleCondition,
)


class _FakeIntlClient(DeepalIntlClient):
    """Fake international client recording the command flow."""

    def __init__(self, results: list[CommandResult]) -> None:
        self.access_token = "test_token_123"
        self.access_token_expires_at: int | None = None
        self.refresh_token: str | None = "test_refresh_123"
        self.private_key_pem = "test_private_key"
        self.user_id = "user-1"
        self.results = list(results)
        self.events: list[str] = []
        self.condition_calls = 0
        self.condition_timestamps: list[int] | None = None
        self.condition_power_on: bool | None = None
        self.condition_error: Exception | None = None
        self.http_condition: VehicleCondition | None = None
        self.capabilities_calls = 0
        self.capabilities: VehicleCapabilities | None = None
        self.capabilities_error: Exception | None = None
        self.refresh_calls = 0
        self.wake_calls = 0
        self.wake_error: Exception | None = None
        self.wake_errors: list[Exception] = []
        self.mqtt_condition: VehicleCondition | None = None
        self.mqtt_condition_errors: list[Exception] = []
        self.mqtt_sda_flags: list[bool] = []
        self.sda_rest_condition: VehicleCondition | None = None
        self.sda_rest_calls = 0

    async def wake_vehicle(self, vehicle_id: str) -> None:
        self.events.append("wake")
        self.wake_calls += 1
        if self.wake_errors:
            raise self.wake_errors.pop(0)
        if self.wake_error is not None:
            error = self.wake_error
            self.wake_error = None
            raise error

    async def s05_mqtt_condition(
        self, vehicle_id: str, vin: str | None = None, *, sda: bool = False
    ) -> VehicleCondition:
        self.mqtt_sda_flags.append(sda)
        self.events.append("mqtt_condition")
        if self.mqtt_condition_errors:
            raise self.mqtt_condition_errors.pop(0)
        if self.mqtt_condition is not None:
            return self.mqtt_condition
        return await self.get_vehicle_condition(vehicle_id, vin=vin)

    async def s05_wait_for_report(
        self,
        vehicle_id: str,
        *,
        previous_timestamp: int | None = None,
        interval: float = 5.0,
        timeout: float = 60.0,
        vin: str | None = None,
    ) -> VehicleCondition | None:
        self.events.append("mqtt_wait")
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            condition = await self.get_vehicle_condition(vehicle_id, vin=vin)
            timestamp = condition.last_updated_timestamp
            if previous_timestamp is None or (
                timestamp is not None and timestamp > previous_timestamp
            ):
                return condition
            remaining = deadline - loop.time()
            if remaining <= 0:
                return None
            await asyncio.sleep(min(interval, remaining))

    async def get_sda_vehicle_condition(
        self, vehicle_id: str, vin: str | None = None
    ) -> VehicleCondition:
        self.sda_rest_calls += 1
        if self.sda_rest_condition is None:
            raise DeepalAPIError("SDA REST condition unavailable")
        return self.sda_rest_condition

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
        if self.condition_error is not None:
            raise self.condition_error
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
    coordinator._last_vehicle_refresh = time.monotonic()
    coordinator.data = data or {}
    coordinator.update_interval = timedelta(seconds=120)
    coordinator._command_locks = {}
    coordinator._command_cooldowns = {}
    coordinator._optimistic_holds = {}
    coordinator._optimistic_pending = {}
    coordinator._last_steering_wheel = {}
    coordinator._background_tasks = []
    coordinator._last_wake_at = {}
    coordinator._last_wake_result = {}
    coordinator._wake_locks = {}
    coordinator.wake_enabled = True
    coordinator._wake_poll_interval = 0.01
    coordinator._wake_report_timeout = 0.1
    coordinator._mqtt_attempts = {}
    coordinator.charging = None
    coordinator._charging_read_task = None
    coordinator._charging_read_stop = None
    coordinator._charging_read_interval = 600.0
    def _create_background_task(hass, target, name, eager_start=True):
        task = asyncio.create_task(target)
        coordinator._background_tasks.append(task)
        return task

    coordinator.entry = SimpleNamespace(
        data={
            CONF_ACCESS_TOKEN: "test_token_123",
            CONF_REFRESH_TOKEN: "test_refresh_123",
            CONF_CAC_TOKEN: "",
        },
        async_create_background_task=_create_background_task,
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


def _expire_optimistic_holds(
    coordinator: DeepalDataUpdateCoordinator, vehicle_id: str = "car-1"
) -> None:
    """Close the window of every optimistic hold of one vehicle."""
    for entry in coordinator._optimistic_holds[vehicle_id].values():
        entry.expires = 0


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
    assert err.value.translation_domain == "deepal"
    assert err.value.translation_key == "command_result_failed_unreachable"
    assert err.value.translation_placeholders["code"] == "2001"
    assert updates[0]["car-1"].climate.power_on is True
    assert coordinator.data["car-1"].climate.power_on is False


@pytest.mark.asyncio
async def test_power_on_command_failure_is_actionable():
    client = _FakeIntlClient(
        [
            CommandResult(
                status=CommandResultStatus.FAILED,
                code=1032,
                error_message="Operation failed\nError code:1032",
                raw={"resultCode": 1032},
            ),
        ]
    )
    coordinator, _ = _coordinator(client)

    async def send_command() -> str:
        return "cmd-1"

    with pytest.raises(HomeAssistantError) as err:
        await coordinator.async_execute_command(
            "car-1",
            send_command,
            timeout=1.0,
            interval=0.01,
        )

    assert "1032" in str(err.value)
    assert "powered off" in str(err.value)
    assert err.value.translation_key == "command_result_failed_power_off"
    assert err.value.translation_placeholders["code"] == "1032"


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
async def test_optimistic_seat_hold_survives_unrelated_command():
    client = _FakeIntlClient([])
    current = VehicleCondition(car_id="car-1", vin="")
    current.seats.front_left.ventilation_level = 2
    coordinator, _ = _coordinator(client, data={"car-1": current})

    before = current.model_dump()
    seat_off = current.model_copy(deep=True)
    seat_off.seats.front_left.ventilation_level = 0
    coordinator._register_optimistic_hold("car-1", before, seat_off.model_dump())
    coordinator.async_set_updated_data({"car-1": seat_off})
    seat_path = "seats.front_left.ventilation_level"
    seat_expiry = coordinator._optimistic_holds["car-1"][seat_path].expires

    before = seat_off.model_dump()
    climate_off = seat_off.model_copy(deep=True)
    climate_off.climate.power_on = False
    coordinator._register_optimistic_hold(
        "car-1", before, climate_off.model_dump()
    )
    coordinator.async_set_updated_data({"car-1": climate_off})

    assert coordinator._optimistic_holds["car-1"][seat_path].expires == seat_expiry

    fetched = VehicleCondition(car_id="car-1", vin="", last_updated_timestamp=2000)
    merged = coordinator._merge_condition("car-1", fetched)
    applied = coordinator._apply_optimistic_hold("car-1", merged)

    assert applied.seats.front_left.ventilation_level == 0
    assert applied.climate.power_on is False


@pytest.mark.asyncio
async def test_optimistic_hold_same_field_refreshes_value_and_expiry():
    client = _FakeIntlClient([])
    current = VehicleCondition(car_id="car-1", vin="")
    current.seats.front_left.ventilation_level = 0
    coordinator, _ = _coordinator(client, data={"car-1": current})

    path = "seats.front_left.ventilation_level"
    before = current.model_dump()
    level_two = current.model_copy(deep=True)
    level_two.seats.front_left.ventilation_level = 2
    coordinator._register_optimistic_hold("car-1", before, level_two.model_dump())
    first_expiry = coordinator._optimistic_holds["car-1"][path].expires

    await asyncio.sleep(0.01)

    before = level_two.model_dump()
    level_three = level_two.model_copy(deep=True)
    level_three.seats.front_left.ventilation_level = 3
    coordinator._register_optimistic_hold(
        "car-1", before, level_three.model_dump()
    )

    entry = coordinator._optimistic_holds["car-1"][path]
    assert entry.value == 3
    assert entry.expires > first_expiry


@pytest.mark.asyncio
async def test_optimistic_holds_expire_independently():
    client = _FakeIntlClient([])
    current = VehicleCondition(car_id="car-1", vin="")
    current.seats.front_left.ventilation_level = 2
    coordinator, _ = _coordinator(client, data={"car-1": current})

    seat_path = "seats.front_left.ventilation_level"
    before = current.model_dump()
    seat_off = current.model_copy(deep=True)
    seat_off.seats.front_left.ventilation_level = 0
    coordinator._register_optimistic_hold("car-1", before, seat_off.model_dump())
    coordinator.async_set_updated_data({"car-1": seat_off})
    coordinator._optimistic_holds["car-1"][seat_path].expires = 0

    before = seat_off.model_dump()
    climate_off = seat_off.model_copy(deep=True)
    climate_off.climate.power_on = False
    coordinator._register_optimistic_hold(
        "car-1", before, climate_off.model_dump()
    )
    coordinator.async_set_updated_data({"car-1": climate_off})

    fetched = VehicleCondition(car_id="car-1", vin="", last_updated_timestamp=2000)
    merged = coordinator._merge_condition("car-1", fetched)
    applied = coordinator._apply_optimistic_hold("car-1", merged)

    assert applied.seats.front_left.ventilation_level is None
    assert applied.climate.power_on is False
    assert seat_path in coordinator._optimistic_pending["car-1"]


@pytest.mark.asyncio
async def test_optimistic_hold_expires():
    client = _FakeIntlClient([])
    current = VehicleCondition(car_id="car-1", vin="")
    coordinator, _ = _coordinator(client, data={"car-1": current})

    before = current.model_dump()
    after = current.model_copy(deep=True)
    after.climate.power_on = True
    coordinator._register_optimistic_hold("car-1", before, after.model_dump())
    _expire_optimistic_holds(coordinator)

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
    mqtt_condition.seats.front_left.ventilation_level = None
    mqtt_condition.seats.front_right.ventilation_level = 3
    mqtt_condition.climate.steering_wheel_heater_on = True

    merged = await coordinator._overlay_app_comfort(vehicle, mqtt_condition)
    assert merged.seats.front_left.ventilation_level == 2
    assert merged.seats.front_right.ventilation_level == 3
    assert merged.climate.steering_wheel_heater_on is True

    client.http_condition = VehicleCondition(car_id="car-1", vin="VIN")
    plain = VehicleCondition(car_id="car-1", vin="VIN")
    plain.seats.front_left.ventilation_level = None
    merged = await coordinator._overlay_app_comfort(vehicle, plain)
    assert merged.seats.front_left.ventilation_level is None


@pytest.mark.asyncio
async def test_app_comfort_overlay_prioritizes_rest_and_remembers_steering():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    vehicle = Vehicle(car_id="car-1", vin="VIN", protocol_type="MQTT")
    coordinator.vehicles = [vehicle]

    app_condition = VehicleCondition(car_id="car-1", vin="VIN")
    app_condition.climate.steering_wheel_heater_on = False
    app_condition.raw_data = {"vehicleStatus": {"steeringWheelHeater": 0}}
    client.http_condition = app_condition

    mqtt_condition = VehicleCondition(car_id="car-1", vin="VIN")
    mqtt_condition.climate.steering_wheel_heater_on = True

    merged = await coordinator._overlay_app_comfort(vehicle, mqtt_condition)
    assert merged.climate.steering_wheel_heater_on is False

    # A later failed overlay keeps the remembered server state instead of
    # exposing the unreliable MQTT flicker.
    client.condition_error = DeepalAPIError("app condition unavailable")
    flicker = VehicleCondition(car_id="car-1", vin="VIN")
    flicker.climate.steering_wheel_heater_on = True

    merged = await coordinator._overlay_app_comfort(vehicle, flicker)
    assert merged.climate.steering_wheel_heater_on is False


@pytest.mark.asyncio
async def test_steering_wheel_falls_back_to_mqtt_before_the_first_server_value():
    client = _FakeIntlClient([])
    client.condition_error = DeepalAPIError("app condition unavailable")
    coordinator, _ = _coordinator(client)
    vehicle = Vehicle(car_id="car-1", vin="VIN", protocol_type="MQTT")
    coordinator.vehicles = [vehicle]

    mqtt_condition = VehicleCondition(car_id="car-1", vin="VIN")
    mqtt_condition.climate.steering_wheel_heater_on = True

    merged = await coordinator._overlay_app_comfort(vehicle, mqtt_condition)
    assert merged.climate.steering_wheel_heater_on is True


@pytest.mark.asyncio
async def test_steering_wheel_keeps_remembered_state_when_the_field_is_missing():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    vehicle = Vehicle(car_id="car-1", vin="VIN", protocol_type="MQTT")
    coordinator.vehicles = [vehicle]

    app_condition = VehicleCondition(car_id="car-1", vin="VIN")
    app_condition.climate.steering_wheel_heater_on = False
    app_condition.raw_data = {"vehicleStatus": {"steeringWheelHeater": 0}}
    client.http_condition = app_condition

    first = VehicleCondition(car_id="car-1", vin="VIN")
    first.climate.steering_wheel_heater_on = True
    merged = await coordinator._overlay_app_comfort(vehicle, first)
    assert merged.climate.steering_wheel_heater_on is False

    # A successful server report without the field keeps the remembered state.
    client.http_condition = VehicleCondition(car_id="car-1", vin="VIN")
    flicker = VehicleCondition(car_id="car-1", vin="VIN")
    flicker.climate.steering_wheel_heater_on = True
    merged = await coordinator._overlay_app_comfort(vehicle, flicker)
    assert merged.climate.steering_wheel_heater_on is False


@pytest.mark.asyncio
async def test_command_poll_applies_the_remembered_steering_state():
    client = _FakeIntlClient(
        [CommandResult(status=CommandResultStatus.SUCCESS, code=0, raw={})]
    )
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [_mqtt_vehicle()]
    coordinator._last_steering_wheel["car-1"] = (False, 0)
    mqtt_condition = VehicleCondition(
        car_id="car-1", vin="", last_updated_timestamp=2000
    )
    mqtt_condition.climate.steering_wheel_heater_on = True
    mqtt_condition.climate.steering_wheel_heater_level = 1
    client.mqtt_condition = mqtt_condition

    await coordinator._async_poll_command("car-1", "cmd-1", 1000, 1.0, 0.01)

    condition = coordinator.data["car-1"]
    assert condition.climate.steering_wheel_heater_on is False
    assert condition.climate.steering_wheel_heater_level == 0


@pytest.mark.asyncio
async def test_app_condition_overlay_keeps_steering_and_defrost_when_stale():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    vehicle = Vehicle(car_id="car-1", vin="VIN", protocol_type="MQTT")
    coordinator.vehicles = [vehicle]

    app_condition = VehicleCondition(car_id="car-1", vin="VIN")
    app_condition.climate.steering_wheel_heater_on = False
    app_condition.climate.defrost_on = False
    app_condition.seats.front_left.ventilation_level = 2
    app_condition.raw_data = {
        "vehicleStatus": {"steeringWheelHeater": 0},
        "hvac": {"defrostStatus": 0},
        "seat": {"leftFront": {"ventStatus": 2}},
    }
    app_condition.last_updated_timestamp = 1000
    client.http_condition = app_condition

    mqtt_condition = VehicleCondition(car_id="car-1", vin="VIN")
    mqtt_condition.climate.steering_wheel_heater_on = True
    mqtt_condition.climate.defrost_on = True
    mqtt_condition.seats.front_left.ventilation_level = 3
    mqtt_condition.last_updated_timestamp = 2000

    merged = await coordinator._overlay_app_comfort(vehicle, mqtt_condition)

    # The unreliable MQTT fields never win over the app condition.
    assert merged.climate.steering_wheel_heater_on is False
    assert merged.climate.defrost_on is False
    # The seat block keeps the freshness rule: the newer snapshot wins.
    assert merged.seats.front_left.ventilation_level == 3


def _charge_overlay_pair() -> tuple[VehicleCondition, VehicleCondition]:
    """Return an app condition with connection data and an empty MQTT snapshot."""
    app_condition = VehicleCondition(car_id="car-1", vin="VIN")
    app_condition.battery.charger_connected = True
    app_condition.battery.dc_gun_connected = True
    app_condition.raw_data = {
        "charge": {"chargeConStatus": 3, "dcChargeGunConnectStatus": 2}
    }
    mqtt_condition = VehicleCondition(car_id="car-1", vin="VIN")
    mqtt_condition.mqtt_raw_data = {"soc": 71}
    return app_condition, mqtt_condition


@pytest.mark.asyncio
async def test_app_condition_overlay_fills_unreported_charge_connection():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    vehicle = Vehicle(car_id="car-1", vin="VIN", protocol_type="MQTT")
    coordinator.vehicles = [vehicle]
    app_condition, mqtt_condition = _charge_overlay_pair()
    client.http_condition = app_condition

    merged = await coordinator._overlay_app_comfort(vehicle, mqtt_condition)

    assert merged.battery.charger_connected is True
    assert merged.battery.dc_gun_connected is True


@pytest.mark.asyncio
async def test_app_condition_overlay_keeps_reported_charge_connection():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    vehicle = Vehicle(car_id="car-1", vin="VIN", protocol_type="MQTT")
    coordinator.vehicles = [vehicle]
    app_condition, mqtt_condition = _charge_overlay_pair()
    client.http_condition = app_condition
    mqtt_condition.mqtt_raw_data = {
        "acChargeGunConnectionState": 0,
        "dcDhargeGunConnectionState": 0,
    }
    mqtt_condition.battery.charger_connected = False
    mqtt_condition.battery.dc_gun_connected = False

    merged = await coordinator._overlay_app_comfort(vehicle, mqtt_condition)

    assert merged.battery.charger_connected is False
    assert merged.battery.dc_gun_connected is False


@pytest.mark.asyncio
async def test_app_condition_overlay_keeps_a_charging_flag_without_gun_data():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    vehicle = Vehicle(car_id="car-1", vin="VIN", protocol_type="MQTT")
    coordinator.vehicles = [vehicle]
    app_condition, mqtt_condition = _charge_overlay_pair()
    app_condition.battery.charger_connected = False
    client.http_condition = app_condition
    mqtt_condition.mqtt_raw_data = {"ChrgSts": 2}
    mqtt_condition.battery.charger_connected = True
    mqtt_condition.battery.charging_status = "2"

    merged = await coordinator._overlay_app_comfort(vehicle, mqtt_condition)

    assert merged.battery.charger_connected is True


@pytest.mark.asyncio
async def test_app_condition_overlay_skips_a_stale_charge_connection():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    vehicle = Vehicle(car_id="car-1", vin="VIN", protocol_type="MQTT")
    coordinator.vehicles = [vehicle]
    app_condition, mqtt_condition = _charge_overlay_pair()
    app_condition.last_updated_timestamp = 1000
    client.http_condition = app_condition
    mqtt_condition.last_updated_timestamp = 2000

    merged = await coordinator._overlay_app_comfort(vehicle, mqtt_condition)

    assert merged.battery.charger_connected is False
    assert merged.battery.dc_gun_connected is False


@pytest.mark.asyncio
async def test_app_condition_overlay_survives_an_unavailable_condition():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    vehicle = Vehicle(car_id="car-1", vin="VIN", protocol_type="MQTT")
    coordinator.vehicles = [vehicle]
    _, mqtt_condition = _charge_overlay_pair()
    client.condition_error = DeepalAPIError("app condition unavailable")

    merged = await coordinator._overlay_app_comfort(vehicle, mqtt_condition)

    assert merged.battery.charger_connected is False
    assert merged.battery.dc_gun_connected is False


def _phev_overlay_pair() -> tuple[VehicleCondition, VehicleCondition]:
    """Return an app condition and an MQTT snapshot with partial PHEV data."""
    app_condition = VehicleCondition(car_id="car-1", vin="VIN")
    app_condition.battery.charge_limit_percent = 80
    app_condition.fuel.level_percent = 55
    app_condition.fuel.remaining_range_km = 500
    app_condition.fuel.volume_l = 28.5
    app_condition.fuel.tank_capacity_l = 45.0
    app_condition.fuel.temperature_c = 18.0
    app_condition.last_updated_timestamp = 2000

    mqtt_condition = VehicleCondition(car_id="car-1", vin="VIN")
    mqtt_condition.fuel.level_percent = 42
    mqtt_condition.fuel.remaining_range_km = 310
    mqtt_condition.last_updated_timestamp = 1000
    return app_condition, mqtt_condition


@pytest.mark.asyncio
async def test_app_condition_overlay_fills_phev_fuel_and_charge_limit():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    vehicle = Vehicle(car_id="car-1", vin="VIN", protocol_type="MQTT")
    coordinator.vehicles = [vehicle]
    app_condition, mqtt_condition = _phev_overlay_pair()
    client.http_condition = app_condition

    merged = await coordinator._overlay_app_comfort(vehicle, mqtt_condition)

    # MQTT wins for the dynamic fuel values it carries.
    assert merged.fuel.level_percent == 42
    assert merged.fuel.remaining_range_km == 310
    # The app fills the static PHEV fields and the missing charge limit.
    assert merged.fuel.volume_l == 28.5
    assert merged.fuel.tank_capacity_l == 45.0
    assert merged.fuel.temperature_c == 18.0
    assert merged.battery.charge_limit_percent == 80


@pytest.mark.asyncio
async def test_app_condition_overlay_uses_stale_static_phev_fields():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    vehicle = Vehicle(car_id="car-1", vin="VIN", protocol_type="MQTT")
    coordinator.vehicles = [vehicle]
    app_condition, mqtt_condition = _phev_overlay_pair()
    app_condition.last_updated_timestamp = 1000
    mqtt_condition.last_updated_timestamp = 2000
    client.http_condition = app_condition

    merged = await coordinator._overlay_app_comfort(vehicle, mqtt_condition)

    assert merged.fuel.level_percent == 42
    assert merged.fuel.remaining_range_km == 310
    assert merged.fuel.volume_l == 28.5
    assert merged.fuel.tank_capacity_l == 45.0
    assert merged.battery.charge_limit_percent == 80


@pytest.mark.asyncio
async def test_mqtt_phev_values_win_over_the_app_condition():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    vehicle = Vehicle(car_id="car-1", vin="VIN", protocol_type="MQTT")
    coordinator.vehicles = [vehicle]
    app_condition, mqtt_condition = _phev_overlay_pair()
    mqtt_condition.fuel.volume_l = 20.0
    mqtt_condition.battery.charge_limit_percent = 70
    client.http_condition = app_condition

    merged = await coordinator._overlay_app_comfort(vehicle, mqtt_condition)

    assert merged.fuel.volume_l == 20.0
    assert merged.battery.charge_limit_percent == 70


@pytest.mark.asyncio
async def test_merge_retains_phev_fuel_and_charge_limit_when_the_app_fails():
    client = _FakeIntlClient([])
    previous = VehicleCondition(car_id="car-1", vin="VIN")
    previous.fuel.level_percent = 42
    previous.fuel.remaining_range_km = 310
    previous.fuel.volume_l = 28.5
    previous.fuel.tank_capacity_l = 45.0
    previous.fuel.temperature_c = 18.0
    previous.battery.charge_limit_percent = 80
    coordinator, _ = _coordinator(client, data={"car-1": previous})
    vehicle = Vehicle(car_id="car-1", vin="VIN", protocol_type="MQTT")
    coordinator.vehicles = [vehicle]
    client.condition_error = DeepalAPIError("app condition unavailable")

    mqtt_condition = VehicleCondition(car_id="car-1", vin="VIN")
    merged = coordinator._merge_condition("car-1", mqtt_condition)
    merged = await coordinator._overlay_app_comfort(vehicle, merged)

    assert merged.fuel.level_percent == 42
    assert merged.fuel.remaining_range_km == 310
    assert merged.fuel.volume_l == 28.5
    assert merged.fuel.tank_capacity_l == 45.0
    assert merged.fuel.temperature_c == 18.0
    assert merged.battery.charge_limit_percent == 80


@pytest.mark.asyncio
async def test_unconfirmed_optimistic_charge_limit_expires():
    client = _FakeIntlClient([])
    previous = VehicleCondition(car_id="car-1", vin="VIN")
    previous.battery.charge_limit_percent = 80
    coordinator, _ = _coordinator(client, data={"car-1": previous})
    coordinator._optimistic_pending = {
        "car-1": {"battery.charge_limit_percent"},
    }

    merged = coordinator._merge_condition(
        "car-1", VehicleCondition(car_id="car-1", vin="VIN")
    )

    assert merged.battery.charge_limit_percent is None


@pytest.mark.asyncio
async def test_condition_uses_sda_service_for_sda_vehicles():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [Vehicle(car_id="car-1", vin="VIN", protocol_type="SDA-MQTT")]
    client.mqtt_condition = VehicleCondition(
        car_id="car-1", vin="VIN", condition_source="sda-mqtt"
    )

    condition = await coordinator._async_fetch_condition("car-1")

    assert client.mqtt_sda_flags == [True]
    assert condition.condition_source == "sda-mqtt"


@pytest.mark.asyncio
async def test_condition_uses_legacy_service_for_mqtt_vehicles():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [Vehicle(car_id="car-1", vin="VIN", protocol_type="MQTT")]
    client.mqtt_condition = VehicleCondition(
        car_id="car-1", vin="VIN", condition_source="legacy-mqtt"
    )

    condition = await coordinator._async_fetch_condition("car-1")

    assert client.mqtt_sda_flags == [False]
    assert condition.condition_source == "legacy-mqtt"


@pytest.mark.asyncio
async def test_condition_marks_the_rest_source():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [Vehicle(car_id="car-1", vin="VIN", protocol_type="REST")]

    condition = await coordinator._async_fetch_condition("car-1")

    assert client.mqtt_sda_flags == []
    assert condition.condition_source == "rest"


@pytest.mark.asyncio
async def test_condition_falls_back_to_sda_rest_for_sda_vehicles():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [Vehicle(car_id="car-1", vin="VIN", protocol_type="SDA-MQTT")]

    async def fail_mqtt(vehicle_id, vin=None, *, sda=False):
        raise DeepalAPIError("MQTT unavailable")

    client.s05_mqtt_condition = fail_mqtt
    client.sda_rest_condition = VehicleCondition(
        car_id="car-1", vin="VIN", condition_source="sda-rest"
    )

    condition = await coordinator._async_fetch_condition("car-1")

    assert client.sda_rest_calls == 1
    assert condition.condition_source == "sda-rest"


@pytest.mark.asyncio
async def test_condition_falls_back_to_intl_rest_when_sda_rest_fails():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [Vehicle(car_id="car-1", vin="VIN", protocol_type="SDA-MQTT")]

    async def fail_mqtt(vehicle_id, vin=None, *, sda=False):
        raise DeepalAPIError("MQTT unavailable")

    client.s05_mqtt_condition = fail_mqtt
    client.sda_rest_condition = None
    client.http_condition = VehicleCondition(car_id="car-1", vin="VIN")

    condition = await coordinator._async_fetch_condition("car-1")

    assert client.sda_rest_calls == 1
    assert condition.condition_source == "rest"


@pytest.mark.asyncio
async def test_failed_mqtt_exchange_is_kept_for_diagnostics():
    from deepal.mqtt import MqttExchangeResult, SdaConditionPlan

    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [Vehicle(car_id="car-1", vin="VIN", protocol_type="SDA-MQTT")]

    async def fail_mqtt(vehicle_id, vin=None, *, sda=False):
        client.last_mqtt_exchange = MqttExchangeResult(
            params={},
            source=None,
            variants={"sda-mqtt": {}, "sda-mqtt-sections": {}},
            plan=SdaConditionPlan(device_did="plan-did"),
        )
        raise DeepalAPIError("S05 MQTT telemetry did not return vehicle condition.")

    client.s05_mqtt_condition = fail_mqtt
    client.sda_rest_condition = None
    client.http_condition = VehicleCondition(car_id="car-1", vin="VIN")

    await coordinator._async_fetch_condition("car-1")

    attempt = coordinator.mqtt_attempt("car-1")
    assert attempt is not None
    assert attempt["variants"] == {"sda-mqtt": {}, "sda-mqtt-sections": {}}
    assert attempt["plan"]["device_did"] == "plan-did"


@pytest.mark.asyncio
async def test_merge_condition_retains_last_valid_seat_levels():
    client = _FakeIntlClient([])
    previous = VehicleCondition(car_id="car-1", vin="")
    previous.seats.front_left.ventilation_level = 2
    previous.seats.front_right.heating_level = 1
    coordinator, _ = _coordinator(client, data={"car-1": previous})

    unknown = VehicleCondition(car_id="car-1", vin="")
    merged = coordinator._merge_condition("car-1", unknown)
    assert merged.seats.front_left.ventilation_level == 2
    assert merged.seats.front_right.heating_level == 1
    assert merged.seats.rear_left.heating_level is None

    reported = VehicleCondition(car_id="car-1", vin="")
    reported.seats.front_left.ventilation_level = 3
    merged = coordinator._merge_condition("car-1", reported)
    assert merged.seats.front_left.ventilation_level == 3
    assert merged.seats.front_right.heating_level == 1


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


@pytest.mark.asyncio
async def test_command_cooldown_rejects_a_repeat_until_it_expires():
    client = _FakeIntlClient(
        [
            CommandResult(
                status=CommandResultStatus.SUCCESS, code=0, raw={"resultCode": 0}
            ),
            CommandResult(
                status=CommandResultStatus.SUCCESS, code=0, raw={"resultCode": 0}
            ),
        ]
    )
    coordinator, _ = _coordinator(client)
    calls = 0

    async def send_command() -> str:
        nonlocal calls
        calls += 1
        return "cmd-1"

    await coordinator.async_execute_command(
        "car-1", send_command, cooldown_key="flash_lights"
    )
    assert calls == 1

    with pytest.raises(HomeAssistantError, match="wait"):
        await coordinator.async_execute_command(
            "car-1", send_command, cooldown_key="flash_lights"
        )
    assert calls == 1

    coordinator._command_cooldowns[("car-1", "flash_lights")] = 0.0
    await coordinator.async_execute_command(
        "car-1", send_command, cooldown_key="flash_lights"
    )
    assert calls == 2


@pytest.mark.asyncio
async def test_flash_and_honk_has_its_own_thirty_second_cooldown():
    client = _FakeIntlClient(
        [
            CommandResult(
                status=CommandResultStatus.SUCCESS, code=0, raw={"resultCode": 0}
            ),
            CommandResult(
                status=CommandResultStatus.SUCCESS, code=0, raw={"resultCode": 0}
            ),
        ]
    )
    coordinator, _ = _coordinator(client)
    calls = 0

    async def send_command() -> str:
        nonlocal calls
        calls += 1
        return "cmd-1"

    await coordinator.async_execute_command(
        "car-1", send_command, cooldown_key="flash_and_honk"
    )

    with pytest.raises(HomeAssistantError, match="wait"):
        await coordinator.async_execute_command(
            "car-1", send_command, cooldown_key="flash_and_honk"
        )
    assert calls == 1
    assert ("car-1", "flash_and_honk") in coordinator._command_cooldowns

    # The combined action does not share the flash key, so the flash cooldown
    # does not block it.
    await coordinator.async_execute_command(
        "car-1", send_command, cooldown_key="flash_lights"
    )
    assert calls == 2


@pytest.mark.asyncio
async def test_command_cooldowns_are_independent_per_command():
    client = _FakeIntlClient(
        [
            CommandResult(
                status=CommandResultStatus.SUCCESS, code=0, raw={"resultCode": 0}
            ),
            CommandResult(
                status=CommandResultStatus.SUCCESS, code=0, raw={"resultCode": 0}
            ),
        ]
    )
    coordinator, _ = _coordinator(client)

    async def send_command() -> str:
        return "cmd-1"

    await coordinator.async_execute_command(
        "car-1", send_command, cooldown_key="flash_lights"
    )
    await coordinator.async_execute_command(
        "car-1", send_command, cooldown_key="honk_horn"
    )

    assert ("car-1", "flash_lights") in coordinator._command_cooldowns
    assert ("car-1", "honk_horn") in coordinator._command_cooldowns


@pytest.mark.asyncio
async def test_failed_command_does_not_start_a_cooldown():
    client = _FakeIntlClient(
        [
            CommandResult(
                status=CommandResultStatus.FAILED,
                code=-1,
                raw={"resultCode": -1},
                error_message="TBOX_2001",
            )
        ]
    )
    coordinator, _ = _coordinator(client)

    async def send_command() -> str:
        return "cmd-1"

    with pytest.raises(HomeAssistantError):
        await coordinator.async_execute_command(
            "car-1", send_command, cooldown_key="honk_horn"
        )

    assert ("car-1", "honk_horn") not in coordinator._command_cooldowns


@pytest.mark.asyncio
async def test_merge_condition_retains_last_valid_comfort_states():
    client = _FakeIntlClient([])
    previous = VehicleCondition(car_id="car-1", vin="")
    previous.climate.steering_wheel_heater_on = True
    previous.climate.steering_wheel_heater_level = 2
    previous.climate.defrost_on = True
    coordinator, _ = _coordinator(client, data={"car-1": previous})

    omitted = VehicleCondition(car_id="car-1", vin="")
    merged = coordinator._merge_condition("car-1", omitted)
    assert merged.climate.steering_wheel_heater_on is True
    assert merged.climate.steering_wheel_heater_level == 2
    assert merged.climate.defrost_on is True

    reported = VehicleCondition(car_id="car-1", vin="")
    reported.climate.steering_wheel_heater_on = False
    reported.climate.steering_wheel_heater_level = 0
    reported.climate.defrost_on = False
    merged = coordinator._merge_condition("car-1", reported)
    assert merged.climate.steering_wheel_heater_on is False
    assert merged.climate.steering_wheel_heater_level == 0
    assert merged.climate.defrost_on is False


def _mqtt_vehicle(car_id: str = "car-1", protocol: str | None = "MQTT") -> Vehicle:
    return Vehicle(car_id=car_id, vin="VIN-PLACEHOLDER-1", protocol_type=protocol)


@pytest.mark.asyncio
async def test_refresh_wakes_stale_mqtt_vehicle():
    client = _FakeIntlClient([])
    stale = int(time.time()) - 3600
    coordinator, _ = _coordinator(
        client,
        data={
            "car-1": VehicleCondition(
                car_id="car-1", vin="", last_updated_timestamp=stale
            )
        },
    )
    coordinator.vehicles = [_mqtt_vehicle()]
    client.condition_timestamps = [stale + 30]

    result = await coordinator.async_refresh_vehicle("car-1")

    assert result is WakeResult.FRESH
    assert client.events == ["wake", "mqtt_wait", "condition", "condition"]
    assert client.wake_calls == 1
    assert coordinator.data["car-1"].last_updated_timestamp == stale + 30
    assert "car-1" in coordinator._last_wake_at


@pytest.mark.asyncio
async def test_wake_recovers_a_ca_token_rejection():
    client = _FakeIntlClient([])
    stale = int(time.time()) - 3600
    coordinator, _ = _coordinator(
        client,
        data={
            "car-1": VehicleCondition(
                car_id="car-1", vin="", last_updated_timestamp=stale
            )
        },
    )
    coordinator.vehicles = [_mqtt_vehicle()]
    client.condition_timestamps = [stale + 30]
    client.wake_error = DeepalAPIError(
        "token rejected", code="APIGW_-1_7_01_004"
    )

    result = await coordinator.async_refresh_vehicle("car-1")

    assert result is WakeResult.FRESH
    assert client.wake_calls == 2
    assert client.refresh_calls == 1
    assert client.access_token == "refreshed_token_1"


@pytest.mark.asyncio
async def test_wake_keeps_the_ca_code_when_the_retry_is_also_rejected():
    client = _FakeIntlClient([])
    stale = int(time.time()) - 3600
    coordinator, _ = _coordinator(
        client,
        data={
            "car-1": VehicleCondition(
                car_id="car-1", vin="", last_updated_timestamp=stale
            )
        },
    )
    coordinator.vehicles = [_mqtt_vehicle()]
    client.condition_timestamps = [stale] * 20
    error = DeepalAPIError("token rejected", code="APIGW_-1_7_01_004")
    client.wake_errors = [error, error]

    result = await coordinator.async_refresh_vehicle("car-1")

    assert result is WakeResult.FAILED
    assert client.wake_calls == 2
    assert client.refresh_calls == 1
    assert coordinator.wake_result("car-1")["code"] == "APIGW_-1_7_01_004"


@pytest.mark.asyncio
async def test_concurrent_refreshes_publish_a_single_wake():
    client = _FakeIntlClient([])
    stale = int(time.time()) - 3600
    coordinator, _ = _coordinator(
        client,
        data={
            "car-1": VehicleCondition(
                car_id="car-1", vin="", last_updated_timestamp=stale
            )
        },
    )
    coordinator.vehicles = [_mqtt_vehicle()]
    client.condition_timestamps = [stale + 30, stale + 30]

    await asyncio.gather(
        coordinator.async_refresh_vehicle("car-1"),
        coordinator.async_refresh_vehicle("car-1"),
    )

    assert client.wake_calls == 1


@pytest.mark.asyncio
async def test_refresh_wake_disabled_does_not_wake():
    client = _FakeIntlClient([])
    stale = int(time.time()) - 3600
    coordinator, _ = _coordinator(
        client,
        data={
            "car-1": VehicleCondition(
                car_id="car-1", vin="", last_updated_timestamp=stale
            )
        },
    )
    coordinator.wake_enabled = False
    coordinator.vehicles = [_mqtt_vehicle()]

    await coordinator.async_refresh_vehicle("car-1")

    assert client.wake_calls == 0
    assert client.events == []


@pytest.mark.asyncio
async def test_refresh_does_not_wake_sda_mqtt_vehicle():
    client = _FakeIntlClient([])
    stale = int(time.time()) - 3600
    coordinator, _ = _coordinator(
        client,
        data={
            "car-1": VehicleCondition(
                car_id="car-1", vin="", last_updated_timestamp=stale
            )
        },
    )
    coordinator.vehicles = [_mqtt_vehicle(protocol="SDA-MQTT")]

    await coordinator.async_refresh_vehicle("car-1")

    assert client.wake_calls == 0
    assert client.events == []


@pytest.mark.asyncio
async def test_refresh_skips_wake_when_mqtt_report_is_fresh():
    client = _FakeIntlClient([])
    now = int(time.time())
    coordinator, _ = _coordinator(
        client,
        data={
            "car-1": VehicleCondition(
                car_id="car-1", vin="", last_updated_timestamp=now
            )
        },
    )
    coordinator.vehicles = [_mqtt_vehicle()]

    await coordinator.async_refresh_vehicle("car-1")

    assert client.events == []
    assert client.wake_calls == 0


@pytest.mark.asyncio
async def test_refresh_wake_is_throttled_per_vehicle():
    client = _FakeIntlClient([])
    stale = int(time.time()) - 3600
    coordinator, _ = _coordinator(
        client,
        data={
            "car-1": VehicleCondition(
                car_id="car-1", vin="", last_updated_timestamp=stale
            )
        },
    )
    coordinator.vehicles = [_mqtt_vehicle()]
    coordinator._last_wake_at["car-1"] = time.monotonic()

    await coordinator.async_refresh_vehicle("car-1")

    assert client.events == []
    assert client.wake_calls == 0


@pytest.mark.asyncio
async def test_refresh_returns_no_report_when_woken_vehicle_does_not_report():
    client = _FakeIntlClient([])
    stale = int(time.time()) - 3600
    coordinator, _ = _coordinator(
        client,
        data={
            "car-1": VehicleCondition(
                car_id="car-1", vin="", last_updated_timestamp=stale
            )
        },
    )
    coordinator.vehicles = [_mqtt_vehicle()]
    client.condition_timestamps = [stale] * 20

    result = await coordinator.async_refresh_vehicle("car-1")

    assert result is WakeResult.NO_REPORT
    assert client.wake_calls == 1
    assert coordinator.wake_result("car-1")["result"] == WakeResult.NO_REPORT


@pytest.mark.asyncio
async def test_refresh_wake_failure_without_report_returns_failed():
    client = _FakeIntlClient([])
    client.wake_error = DeepalAPIError("wake rejected", code="VVCC_-1_-1_02_023")
    stale = int(time.time()) - 3600
    coordinator, _ = _coordinator(
        client,
        data={
            "car-1": VehicleCondition(
                car_id="car-1", vin="", last_updated_timestamp=stale
            )
        },
    )
    coordinator.vehicles = [_mqtt_vehicle()]
    client.condition_timestamps = [stale] * 20

    result = await coordinator.async_refresh_vehicle("car-1")

    assert result is WakeResult.FAILED
    assert client.wake_calls == 1
    assert client.events[0] == "wake"
    assert "mqtt_wait" in client.events
    assert "car-1" not in coordinator._last_wake_at
    assert coordinator.wake_result("car-1")["wake_sent"] is False


@pytest.mark.asyncio
async def test_refresh_wake_failure_with_report_succeeds():
    client = _FakeIntlClient([])
    client.wake_error = DeepalAPIError("Vehicle wake did not return a response.")
    stale = int(time.time()) - 3600
    coordinator, _ = _coordinator(
        client,
        data={
            "car-1": VehicleCondition(
                car_id="car-1", vin="", last_updated_timestamp=stale
            )
        },
    )
    coordinator.vehicles = [_mqtt_vehicle()]
    client.condition_timestamps = [stale + 30]

    result = await coordinator.async_refresh_vehicle("car-1")

    assert result is WakeResult.FRESH
    assert client.wake_calls == 1
    assert client.events == ["wake", "mqtt_wait", "condition", "condition"]
    assert "car-1" not in coordinator._last_wake_at
    assert coordinator.wake_result("car-1")["wake_sent"] is False


@pytest.mark.asyncio
async def test_refresh_rest_vehicle_uses_condition_inquiry():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [_mqtt_vehicle(protocol=None)]

    await coordinator.async_refresh_vehicle("car-1")

    assert client.events == ["condition_inquiry"]
    assert client.wake_calls == 0


@pytest.mark.asyncio
async def test_periodic_update_does_not_wake():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [_mqtt_vehicle()]
    coordinator._capabilities = {}

    await coordinator._async_update_data()

    assert client.wake_calls == 0
    assert "wake" not in client.events


@pytest.mark.asyncio
async def test_periodic_update_recovers_from_ca_token_rejection():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [_mqtt_vehicle()]
    coordinator._capabilities = {}
    client.mqtt_condition_errors = [
        DeepalAPIError("token rejected", code="APIGW_-1_7_01_004")
    ]

    data = await coordinator._async_update_data()

    assert client.refresh_calls == 1
    assert client.mqtt_condition_errors == []
    assert data["car-1"].car_id == "car-1"


@pytest.mark.asyncio
async def test_rate_limited_update_defers_the_next_refresh():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [_mqtt_vehicle(protocol=None)]
    coordinator._capabilities = {}
    client.condition_error = DeepalRateLimitError("limit")

    with pytest.raises(UpdateFailed) as err:
        await coordinator._async_update_data()

    assert err.value.retry_after == 300.0


@pytest.mark.asyncio
async def test_rate_limited_update_honors_a_longer_gateway_wait():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [_mqtt_vehicle(protocol=None)]
    coordinator._capabilities = {}
    client.condition_error = DeepalRateLimitError("limit", retry_after=900)

    with pytest.raises(UpdateFailed) as err:
        await coordinator._async_update_data()

    assert err.value.retry_after == 900.0


@pytest.mark.asyncio
async def test_short_scan_interval_does_not_tighten_the_backoff():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.update_interval = timedelta(seconds=30)
    coordinator.vehicles = [_mqtt_vehicle(protocol=None)]
    coordinator._capabilities = {}
    client.condition_error = DeepalRateLimitError("limit")

    with pytest.raises(UpdateFailed) as err:
        await coordinator._async_update_data()

    assert err.value.retry_after == 300.0


@pytest.mark.asyncio
async def test_transport_errors_keep_no_retry_after():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [_mqtt_vehicle(protocol=None)]
    coordinator._capabilities = {}
    client.condition_error = DeepalAPIError("boom")

    with pytest.raises(UpdateFailed) as err:
        await coordinator._async_update_data()

    assert err.value.retry_after is None


class _RecordingStore:
    """Store double recording the saved snapshots."""

    def __init__(self) -> None:
        self.saved: list[dict] = []

    async def async_load(self):
        return None

    def async_delay_save(self, data, delay):
        self.saved.append(data())

    async def async_remove(self):
        pass


@pytest.mark.asyncio
async def test_periodic_update_tracks_charging_sessions():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [_mqtt_vehicle()]
    coordinator._capabilities = {}
    client.mqtt_condition = VehicleCondition(car_id="car-1", vin="VIN")
    client.mqtt_condition.battery.charging_status = "2"
    client.mqtt_condition.battery.soc_percentage = 55
    store = _RecordingStore()
    coordinator.charging = ChargingSessionManager(store)

    await coordinator._async_update_data()

    attrs = coordinator.charging.attributes("car-1")
    assert attrs["current_charge"]["start_level"] == 55
    assert store.saved
    assert coordinator._charging_read_task is not None
    coordinator._sync_charging_read({})
    assert coordinator._charging_read_task is None


@pytest.mark.asyncio
async def test_periodic_update_does_not_track_a_plugged_only_car():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [_mqtt_vehicle()]
    coordinator._capabilities = {}
    client.mqtt_condition = VehicleCondition(car_id="car-1", vin="VIN")
    client.mqtt_condition.battery.charging_status = "2"
    client.mqtt_condition.battery.soc_percentage = 55
    client.mqtt_condition.mqtt_raw_data = {"ChrgSts": 2}
    store = _RecordingStore()
    coordinator.charging = ChargingSessionManager(store)

    await coordinator._async_update_data()

    assert coordinator.charging.attributes("car-1") == {}
    assert store.saved == []


def _charging_condition(car_id: str, charging: bool = True) -> VehicleCondition:
    condition = VehicleCondition(car_id=car_id, vin="VIN")
    condition.battery.charging_status = "3" if charging else "0"
    return condition


@pytest.mark.asyncio
async def test_charging_read_updates_only_the_requested_vehicle():
    client = _FakeIntlClient([])
    coordinator, updates = _coordinator(client)
    coordinator.vehicles = [_mqtt_vehicle(protocol=None)]
    parked = _charging_condition("car-2", charging=False)
    coordinator.data = {"car-1": _charging_condition("car-1"), "car-2": parked}
    refreshed: list[str] = []

    async def refresh(vehicle_id: str) -> None:
        refreshed.append(vehicle_id)

    coordinator.async_refresh_vehicle = refresh
    fresh = _charging_condition("car-1")
    fresh.last_updated_timestamp = 2000
    client.http_condition = fresh

    await coordinator._async_read_charging_vehicle("car-1")

    assert refreshed == ["car-1"]
    assert updates[-1]["car-1"].last_updated_timestamp == 2000
    assert updates[-1]["car-2"] is parked


@pytest.mark.asyncio
async def test_charging_read_loop_reads_only_charging_vehicles_and_stops():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator._charging_read_interval = 0.01
    reads: list[str] = []

    async def read(vehicle_id: str) -> None:
        reads.append(vehicle_id)

    coordinator._async_read_charging_vehicle = read
    data = {
        "car-1": _charging_condition("car-1"),
        "car-2": _charging_condition("car-2", charging=False),
    }
    coordinator.data = data
    coordinator._sync_charging_read(data)
    task = coordinator._charging_read_task
    assert task is not None

    await asyncio.sleep(0.03)

    assert reads
    assert set(reads) == {"car-1"}
    coordinator._sync_charging_read(
        {
            "car-1": _charging_condition("car-1", charging=False),
            "car-2": _charging_condition("car-2", charging=False),
        }
    )
    await asyncio.sleep(0.01)
    assert task.done()


@pytest.mark.asyncio
async def test_charging_read_loop_is_not_duplicated():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator._charging_read_interval = 0.01

    async def read(vehicle_id: str) -> None:
        return None

    coordinator._async_read_charging_vehicle = read
    data = {"car-1": _charging_condition("car-1")}
    coordinator.data = data
    coordinator._sync_charging_read(data)
    first = coordinator._charging_read_task
    coordinator._sync_charging_read(data)

    assert first is coordinator._charging_read_task
    coordinator._sync_charging_read({})
    await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_charging_read_failure_keeps_the_loop_alive():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator._charging_read_interval = 0.01
    reads: list[str] = []

    async def read(vehicle_id: str) -> None:
        reads.append(vehicle_id)
        raise HomeAssistantError("boom")

    coordinator._async_read_charging_vehicle = read
    data = {"car-1": _charging_condition("car-1")}
    coordinator.data = data
    coordinator._sync_charging_read(data)
    task = coordinator._charging_read_task

    await asyncio.sleep(0.03)

    assert len(reads) >= 2
    assert task is not None and not task.done()
    coordinator._sync_charging_read({})
    await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_charging_read_task_cancellation_clears_the_lifecycle():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator._charging_read_interval = 600.0

    async def read(vehicle_id: str) -> None:
        return None

    coordinator._async_read_charging_vehicle = read
    data = {"car-1": _charging_condition("car-1")}
    coordinator.data = data
    coordinator._sync_charging_read(data)
    task = coordinator._charging_read_task
    assert task is not None
    await asyncio.sleep(0)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert coordinator._charging_read_task is None
    assert coordinator._charging_read_stop is None


@pytest.mark.asyncio
async def test_vehicle_list_first_fetch_populates_without_reload():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    reloads: list[str] = []
    coordinator.entry = SimpleNamespace(entry_id="entry-1", data={})
    coordinator.hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_schedule_reload=reloads.append)
    )

    async def get_vehicles():
        return [Vehicle(car_id="car-1", vin="")]

    client.get_vehicles = get_vehicles

    await coordinator._async_maybe_refresh_vehicles()

    assert [vehicle.car_id for vehicle in coordinator.vehicles] == ["car-1"]
    assert reloads == []


@pytest.mark.asyncio
async def test_vehicle_list_unchanged_within_interval_skips_the_request():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [_mqtt_vehicle("car-1")]
    coordinator._last_vehicle_refresh = time.monotonic()

    async def get_vehicles():
        raise AssertionError("vehicle list must not be fetched")

    client.get_vehicles = get_vehicles

    await coordinator._async_maybe_refresh_vehicles()

    assert [vehicle.car_id for vehicle in coordinator.vehicles] == ["car-1"]


@pytest.mark.asyncio
async def test_vehicle_list_unchanged_after_interval_refetches_without_reload():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [_mqtt_vehicle("car-1")]
    coordinator._last_vehicle_refresh = time.monotonic() - 601
    reloads: list[str] = []
    coordinator.entry = SimpleNamespace(entry_id="entry-1", data={})
    coordinator.hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_schedule_reload=reloads.append)
    )

    async def get_vehicles():
        return [Vehicle(car_id="car-1", vin="VIN-FRESH")]

    client.get_vehicles = get_vehicles

    await coordinator._async_maybe_refresh_vehicles()

    assert [vehicle.car_id for vehicle in coordinator.vehicles] == ["car-1"]
    assert coordinator.vehicles[0].vin == "VIN-FRESH"
    assert reloads == []


@pytest.mark.asyncio
async def test_vehicle_list_change_schedules_a_reload():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [_mqtt_vehicle("car-1")]
    # -inf means "never refreshed": 0.0 only looks old once the host clock
    # has run for longer than the refresh interval (a fresh CI runner has not).
    coordinator._last_vehicle_refresh = -math.inf
    reloads: list[str] = []
    coordinator.entry = SimpleNamespace(entry_id="entry-9", data={})
    coordinator.hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_schedule_reload=reloads.append)
    )

    async def get_vehicles():
        return [Vehicle(car_id="car-1", vin=""), Vehicle(car_id="car-2", vin="")]

    client.get_vehicles = get_vehicles

    await coordinator._async_maybe_refresh_vehicles()

    assert reloads == ["entry-9"]
    assert [vehicle.car_id for vehicle in coordinator.vehicles] == ["car-1", "car-2"]


@pytest.mark.asyncio
async def test_vehicle_list_failure_keeps_the_current_list():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [_mqtt_vehicle("car-1")]
    # -inf means "never refreshed": 0.0 only looks old once the host clock
    # has run for longer than the refresh interval (a fresh CI runner has not).
    coordinator._last_vehicle_refresh = -math.inf
    reloads: list[str] = []
    coordinator.hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_schedule_reload=reloads.append)
    )

    async def get_vehicles():
        raise DeepalConnectionError("offline")

    client.get_vehicles = get_vehicles

    await coordinator._async_maybe_refresh_vehicles()

    assert [vehicle.car_id for vehicle in coordinator.vehicles] == ["car-1"]
    assert reloads == []


@pytest.mark.asyncio
async def test_vehicle_list_empty_refresh_keeps_the_current_list():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [_mqtt_vehicle("car-1")]
    # -inf means "never refreshed": 0.0 only looks old once the host clock
    # has run for longer than the refresh interval (a fresh CI runner has not).
    coordinator._last_vehicle_refresh = -math.inf
    reloads: list[str] = []
    coordinator.hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_schedule_reload=reloads.append)
    )

    async def get_vehicles():
        return []

    client.get_vehicles = get_vehicles

    await coordinator._async_maybe_refresh_vehicles()

    assert [vehicle.car_id for vehicle in coordinator.vehicles] == ["car-1"]
    assert reloads == []


def _stale_condition(
    car_id: str = "car-1", stale_seconds: int = 3600
) -> VehicleCondition:
    return VehicleCondition(
        car_id=car_id,
        vin="",
        last_updated_timestamp=int(time.time()) - stale_seconds,
    )


async def _run_pin_command(
    coordinator: DeepalDataUpdateCoordinator,
    events: list[str] | None = None,
) -> list[str]:
    sent: list[str] = []

    async def send_command() -> str:
        sent.append("cmd-1")
        if events is not None:
            events.append("send")
        return "cmd-1"

    await coordinator.async_execute_command(
        "car-1",
        send_command,
        wake_first=True,
        timeout=1.0,
        interval=0.01,
    )
    return sent


@pytest.mark.asyncio
async def test_pin_command_wake_uses_the_thirty_second_timeout():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(
        client, data={"car-1": _stale_condition()}
    )
    coordinator.vehicles = [_mqtt_vehicle()]
    seen: list[float | None] = []

    async def wake(
        vehicle_id: str,
        *,
        wait_when_unconfirmed: bool = False,
        timeout: float | None = None,
    ) -> WakeResult:
        seen.append(timeout)
        return WakeResult.FRESH

    coordinator._async_wake_and_wait = wake

    await coordinator._async_prepare_pin_command("car-1")

    assert seen == [30]


@pytest.mark.asyncio
async def test_pin_command_wakes_stale_mqtt_vehicle_first():
    client = _FakeIntlClient([_success_result()])
    stale = int(time.time()) - 3600
    coordinator, _ = _coordinator(
        client, data={"car-1": _stale_condition()}
    )
    coordinator.vehicles = [_mqtt_vehicle()]
    client.condition_timestamps = [stale + 30]

    sent = await _run_pin_command(coordinator, client.events)

    assert sent == ["cmd-1"]
    assert client.wake_calls == 1
    assert client.events.index("wake") < client.events.index("send")
    assert "car-1" in coordinator._last_wake_at


@pytest.mark.asyncio
async def test_pin_command_skips_wake_when_mqtt_report_is_fresh():
    client = _FakeIntlClient([_success_result()])
    coordinator, _ = _coordinator(
        client,
        data={"car-1": _current_condition(timestamp=int(time.time()))},
    )
    coordinator.vehicles = [_mqtt_vehicle()]

    sent = await _run_pin_command(coordinator)

    assert sent == ["cmd-1"]
    assert client.wake_calls == 0


@pytest.mark.asyncio
async def test_pin_command_wake_is_throttled_per_vehicle():
    client = _FakeIntlClient([_success_result()])
    coordinator, _ = _coordinator(
        client, data={"car-1": _stale_condition()}
    )
    coordinator.vehicles = [_mqtt_vehicle()]
    coordinator._last_wake_at["car-1"] = time.monotonic()

    sent = await _run_pin_command(coordinator)

    assert sent == ["cmd-1"]
    assert client.wake_calls == 0


@pytest.mark.asyncio
async def test_pin_command_wake_failure_still_sends_the_command():
    client = _FakeIntlClient([_success_result()])
    client.wake_error = DeepalAPIError(
        "wake rejected", code="VVCC_-1_-1_02_023"
    )
    coordinator, _ = _coordinator(
        client, data={"car-1": _stale_condition()}
    )
    coordinator.vehicles = [_mqtt_vehicle()]

    sent = await _run_pin_command(coordinator)

    assert sent == ["cmd-1"]
    assert client.wake_calls == 1
    assert "car-1" not in coordinator._last_wake_at


@pytest.mark.asyncio
async def test_pin_command_sends_after_wake_without_a_fresh_report():
    client = _FakeIntlClient([_success_result()])
    stale = int(time.time()) - 3600
    coordinator, _ = _coordinator(
        client, data={"car-1": _stale_condition()}
    )
    coordinator.vehicles = [_mqtt_vehicle()]
    client.condition_timestamps = [stale] * 50

    sent = await _run_pin_command(coordinator)

    assert sent == ["cmd-1"]
    assert client.wake_calls == 1
    assert "car-1" in coordinator._last_wake_at


@pytest.mark.asyncio
async def test_non_pin_command_does_not_wake():
    client = _FakeIntlClient([_success_result()])
    coordinator, _ = _coordinator(
        client, data={"car-1": _stale_condition()}
    )
    coordinator.vehicles = [_mqtt_vehicle()]

    async def send_command() -> str:
        return "cmd-1"

    await coordinator.async_execute_command(
        "car-1", send_command, timeout=1.0, interval=0.01
    )

    assert client.wake_calls == 0


@pytest.mark.asyncio
async def test_pin_command_does_not_wake_rest_vehicle():
    client = _FakeIntlClient([_success_result()])
    coordinator, _ = _coordinator(
        client, data={"car-1": _stale_condition()}
    )
    coordinator.vehicles = [_mqtt_vehicle(protocol=None)]

    sent = await _run_pin_command(coordinator)

    assert sent == ["cmd-1"]
    assert client.wake_calls == 0


@pytest.mark.asyncio
async def test_pin_command_does_not_wake_sda_mqtt_vehicle():
    client = _FakeIntlClient([_success_result()])
    coordinator, _ = _coordinator(
        client, data={"car-1": _stale_condition()}
    )
    coordinator.vehicles = [_mqtt_vehicle(protocol="SDA-MQTT")]

    sent = await _run_pin_command(coordinator)

    assert sent == ["cmd-1"]
    assert client.wake_calls == 0


@pytest.mark.asyncio
async def test_concurrent_pin_commands_wake_once():
    client = _FakeIntlClient([_success_result(), _success_result()])
    stale = int(time.time()) - 3600
    coordinator, _ = _coordinator(
        client, data={"car-1": _stale_condition()}
    )
    coordinator.vehicles = [_mqtt_vehicle()]
    client.condition_timestamps = [stale + 30] * 10
    started = asyncio.Event()
    release = asyncio.Event()
    original_wake = client.wake_vehicle

    async def delayed_wake(vehicle_id: str) -> None:
        started.set()
        await release.wait()
        await original_wake(vehicle_id)

    client.wake_vehicle = delayed_wake

    async def send_command() -> str:
        return "cmd-1"

    first = asyncio.create_task(
        coordinator.async_execute_command(
            "car-1", send_command, wake_first=True, timeout=1.0, interval=0.01
        )
    )
    await started.wait()
    second = asyncio.create_task(
        coordinator.async_execute_command(
            "car-1", send_command, wake_first=True, timeout=1.0, interval=0.01
        )
    )
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(first, second)

    assert client.wake_calls == 1


@pytest.mark.asyncio
async def test_asleep_command_rejection_is_actionable():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)

    async def send_command() -> str:
        raise DeepalAPIError(
            "API Error: APP_1_1_05_001 Operation failed",
            code="APP_1_1_05_001",
        )

    with pytest.raises(HomeAssistantError) as err:
        await coordinator.async_execute_command("car-1", send_command)

    assert "did not accept the command" in str(err.value)
    assert "may not have woken up" in str(err.value)
    assert err.value.translation_key == "command_asleep"
    assert isinstance(err.value.__cause__, DeepalAPIError)
    assert err.value.__cause__.code == "APP_1_1_05_001"


@pytest.mark.asyncio
async def test_other_command_rejections_keep_the_api_error():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)

    async def send_command() -> str:
        raise DeepalAPIError(
            "API Error: COMMON_1_1_01_008", code="COMMON_1_1_01_008"
        )

    with pytest.raises(DeepalAPIError) as err:
        await coordinator.async_execute_command("car-1", send_command)

    assert err.value.code == "COMMON_1_1_01_008"


@pytest.mark.asyncio
async def test_unconfirmed_optimistic_value_expires_instead_of_freezing():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client, data={"car-1": VehicleCondition(car_id="car-1", vin="")})

    current = coordinator.data["car-1"]
    before = current.model_dump()
    after = current.model_copy(deep=True)
    after.climate.power_on = True
    coordinator._register_optimistic_hold("car-1", before, after.model_dump())

    shown = coordinator._apply_optimistic_hold(
        "car-1", VehicleCondition(car_id="car-1", vin="", last_updated_timestamp=2000)
    )
    assert shown.climate.power_on is True
    coordinator.async_set_updated_data({"car-1": shown})
    _expire_optimistic_holds(coordinator)

    fetched = VehicleCondition(car_id="car-1", vin="", last_updated_timestamp=3000)
    merged = coordinator._merge_condition("car-1", fetched)
    assert merged.climate.power_on is None
    applied = coordinator._apply_optimistic_hold("car-1", merged)
    assert applied.climate.power_on is None
    assert "car-1" not in coordinator._optimistic_holds
    coordinator.async_set_updated_data({"car-1": applied})

    reported = VehicleCondition(
        car_id="car-1",
        vin="",
        climate=ClimateCondition(power_on=False),
        last_updated_timestamp=4000,
    )
    merged = coordinator._merge_condition("car-1", reported)
    applied = coordinator._apply_optimistic_hold("car-1", merged)
    assert applied.climate.power_on is False
    coordinator.async_set_updated_data({"car-1": applied})

    silent = VehicleCondition(car_id="car-1", vin="", last_updated_timestamp=5000)
    merged = coordinator._merge_condition("car-1", silent)
    assert merged.climate.power_on is False
    assert "car-1" not in coordinator._optimistic_pending


@pytest.mark.asyncio
async def test_unconfirmed_optimistic_seat_level_expires_without_retention():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client, data={"car-1": VehicleCondition(car_id="car-1", vin="")})

    current = coordinator.data["car-1"]
    before = current.model_dump()
    after = current.model_copy(deep=True)
    after.seats.front_left.ventilation_level = 2
    coordinator._register_optimistic_hold("car-1", before, after.model_dump())

    shown = coordinator._apply_optimistic_hold(
        "car-1", VehicleCondition(car_id="car-1", vin="", last_updated_timestamp=2000)
    )
    assert shown.seats.front_left.ventilation_level == 2
    coordinator.async_set_updated_data({"car-1": shown})
    _expire_optimistic_holds(coordinator)

    fetched = VehicleCondition(car_id="car-1", vin="", last_updated_timestamp=3000)
    merged = coordinator._merge_condition("car-1", fetched)
    applied = coordinator._apply_optimistic_hold("car-1", merged)
    assert applied.seats.front_left.ventilation_level is None


@pytest.mark.asyncio
async def test_failed_command_clears_unconfirmed_marks():
    client = _FakeIntlClient([])
    current = _current_condition()
    coordinator, _ = _coordinator(client, data={"car-1": current})

    before = current.model_dump()
    after = current.model_copy(deep=True)
    after.climate.power_on = True
    coordinator._register_optimistic_hold("car-1", before, after.model_dump())
    assert coordinator._optimistic_pending["car-1"]

    coordinator._restore_condition("car-1", current)

    assert "car-1" not in coordinator._optimistic_holds
    assert "car-1" not in coordinator._optimistic_pending


@pytest.mark.asyncio
async def test_location_retention_keeps_the_last_known_position():
    client = _FakeIntlClient([])
    current = VehicleCondition(
        car_id="car-1", vin="", latitude=41.65, longitude=-0.89
    )
    coordinator, _ = _coordinator(client, data={"car-1": current})

    silent = VehicleCondition(car_id="car-1", vin="", last_updated_timestamp=2000)
    merged = coordinator._merge_condition("car-1", silent)

    assert merged.latitude == 41.65
    assert merged.longitude == -0.89

    reported = VehicleCondition(
        car_id="car-1",
        vin="",
        latitude=40.0,
        longitude=-3.0,
        last_updated_timestamp=3000,
    )
    merged = coordinator._merge_condition("car-1", reported)

    assert merged.latitude == 40.0
    assert merged.longitude == -3.0


@pytest.mark.asyncio
async def test_warning_lights_retain_the_last_known_values():
    client = _FakeIntlClient([])
    current = VehicleCondition(
        car_id="car-1",
        vin="",
        warnings={"power_limit": True, "abs": False},
    )
    coordinator, _ = _coordinator(client, data={"car-1": current})

    silent = VehicleCondition(car_id="car-1", vin="", last_updated_timestamp=2000)
    merged = coordinator._merge_condition("car-1", silent)

    assert merged.warnings.power_limit is True
    assert merged.warnings.abs is False

    reported = VehicleCondition(
        car_id="car-1",
        vin="",
        warnings={"power_limit": False},
        last_updated_timestamp=3000,
    )
    merged = coordinator._merge_condition("car-1", reported)

    assert merged.warnings.power_limit is False
    assert merged.warnings.abs is False

    first_poll = _coordinator(_FakeIntlClient([]))
    merged = first_poll[0]._merge_condition(
        "car-1", VehicleCondition(car_id="car-1", vin="")
    )
    assert merged.warnings.power_limit is None
