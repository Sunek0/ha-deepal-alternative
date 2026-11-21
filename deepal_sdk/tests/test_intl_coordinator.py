"""Tests for the Home Assistant coordinator command flow."""

import asyncio
import inspect
import math
import time
from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest

pytest.importorskip("homeassistant")

from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.deepal.charging import ChargingSessionManager
from custom_components.deepal.const import (
    CONF_ACCESS_TOKEN,
    CONF_CAC_TOKEN,
    CONF_ENABLE_LOCATION,
    CONF_REFRESH_TOKEN,
)
from custom_components.deepal.coordinator import (
    _S05_WARNING_SETTLE_SECONDS,
    DeepalDataUpdateCoordinator,
    WakeResult,
)
from custom_components.deepal.deepal.models import TireStatus, TiresCondition
from custom_components.deepal.deepal import (
    AuthToken,
    BatteryCondition,
    ClimateCondition,
    CommandResult,
    CommandResultStatus,
    DeepalAPIError,
    DeepalAuthError,
    DeepalClient,
    DeepalCommandAuthError,
    DeepalCommandNotReady,
    DeepalConnectionError,
    DeepalIntlClient,
    DeepalMqttAuthRejected,
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
        self.condition_model_codes: list[str | None] = []
        self.capabilities_error: Exception | None = None
        self.refresh_calls = 0
        self.refresh_error: Exception | None = None
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
        if self.refresh_error is not None:
            raise self.refresh_error
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
        self,
        vehicle_id: str,
        vin: str | None = None,
        *,
        model_code: str | None = None,
    ) -> VehicleCondition:
        self.events.append("condition")
        self.condition_model_codes.append(model_code)
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
    coordinator._last_ca_refresh_at = None
    coordinator.data = data or {}
    coordinator.update_interval = timedelta(seconds=120)
    coordinator._command_locks = {}
    coordinator._command_cooldowns = {}
    coordinator._optimistic_holds = {}
    coordinator._optimistic_pending = {}
    coordinator._last_steering_wheel = {}
    coordinator._ready_since = {}
    coordinator._last_app_report_ts = {}
    coordinator._tire_zero_since = {}
    coordinator._tire_guard_condition = {}
    coordinator._background_tasks = []
    coordinator._last_wake_at = {}
    coordinator._last_wake_result = {}
    coordinator._wake_locks = {}
    coordinator._restored = {}
    coordinator._restored_loaded = False
    coordinator._store = _RecordingStore()
    coordinator.wake_enabled = True
    coordinator._wake_poll_interval = 0.01
    coordinator._wake_report_timeout = 0.1
    coordinator._mqtt_attempts = {}
    coordinator.charging = None
    coordinator._charging_read_task = None
    coordinator._charging_read_stop = None
    coordinator._charging_read_interval = 600.0
    coordinator.live_session_enabled = True
    coordinator._mqtt_session = None
    coordinator._mqtt_session_state = None
    coordinator._live_session_stopping = False
    coordinator._vehicle_generation = {}
    coordinator._push_pending = {}
    coordinator._push_tasks = {}
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


@pytest.mark.parametrize(
    "error",
    [
        DeepalCommandAuthError("Control-code check did not return an rcToken."),
        DeepalCommandNotReady("Login private key is required to sign commands."),
    ],
)
@pytest.mark.asyncio
async def test_command_auth_error_is_not_replayed_as_session_expiry(error):
    client = _FakeIntlClient([_success_result()])
    coordinator, _ = _coordinator(client, data={"car-1": _current_condition()})
    attempts = {"count": 0}

    async def send_command() -> str:
        attempts["count"] += 1
        raise error

    with pytest.raises(type(error)):
        await coordinator.async_execute_command(
            "car-1",
            send_command,
            optimistic_update=_optimistic_power_on(),
            timeout=1.0,
            interval=0.01,
        )

    assert attempts["count"] == 1
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
async def test_app_comfort_overlay_copies_the_charge_plan():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    vehicle = Vehicle(car_id="car-1", vin="VIN", protocol_type="MQTT")
    coordinator.vehicles = [vehicle]

    app_condition = VehicleCondition(car_id="car-1", vin="VIN")
    app_condition.battery.charge_plan_id = "99"
    app_condition.battery.charge_plan_valid = True
    app_condition.battery.charge_schedule_enabled = True
    app_condition.battery.charge_schedule_start = "0000"
    app_condition.battery.charge_schedule_end = "0100"
    plans = [
        {
            "planId": 99,
            "isValid": 1,
            "startSwitch": 1,
            "endSwitch": 1,
            "startTime": "0000",
            "endTime": "0100",
        }
    ]
    app_condition.battery.charge_plans = plans
    app_condition.raw_data = {"charge": {"chargePlanList": plans}}
    client.http_condition = app_condition

    merged = await coordinator._overlay_app_comfort(
        vehicle, VehicleCondition(car_id="car-1", vin="VIN")
    )

    assert merged.battery.charge_plan_id == "99"
    assert merged.battery.charge_plans == plans
    assert merged.battery.charge_plan_valid is True
    assert merged.battery.charge_schedule_enabled is True
    assert merged.battery.charge_schedule_start == "0000"
    assert merged.battery.charge_schedule_end == "0100"


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
async def test_s05_command_poll_does_not_publish_the_glitched_bits():
    client = _FakeIntlClient(
        [CommandResult(status=CommandResultStatus.SUCCESS, code=0, raw={})]
    )
    previous = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        warnings={"abs": False, "airbag": False, "eps": False},
        last_updated_timestamp=1000,
    )
    coordinator, _ = _coordinator(client, data={"car-1": previous})
    coordinator.vehicles = [
        Vehicle(
            car_id="car-1",
            vin="VIN",
            protocol_type="MQTT",
            model_code="SC6464AAKBEV",
        )
    ]
    mqtt_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        warnings={"abs": True, "airbag": True, "eps": True},
        last_updated_timestamp=2000,
    )
    client.mqtt_condition = mqtt_condition

    await coordinator._async_poll_command("car-1", "cmd-1", 1000, 1.0, 0.01)

    condition = coordinator.data["car-1"]
    assert condition.warnings.abs is False
    assert condition.warnings.airbag is False
    assert condition.warnings.eps is False


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
    mqtt_condition.mqtt_raw_data = {"steeringWheelHeating": 2}

    merged = await coordinator._overlay_app_comfort(vehicle, mqtt_condition)

    # The corrected MQTT steering enum (2 = on) wins over a stale REST 0.
    assert merged.climate.steering_wheel_heater_on is True
    # Defrost still comes from the app condition; its MQTT field is unreliable.
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
async def test_app_condition_overlay_skips_the_s05_cable_fallback():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)

    for model_code, series_code in (
        ("SC6464AAKBEV", None),
        ("SC6460AAAA7HEV", None),
        (None, "C857-EU"),
    ):
        vehicle = Vehicle(
            car_id="car-1",
            vin="VIN",
            protocol_type="MQTT",
            model_code=model_code,
            series_code=series_code,
        )
        coordinator.vehicles = [vehicle]
        app_condition, mqtt_condition = _charge_overlay_pair()
        client.http_condition = app_condition

        merged = await coordinator._overlay_app_comfort(vehicle, mqtt_condition)

        assert merged.battery.charger_connected is False
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


def test_merge_retains_odometer_on_a_precision_dip():
    client = _FakeIntlClient([])
    previous = VehicleCondition(
        car_id="car-1", vin="VIN", last_updated_timestamp=2000
    )
    previous.total_odometer_km = 1500.9
    coordinator, _ = _coordinator(client, data={"car-1": previous})

    fetched = VehicleCondition(
        car_id="car-1", vin="VIN", last_updated_timestamp=2001
    )
    fetched.total_odometer_km = 1500.0

    merged = coordinator._merge_condition("car-1", fetched)

    assert merged.total_odometer_km == 1500.9


def test_merge_retains_odometer_when_the_report_omits_it():
    client = _FakeIntlClient([])
    previous = VehicleCondition(
        car_id="car-1", vin="VIN", last_updated_timestamp=2000
    )
    previous.total_odometer_km = 1500.9
    coordinator, _ = _coordinator(client, data={"car-1": previous})

    fetched = VehicleCondition(
        car_id="car-1", vin="VIN", last_updated_timestamp=2001
    )

    merged = coordinator._merge_condition("car-1", fetched)

    assert merged.total_odometer_km == 1500.9


def test_merge_ignores_a_lower_odometer_from_a_stale_report():
    client = _FakeIntlClient([])
    previous = VehicleCondition(
        car_id="car-1", vin="VIN", last_updated_timestamp=2001
    )
    previous.total_odometer_km = 1500.9
    coordinator, _ = _coordinator(client, data={"car-1": previous})

    fetched = VehicleCondition(
        car_id="car-1", vin="VIN", last_updated_timestamp=2000
    )
    fetched.total_odometer_km = 1200.0

    merged = coordinator._merge_condition("car-1", fetched)

    assert merged.total_odometer_km == 1500.9


def test_merge_accepts_a_real_odometer_reset():
    client = _FakeIntlClient([])
    previous = VehicleCondition(
        car_id="car-1", vin="VIN", last_updated_timestamp=2000
    )
    previous.total_odometer_km = 1500.9
    coordinator, _ = _coordinator(client, data={"car-1": previous})

    fetched = VehicleCondition(
        car_id="car-1", vin="VIN", last_updated_timestamp=2001
    )
    fetched.total_odometer_km = 0.0

    merged = coordinator._merge_condition("car-1", fetched)

    assert merged.total_odometer_km == 0.0


def test_merge_accepts_a_higher_odometer():
    client = _FakeIntlClient([])
    previous = VehicleCondition(
        car_id="car-1", vin="VIN", last_updated_timestamp=2000
    )
    previous.total_odometer_km = 1500.9
    coordinator, _ = _coordinator(client, data={"car-1": previous})

    fetched = VehicleCondition(
        car_id="car-1", vin="VIN", last_updated_timestamp=2001
    )
    fetched.total_odometer_km = 1501.0

    merged = coordinator._merge_condition("car-1", fetched)

    assert merged.total_odometer_km == 1501.0


def test_merge_accepts_a_higher_odometer_from_an_older_report():
    client = _FakeIntlClient([])
    previous = VehicleCondition(
        car_id="car-1", vin="VIN", last_updated_timestamp=2001
    )
    previous.total_odometer_km = 1500.9
    coordinator, _ = _coordinator(client, data={"car-1": previous})

    fetched = VehicleCondition(
        car_id="car-1", vin="VIN", last_updated_timestamp=2000
    )
    fetched.total_odometer_km = 1600.0

    merged = coordinator._merge_condition("car-1", fetched)

    assert merged.total_odometer_km == 1600.0


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
            qos=1,
            keepalive=60.0,
            connect_timeout=30.0,
            server_keep_alive=45,
            maximum_qos=0,
            effective_qos=0,
            effective_keepalive=45.0,
            logout_sent=True,
            logout_error=None,
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
    assert attempt["qos"] == 1
    assert attempt["keepalive"] == 60.0
    assert attempt["connect_timeout"] == 30.0
    assert attempt["server_keep_alive"] == 45
    assert attempt["maximum_qos"] == 0
    assert attempt["effective_qos"] == 0
    assert attempt["effective_keepalive"] == 45.0
    assert attempt["logout_sent"] is True
    assert attempt["logout_error"] is None


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
async def test_charging_read_uses_the_sda_condition_without_inquiry():
    class _SdaClient:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def get_vehicle_condition(
            self, vehicle_id, vin=None, *, model_code=None
        ):
            self.calls.append(vehicle_id)
            return VehicleCondition(
                car_id=vehicle_id,
                vin=vin or "",
                last_updated_timestamp=1000,
            )

    client = _SdaClient()
    coordinator, _ = _coordinator(_FakeIntlClient([]))
    coordinator.client = client
    coordinator.vehicles = []

    await coordinator._async_read_charging_vehicle("car-1")

    assert client.calls == ["car-1"]
    assert coordinator.data["car-1"].car_id == "car-1"


@pytest.mark.asyncio
async def test_sda_condition_fetch_uses_the_real_client_without_model_code():
    """An SDA poll must reach the real client, whose signature has no model_code."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {"BatterySoc": 82, "CdcTotMilg": "1234"},
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as http_client:
        client = DeepalClient(
            access_token="test_token_123", httpx_client=http_client
        )
        coordinator, _ = _coordinator(client)
        coordinator.vehicles = [
            Vehicle(car_id="car-1", vin="VIN-PLACEHOLDER-1", model_code="C857")
        ]

        condition = await coordinator._async_fetch_condition("car-1")

    assert condition.car_id == "car-1"
    assert condition.battery.soc_percentage == 82
    assert condition.condition_source == "rest"
    assert seen[0].url.params["carId"] == "car-1"


@pytest.mark.asyncio
async def test_sda_condition_fetch_never_forwards_the_model_code():
    """The coordinator keeps model_code for the international client only."""

    class _RecordingSdaClient(DeepalClient):
        def __init__(self) -> None:
            super().__init__(access_token="test_token_123")
            self.calls: list[tuple[str, str | None]] = []

        async def get_vehicle_condition(
            self, car_id: str, vin: str | None = None
        ) -> VehicleCondition:
            self.calls.append((car_id, vin))
            return VehicleCondition(car_id=car_id, vin=vin or "")

    client = _RecordingSdaClient()
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [
        Vehicle(car_id="car-1", vin="VIN-PLACEHOLDER-1", model_code="C857")
    ]

    await coordinator._async_fetch_condition("car-1")

    assert client.calls == [("car-1", "VIN-PLACEHOLDER-1")]
    await client.close()


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
async def test_one_vehicle_failure_does_not_fail_the_others():
    client = _FakeIntlClient([])
    previous = _current_condition("car-2", 900)
    coordinator, _ = _coordinator(client, data={"car-2": previous})
    coordinator.vehicles = [
        _mqtt_vehicle("car-1", protocol=None),
        _mqtt_vehicle("car-2", protocol=None),
    ]
    coordinator._capabilities = {}
    original = client.get_vehicle_condition

    async def flaky(vehicle_id, vin=None, *, model_code=None):
        if vehicle_id == "car-2":
            raise DeepalConnectionError("offline")
        return await original(vehicle_id, vin=vin, model_code=model_code)

    client.get_vehicle_condition = flaky
    client.condition_timestamps = [2000]

    data = await coordinator._async_update_data()

    assert data["car-1"].last_updated_timestamp == 2000
    assert data["car-2"] is previous


@pytest.mark.asyncio
async def test_ca_refresh_is_throttled_to_once_per_hour():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    rejection = DeepalAPIError("token rejected", code="APIGW_-1_7_01_004")

    assert await coordinator._async_refresh_session_for_mqtt(rejection) is True
    assert await coordinator._async_refresh_session_for_mqtt(rejection) is False

    assert client.refresh_calls == 1


@pytest.mark.asyncio
async def test_ca_refresh_retries_after_the_hour_window():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    rejection = DeepalAPIError("token rejected", code="APIGW_-1_7_01_004")

    assert await coordinator._async_refresh_session_for_mqtt(rejection) is True
    coordinator._last_ca_refresh_at -= 3601
    assert await coordinator._async_refresh_session_for_mqtt(rejection) is True

    assert client.refresh_calls == 2


@pytest.mark.asyncio
async def test_auth_refresh_is_not_capped_by_the_ca_window():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [_mqtt_vehicle(protocol=None)]
    coordinator._capabilities = {}
    await coordinator._async_refresh_session_for_mqtt(
        DeepalAPIError("token rejected", code="APIGW_-1_7_01_004")
    )
    client.condition_error = DeepalAuthError("expired")

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()

    assert client.refresh_calls == 2


@pytest.mark.asyncio
async def test_ca_refresh_failure_occupies_the_hour_window():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    client.refresh_error = DeepalConnectionError("offline")
    rejection = DeepalAPIError("token rejected", code="APIGW_-1_7_01_004")

    assert await coordinator._async_refresh_session_for_mqtt(rejection) is False
    assert await coordinator._async_refresh_session_for_mqtt(rejection) is False

    assert client.refresh_calls == 1


@pytest.mark.asyncio
async def test_poll_fails_when_every_vehicle_fails_without_previous():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [_mqtt_vehicle(protocol=None)]
    coordinator._capabilities = {}

    async def failing(vehicle_id, vin=None, *, model_code=None):
        raise DeepalConnectionError("offline")

    client.get_vehicle_condition = failing

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_mqtt_connection_error_falls_back_to_rest():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [_mqtt_vehicle()]
    coordinator._capabilities = {}
    client.mqtt_condition_errors = [DeepalConnectionError("broker down")]

    data = await coordinator._async_update_data()

    assert data["car-1"].condition_source == "rest"
    assert client.events[0] == "mqtt_condition"
    assert "condition" in client.events


@pytest.mark.asyncio
async def test_mqtt_session_error_falls_back_to_rest():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [_mqtt_vehicle()]
    coordinator._capabilities = {}
    client.mqtt_condition_errors = [DeepalAuthError("expired")]

    data = await coordinator._async_update_data()

    assert data["car-1"].condition_source == "rest"
    assert client.refresh_calls == 0


@pytest.mark.asyncio
async def test_mqtt_broker_auth_rejection_falls_back_to_rest():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [_mqtt_vehicle()]
    coordinator._capabilities = {}
    client.mqtt_condition_errors = [
        DeepalMqttAuthRejected("broker rejected", reason_code=0x87)
    ]

    data = await coordinator._async_update_data()

    assert data["car-1"].condition_source == "rest"
    assert client.refresh_calls == 0


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


@pytest.mark.asyncio
async def test_retry_after_auth_refresh_maps_a_transient_error_to_update_failed():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [_mqtt_vehicle(protocol=None)]
    coordinator._capabilities = {}
    calls = {"count": 0}

    async def flaky_condition(vehicle_id, vin=None, *, model_code=None):
        calls["count"] += 1
        if calls["count"] == 1:
            raise DeepalAuthError("Authentication failed: APP_1_1_02_004")
        raise DeepalAPIError("server error")

    client.get_vehicle_condition = flaky_condition

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    assert client.refresh_calls == 1
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_retry_after_auth_refresh_keeps_auth_errors_as_reauth():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [_mqtt_vehicle(protocol=None)]
    coordinator._capabilities = {}
    calls = {"count": 0}

    async def flaky_condition(vehicle_id, vin=None, *, model_code=None):
        calls["count"] += 1
        raise DeepalAuthError("Authentication failed: APP_1_1_02_004")

    client.get_vehicle_condition = flaky_condition

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()

    assert client.refresh_calls == 1
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_rejected_refresh_maps_to_reauth():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [_mqtt_vehicle(protocol=None)]
    coordinator._capabilities = {}
    client.condition_error = DeepalAuthError("expired")
    client.refresh_error = DeepalAuthError("refresh rejected")

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()

    assert client.refresh_calls == 1


@pytest.mark.asyncio
async def test_refresh_transport_error_maps_to_update_failed():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [_mqtt_vehicle(protocol=None)]
    coordinator._capabilities = {}
    client.condition_error = DeepalAuthError("expired")
    client.refresh_error = DeepalConnectionError("offline")

    with pytest.raises(UpdateFailed) as err:
        await coordinator._async_update_data()

    assert err.value.retry_after is None
    assert client.refresh_calls == 1


@pytest.mark.asyncio
async def test_proactive_refresh_transport_error_maps_to_update_failed():
    client = _FakeIntlClient([])
    client.access_token_expires_soon = lambda: True
    client.refresh_error = DeepalConnectionError("offline")
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [_mqtt_vehicle(protocol=None)]
    coordinator._capabilities = {}

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    assert client.refresh_calls == 1
    assert client.events == []


@pytest.mark.asyncio
async def test_ca_refresh_transport_error_falls_back_to_rest():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [_mqtt_vehicle()]
    coordinator._capabilities = {}
    client.mqtt_condition_errors = [
        DeepalAPIError("token rejected", code="APIGW_-1_7_01_004")
    ]
    client.refresh_error = DeepalConnectionError("offline")

    data = await coordinator._async_update_data()

    assert client.refresh_calls == 1
    assert data["car-1"].condition_source == "rest"


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


@pytest.mark.asyncio
async def test_retained_s05_charge_state_starts_no_session_or_read_loop():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [
        Vehicle(car_id="car-1", vin="VIN-PLACEHOLDER-1", series_name="S05")
    ]
    retained = VehicleCondition(car_id="car-1", vin="VIN-PLACEHOLDER-1")
    retained.battery.charging_status = "5"  # retained from the previous report
    retained.mqtt_raw_data = {"BattSoc": 50}  # partial payload: no ChrgSts
    retained.condition_source = "legacy-mqtt"
    coordinator.data = {"car-1": retained}
    store = _RecordingStore()
    coordinator.charging = ChargingSessionManager(store)

    coordinator._track_charging(coordinator.data)
    coordinator._sync_charging_read(coordinator.data)

    assert coordinator.charging.attributes("car-1") == {}
    assert store.saved == []
    assert coordinator._charging_read_task is None


def _charging_condition(car_id: str, charging: bool = True) -> VehicleCondition:
    condition = VehicleCondition(car_id=car_id, vin="VIN")
    condition.battery.charging_status = "3" if charging else "0"
    return condition


@pytest.mark.asyncio
async def test_charging_read_of_an_mqtt_vehicle_does_not_wake_it():
    client = _FakeIntlClient([])
    coordinator, updates = _coordinator(client)
    coordinator.vehicles = [_mqtt_vehicle(protocol="MQTT")]
    parked = _charging_condition("car-2", charging=False)
    coordinator.data = {"car-1": _charging_condition("car-1"), "car-2": parked}
    fresh = _charging_condition("car-1")
    fresh.last_updated_timestamp = 2000
    client.mqtt_condition = fresh
    client.http_condition = fresh

    await coordinator._async_read_charging_vehicle("car-1")

    # The live session already streams the charge telemetry: no wake, and no
    # REST inquiry either, only the live condition request plus the overlay.
    assert client.wake_calls == 0
    assert client.events.count("mqtt_condition") == 1
    assert "condition" in client.events
    assert updates[-1]["car-1"].last_updated_timestamp == 2000
    assert updates[-1]["car-2"] is parked


@pytest.mark.asyncio
async def test_charging_read_of_a_rest_vehicle_uses_the_refresh_path():
    client = _FakeIntlClient([])
    coordinator, updates = _coordinator(client)
    coordinator.vehicles = [_mqtt_vehicle(car_id="car-1", protocol=None)]
    coordinator.data = {"car-1": _charging_condition("car-1")}
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
async def test_applying_a_charging_condition_starts_the_read_loop():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator._charging_read_interval = 600.0
    condition = _charging_condition("car-1")

    await coordinator._async_apply_condition("car-1", condition)

    assert coordinator._charging_read_task is not None
    coordinator._sync_charging_read({})
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_a_read_from_inside_the_loop_keeps_its_task():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    stop = asyncio.Event()
    coordinator._charging_read_stop = stop
    coordinator._charging_read_task = asyncio.current_task()
    sentinel = coordinator._charging_read_task

    await coordinator._async_apply_condition(
        "car-1", _charging_condition("car-1")
    )

    # The loop publishes through the same path: it must not replace its own
    # task or stop itself while the session is still open.
    assert coordinator._charging_read_task is sentinel
    assert not stop.is_set()


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
        warnings={
            "power_limit": True,
            "abs": False,
            "airbag": True,
            "coolant_temperature": False,
        },
    )
    coordinator, _ = _coordinator(client, data={"car-1": current})

    silent = VehicleCondition(car_id="car-1", vin="", last_updated_timestamp=2000)
    merged = coordinator._merge_condition("car-1", silent)

    assert merged.warnings.power_limit is True
    assert merged.warnings.abs is False
    assert merged.warnings.airbag is True
    assert merged.warnings.coolant_temperature is False

    reported = VehicleCondition(
        car_id="car-1",
        vin="",
        warnings={"power_limit": False},
        last_updated_timestamp=3000,
    )
    merged = coordinator._merge_condition("car-1", reported)

    assert merged.warnings.power_limit is False
    assert merged.warnings.abs is False
    assert merged.warnings.airbag is True
    assert merged.warnings.coolant_temperature is False

    first_poll = _coordinator(_FakeIntlClient([]))
    merged = first_poll[0]._merge_condition(
        "car-1", VehicleCondition(car_id="car-1", vin="")
    )
    assert merged.warnings.power_limit is None


@pytest.mark.asyncio
async def test_s05_subsystem_warnings_survive_an_asleep_poll():
    client = _FakeIntlClient([])
    current = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        warnings={"abs": False, "airbag": False, "eps": False},
        last_updated_timestamp=1000,
    )
    coordinator, _ = _coordinator(client, data={"car-1": current})
    vehicle = Vehicle(
        car_id="car-1",
        vin="VIN",
        protocol_type="MQTT",
        model_code="SC6464AAKBEV",
    )
    coordinator.vehicles = [vehicle]
    coordinator._capabilities = {}

    # The MQTT bits glitch to 1 on a healthy car, so the overlay must not use
    # them as a fallback while the car is asleep.
    client.mqtt_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=0,
        warnings={"abs": True, "airbag": True, "eps": True},
        last_updated_timestamp=2000,
    )
    client.http_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=0,
        raw_data={"vehicleStatus": {"powerStatus": 0}},
        last_updated_timestamp=2000,
    )

    condition = (await coordinator._async_fetch())["car-1"]

    assert condition.warnings.abs is False
    assert condition.warnings.airbag is False
    assert condition.warnings.eps is False


@pytest.mark.asyncio
async def test_s05_subsystem_warnings_are_replaced_when_ready_again():
    client = _FakeIntlClient([])
    current = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        warnings={"abs": False, "airbag": False, "eps": False},
        last_updated_timestamp=1000,
    )
    coordinator, _ = _coordinator(client, data={"car-1": current})
    vehicle = Vehicle(
        car_id="car-1",
        vin="VIN",
        protocol_type="MQTT",
        model_code="SC6464AAKBEV",
    )
    coordinator.vehicles = [vehicle]
    coordinator._capabilities = {}
    # The car has already been ready for longer than the bulb check.
    coordinator._ready_since = {"car-1": time.monotonic() - 120}

    client.mqtt_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        last_updated_timestamp=2000,
    )
    client.http_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        raw_data={
            "vehicleStatus": {
                "powerStatus": 2,
                "absAntiLockBrakingSysStatus": 1,
                "airBagSysStatus": 1,
                "powerSteeringSysStatus": 1,
            }
        },
        last_updated_timestamp=2000,
    )

    condition = (await coordinator._async_fetch())["car-1"]

    assert condition.warnings.abs is True
    assert condition.warnings.airbag is True
    assert condition.warnings.eps is True


def test_s05_ready_window_opens_and_closes():
    coordinator, _ = _coordinator(_FakeIntlClient([]))
    ready = VehicleCondition(car_id="car-1", vin="", power_status=2)
    asleep = VehicleCondition(car_id="car-1", vin="", power_status=0)

    coordinator._update_ready_window("car-1", ready)
    assert "car-1" in coordinator._ready_since
    assert coordinator._ready_is_established("car-1", ready) is False

    # Still inside the dashboard bulb-check window.
    coordinator._ready_since["car-1"] = (
        time.monotonic() - (_S05_WARNING_SETTLE_SECONDS - 1)
    )
    assert coordinator._ready_is_established("car-1", ready) is False

    coordinator._ready_since["car-1"] = (
        time.monotonic() - (_S05_WARNING_SETTLE_SECONDS + 1)
    )
    assert coordinator._ready_is_established("car-1", ready) is True

    coordinator._update_ready_window("car-1", asleep)
    assert "car-1" not in coordinator._ready_since
    assert coordinator._ready_is_established("car-1", ready) is False


@pytest.mark.asyncio
async def test_s05_update_data_opens_and_closes_the_ready_window():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    vehicle = Vehicle(
        car_id="car-1",
        vin="VIN",
        protocol_type="MQTT",
        model_code="SC6464AAKBEV",
    )
    coordinator.vehicles = [vehicle]
    coordinator._capabilities = {}

    client.mqtt_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        last_updated_timestamp=2000,
    )
    client.http_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        raw_data={"vehicleStatus": {"powerStatus": 2}},
        last_updated_timestamp=2000,
    )

    await coordinator._async_update_data()
    assert "car-1" in coordinator._ready_since
    assert coordinator._ready_is_established(
        "car-1", client.mqtt_condition
    ) is False

    coordinator._ready_since["car-1"] = time.monotonic() - 120
    assert coordinator._ready_is_established(
        "car-1", client.mqtt_condition
    ) is True

    client.mqtt_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=0,
        last_updated_timestamp=3000,
    )
    client.http_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=0,
        raw_data={"vehicleStatus": {"powerStatus": 0}},
        last_updated_timestamp=3000,
    )

    await coordinator._async_update_data()
    assert "car-1" not in coordinator._ready_since


@pytest.mark.asyncio
async def test_s05_update_data_gates_the_warning_value_on_the_ready_window():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    vehicle = Vehicle(
        car_id="car-1",
        vin="VIN",
        protocol_type="MQTT",
        model_code="SC6464AAKBEV",
    )
    coordinator.vehicles = [vehicle]
    coordinator._capabilities = {}

    client.mqtt_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        last_updated_timestamp=2000,
    )
    client.http_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        raw_data={
            "vehicleStatus": {
                "powerStatus": 2,
                "absAntiLockBrakingSysStatus": 1,
                "airBagSysStatus": 1,
                "powerSteeringSysStatus": 1,
            }
        },
        last_updated_timestamp=2000,
    )

    data = await coordinator._async_update_data()
    assert data["car-1"].warnings.abs is None
    assert data["car-1"].warnings.airbag is None
    assert data["car-1"].warnings.eps is None

    coordinator.data = data
    coordinator._ready_since["car-1"] = time.monotonic() - 120
    client.mqtt_condition.last_updated_timestamp = 3000
    client.http_condition.last_updated_timestamp = 3000

    data = await coordinator._async_update_data()
    assert data["car-1"].warnings.abs is True
    assert data["car-1"].warnings.airbag is True
    assert data["car-1"].warnings.eps is True


@pytest.mark.asyncio
async def test_s05_first_ready_report_after_wake_is_not_a_fault():
    client = _FakeIntlClient([])
    previous = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=0,
        warnings={"abs": False, "airbag": False, "eps": False},
        last_updated_timestamp=1000,
    )
    coordinator, _ = _coordinator(client, data={"car-1": previous})
    vehicle = Vehicle(
        car_id="car-1",
        vin="VIN",
        protocol_type="MQTT",
        model_code="SC6464AAKBEV",
    )
    coordinator.vehicles = [vehicle]
    coordinator._capabilities = {}

    client.mqtt_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        last_updated_timestamp=2000,
    )
    client.http_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        raw_data={
            "vehicleStatus": {
                "powerStatus": 2,
                "absAntiLockBrakingSysStatus": 1,
                "airBagSysStatus": 1,
                "powerSteeringSysStatus": 1,
            }
        },
        last_updated_timestamp=2000,
    )

    # The first ready report after the wake is the dashboard bulb check: the
    # non-zero registers must not be published as faults.
    condition = (await coordinator._async_fetch())["car-1"]
    assert condition.warnings.abs is False
    assert condition.warnings.airbag is False
    assert condition.warnings.eps is False
    assert coordinator._last_app_report_ts["car-1"] == 2000

    # Once the ready window is established and a new app report arrives, the
    # same registers are a confirmed fault.
    coordinator.data = {"car-1": condition}
    coordinator._ready_since["car-1"] = time.monotonic() - 120
    client.mqtt_condition.last_updated_timestamp = 3000
    client.http_condition.last_updated_timestamp = 3000

    condition = (await coordinator._async_fetch())["car-1"]
    assert condition.warnings.abs is True
    assert condition.warnings.airbag is True
    assert condition.warnings.eps is True


@pytest.mark.asyncio
async def test_s05_snapshot_fault_is_not_revived_on_the_first_asleep_poll():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator._restored = {
        "car-1": VehicleCondition(
            car_id="car-1",
            vin="VIN",
            power_status=2,
            warnings={"abs": True, "airbag": True, "eps": True},
            last_updated_timestamp=1000,
        )
    }
    vehicle = Vehicle(
        car_id="car-1",
        vin="VIN",
        protocol_type="MQTT",
        model_code="SC6464AAKBEV",
    )
    coordinator.vehicles = [vehicle]
    coordinator._capabilities = {}

    client.mqtt_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=0,
        last_updated_timestamp=2000,
    )
    client.http_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=0,
        raw_data={"vehicleStatus": {"powerStatus": 0}},
        last_updated_timestamp=2000,
    )

    condition = (await coordinator._async_fetch())["car-1"]

    assert condition.warnings.abs is None
    assert condition.warnings.airbag is None
    assert condition.warnings.eps is None


@pytest.mark.asyncio
async def test_s05_snapshot_fault_is_not_revived_on_the_first_ready_poll():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator._restored = {
        "car-1": VehicleCondition(
            car_id="car-1",
            vin="VIN",
            power_status=2,
            warnings={"abs": True, "airbag": True, "eps": True},
            last_updated_timestamp=1000,
        )
    }
    vehicle = Vehicle(
        car_id="car-1",
        vin="VIN",
        protocol_type="MQTT",
        model_code="SC6464AAKBEV",
    )
    coordinator.vehicles = [vehicle]
    coordinator._capabilities = {}

    client.mqtt_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        last_updated_timestamp=2000,
    )
    client.http_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        raw_data={
            "vehicleStatus": {
                "powerStatus": 2,
                "absAntiLockBrakingSysStatus": 1,
                "airBagSysStatus": 1,
                "powerSteeringSysStatus": 1,
            }
        },
        last_updated_timestamp=2000,
    )

    condition = (await coordinator._async_fetch())["car-1"]

    assert condition.warnings.abs is None
    assert condition.warnings.airbag is None
    assert condition.warnings.eps is None


@pytest.mark.asyncio
async def test_s05_healthy_snapshot_survives_the_first_ready_poll():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator._restored = {
        "car-1": VehicleCondition(
            car_id="car-1",
            vin="VIN",
            power_status=2,
            warnings={"abs": False, "airbag": False, "eps": False},
            last_updated_timestamp=1000,
        )
    }
    vehicle = Vehicle(
        car_id="car-1",
        vin="VIN",
        protocol_type="MQTT",
        model_code="SC6464AAKBEV",
    )
    coordinator.vehicles = [vehicle]
    coordinator._capabilities = {}

    client.mqtt_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        last_updated_timestamp=2000,
    )
    client.http_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        raw_data={
            "vehicleStatus": {
                "powerStatus": 2,
                "absAntiLockBrakingSysStatus": 1,
                "airBagSysStatus": 1,
                "powerSteeringSysStatus": 1,
            }
        },
        last_updated_timestamp=2000,
    )

    condition = (await coordinator._async_fetch())["car-1"]

    assert condition.warnings.abs is False
    assert condition.warnings.airbag is False
    assert condition.warnings.eps is False


@pytest.mark.asyncio
async def test_s05_confirmed_fault_is_dropped_when_the_car_sleeps():
    client = _FakeIntlClient([])
    previous = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        warnings={"abs": True, "airbag": True, "eps": True},
        last_updated_timestamp=1000,
    )
    coordinator, _ = _coordinator(client, data={"car-1": previous})
    vehicle = Vehicle(
        car_id="car-1",
        vin="VIN",
        protocol_type="MQTT",
        model_code="SC6464AAKBEV",
    )
    coordinator.vehicles = [vehicle]
    coordinator._capabilities = {}

    client.mqtt_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=0,
        last_updated_timestamp=2000,
    )
    client.http_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=0,
        raw_data={"vehicleStatus": {"powerStatus": 0}},
        last_updated_timestamp=2000,
    )

    condition = (await coordinator._async_fetch())["car-1"]

    assert condition.warnings.abs is None
    assert condition.warnings.airbag is None
    assert condition.warnings.eps is None


@pytest.mark.asyncio
async def test_s05_rest_only_vehicle_drops_a_fault_when_asleep():
    client = _FakeIntlClient([])
    previous = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        warnings={"abs": True, "airbag": True, "eps": True},
        last_updated_timestamp=1000,
    )
    coordinator, _ = _coordinator(client, data={"car-1": previous})
    vehicle = Vehicle(
        car_id="car-1",
        vin="VIN",
        protocol_type="REST",
        model_code="SC6464AAKBEV",
    )
    coordinator.vehicles = [vehicle]

    client.http_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=0,
        raw_data={"vehicleStatus": {"powerStatus": 0}},
        last_updated_timestamp=2000,
    )

    condition = await coordinator._async_fetch_condition("car-1")

    assert condition.warnings.abs is None
    assert condition.warnings.airbag is None
    assert condition.warnings.eps is None


@pytest.mark.asyncio
async def test_s05_healthy_register_clears_a_retained_fault_immediately():
    client = _FakeIntlClient([])
    previous = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        warnings={"abs": True, "airbag": True, "eps": True},
        last_updated_timestamp=1000,
    )
    coordinator, _ = _coordinator(client, data={"car-1": previous})
    vehicle = Vehicle(
        car_id="car-1",
        vin="VIN",
        protocol_type="MQTT",
        model_code="SC6464AAKBEV",
    )
    coordinator.vehicles = [vehicle]
    coordinator._capabilities = {}
    coordinator._ready_since = {"car-1": time.monotonic() - 120}

    client.mqtt_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        last_updated_timestamp=2000,
    )
    client.http_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        raw_data={
            "vehicleStatus": {
                "powerStatus": 2,
                "absAntiLockBrakingSysStatus": 0,
                "airBagSysStatus": 0,
                "powerSteeringSysStatus": 0,
            }
        },
        last_updated_timestamp=2000,
    )

    condition = (await coordinator._async_fetch())["car-1"]

    assert condition.warnings.abs is False
    assert condition.warnings.airbag is False
    assert condition.warnings.eps is False


@pytest.mark.asyncio
async def test_s05_confirmed_fault_survives_a_poll_without_registers():
    client = _FakeIntlClient([])
    previous = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        warnings={"abs": True, "airbag": True, "eps": True},
        last_updated_timestamp=1000,
    )
    coordinator, _ = _coordinator(client, data={"car-1": previous})
    vehicle = Vehicle(
        car_id="car-1",
        vin="VIN",
        protocol_type="MQTT",
        model_code="SC6464AAKBEV",
    )
    coordinator.vehicles = [vehicle]
    coordinator._capabilities = {}
    coordinator._ready_since = {"car-1": time.monotonic() - 120}

    client.mqtt_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        last_updated_timestamp=2000,
    )
    client.http_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        raw_data={"vehicleStatus": {"powerStatus": 2}},
        last_updated_timestamp=2000,
    )

    condition = (await coordinator._async_fetch())["car-1"]

    assert condition.warnings.abs is True
    assert condition.warnings.airbag is True
    assert condition.warnings.eps is True


def test_merge_rest_only_fields_keeps_a_confirmed_subsystem_fault():
    current = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        last_updated_timestamp=2000,
    )
    polled = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        warnings={"abs": True, "airbag": True, "eps": True},
        last_updated_timestamp=1000,
    )

    merged = DeepalDataUpdateCoordinator._merge_rest_only_fields(current, polled)

    assert merged.warnings.abs is True
    assert merged.warnings.airbag is True
    assert merged.warnings.eps is True

    # A poll that could not resolve the registers must not erase the push's
    # retained fault.
    current.warnings.airbag = True
    polled.warnings.airbag = None
    merged = DeepalDataUpdateCoordinator._merge_rest_only_fields(current, polled)
    assert merged.warnings.airbag is True


@pytest.mark.asyncio
async def test_s05_cached_rest_block_cannot_raise_a_new_fault():
    client = _FakeIntlClient([])
    previous = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        warnings={"abs": False, "airbag": False, "eps": False},
        last_updated_timestamp=1000,
    )
    coordinator, _ = _coordinator(client, data={"car-1": previous})
    vehicle = Vehicle(
        car_id="car-1",
        vin="VIN",
        protocol_type="MQTT",
        model_code="SC6464AAKBEV",
    )
    coordinator.vehicles = [vehicle]
    coordinator._capabilities = {}
    coordinator._ready_since = {"car-1": time.monotonic() - 120}
    # The app already returned this report on the previous poll.
    coordinator._last_app_report_ts = {"car-1": 2000}

    client.mqtt_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        last_updated_timestamp=2000,
    )
    client.http_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        raw_data={
            "vehicleStatus": {
                "powerStatus": 2,
                "absAntiLockBrakingSysStatus": 1,
                "airBagSysStatus": 1,
                "powerSteeringSysStatus": 1,
            }
        },
        last_updated_timestamp=2000,
    )

    condition = (await coordinator._async_fetch())["car-1"]

    assert condition.warnings.abs is False
    assert condition.warnings.airbag is False
    assert condition.warnings.eps is False


@pytest.mark.asyncio
async def test_s05_missing_app_timestamp_uses_the_ready_window():
    client = _FakeIntlClient([])
    previous = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        warnings={"abs": False, "airbag": False, "eps": False},
        last_updated_timestamp=1000,
    )
    coordinator, _ = _coordinator(client, data={"car-1": previous})
    vehicle = Vehicle(
        car_id="car-1",
        vin="VIN",
        protocol_type="MQTT",
        model_code="SC6464AAKBEV",
    )
    coordinator.vehicles = [vehicle]
    coordinator._capabilities = {}
    coordinator._ready_since = {"car-1": time.monotonic() - 120}

    client.mqtt_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        last_updated_timestamp=2000,
    )
    client.http_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        raw_data={
            "vehicleStatus": {
                "powerStatus": 2,
                "absAntiLockBrakingSysStatus": 1,
                "airBagSysStatus": 1,
                "powerSteeringSysStatus": 1,
            }
        },
        last_updated_timestamp=None,
    )

    condition = (await coordinator._async_fetch())["car-1"]

    assert condition.warnings.abs is True
    assert condition.warnings.airbag is True
    assert condition.warnings.eps is True


@pytest.mark.asyncio
async def test_s05_apply_condition_without_vehicle_guards_the_bits():
    client = _FakeIntlClient([])
    previous = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        warnings={"abs": False, "airbag": False, "eps": False},
        last_updated_timestamp=1000,
    )
    coordinator, _ = _coordinator(client, data={"car-1": previous})

    condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        warnings={"abs": True, "airbag": True, "eps": True},
        last_updated_timestamp=2000,
    )
    await coordinator._async_apply_condition("car-1", condition)

    published = coordinator.data["car-1"]
    assert published.warnings.abs is False
    assert published.warnings.airbag is False
    assert published.warnings.eps is False


@pytest.mark.asyncio
async def test_s05_live_push_does_not_publish_the_glitched_bits():
    client = _FakeIntlClient([])
    previous = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        warnings={"abs": False, "airbag": False, "eps": False},
        last_updated_timestamp=1000,
    )
    coordinator, updates = _coordinator(client, data={"car-1": previous})
    vehicle = Vehicle(
        car_id="car-1",
        vin="VIN",
        protocol_type="MQTT",
        model_code="SC6464AAKBEV",
    )
    coordinator.vehicles = [vehicle]

    push = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        warnings={"abs": True, "airbag": True, "eps": True},
        last_updated_timestamp=2000,
    )
    await coordinator._async_publish_push_condition("car-1", push)

    published = updates[-1]["car-1"]
    assert published.warnings.abs is False
    assert published.warnings.airbag is False
    assert published.warnings.eps is False


@pytest.mark.asyncio
async def test_s05_live_push_without_the_vehicle_list_does_not_publish_the_bits():
    client = _FakeIntlClient([])
    previous = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        warnings={"abs": False, "airbag": False, "eps": False},
        last_updated_timestamp=1000,
    )
    coordinator, updates = _coordinator(client, data={"car-1": previous})

    push = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        warnings={"abs": True, "airbag": True, "eps": True},
        last_updated_timestamp=2000,
    )
    await coordinator._async_publish_push_condition("car-1", push)

    published = updates[-1]["car-1"]
    assert published.warnings.abs is False
    assert published.warnings.airbag is False
    assert published.warnings.eps is False


@pytest.mark.asyncio
async def test_s05_live_push_keeps_an_established_fault():
    client = _FakeIntlClient([])
    previous = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        warnings={"abs": True, "airbag": True, "eps": True},
        last_updated_timestamp=1000,
    )
    coordinator, updates = _coordinator(client, data={"car-1": previous})
    vehicle = Vehicle(
        car_id="car-1",
        vin="VIN",
        protocol_type="MQTT",
        model_code="SC6464AAKBEV",
    )
    coordinator.vehicles = [vehicle]
    coordinator._ready_since = {"car-1": time.monotonic() - 120}

    push = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        last_updated_timestamp=2000,
    )
    await coordinator._async_publish_push_condition("car-1", push)

    published = updates[-1]["car-1"]
    assert published.warnings.abs is True
    assert published.warnings.airbag is True
    assert published.warnings.eps is True


@pytest.mark.asyncio
async def test_s05_subsystem_warnings_survive_the_first_asleep_poll_after_restart():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator._restored = {
        "car-1": VehicleCondition(
            car_id="car-1",
            vin="VIN",
            warnings={"abs": False, "airbag": False, "eps": False},
            last_updated_timestamp=1000,
        )
    }
    vehicle = Vehicle(
        car_id="car-1",
        vin="VIN",
        protocol_type="MQTT",
        model_code="SC6464AAKBEV",
    )
    coordinator.vehicles = [vehicle]
    coordinator._capabilities = {}

    client.mqtt_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=0,
        last_updated_timestamp=2000,
    )
    client.http_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=0,
        raw_data={"vehicleStatus": {"powerStatus": 0}},
        last_updated_timestamp=2000,
    )

    condition = (await coordinator._async_fetch())["car-1"]

    assert condition.warnings.abs is False
    assert condition.warnings.airbag is False
    assert condition.warnings.eps is False


@pytest.mark.asyncio
async def test_partial_first_poll_keeps_the_restored_state_of_failed_vehicles():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [
        Vehicle(car_id="car-1", vin="VIN-1"),
        Vehicle(car_id="car-2", vin="VIN-2"),
    ]
    coordinator._capabilities = {}
    coordinator._restored_loaded = True
    coordinator._restored = {
        "car-1": VehicleCondition(car_id="car-1", vin="VIN-1"),
        "car-2": VehicleCondition(car_id="car-2", vin="VIN-2"),
    }

    async def condition(vehicle_id, vin=None, *, model_code=None):
        if vehicle_id == "car-2":
            raise DeepalAPIError("boom")
        return VehicleCondition(
            car_id=vehicle_id, vin=vin or "", last_updated_timestamp=2000
        )

    client.get_vehicle_condition = condition

    await coordinator._async_update_data()

    assert set(coordinator._restored) == {"car-2"}


def test_snapshot_payload_excludes_location_when_the_option_is_off():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    condition = VehicleCondition(car_id="car-1", vin="VIN")
    condition.latitude = 37.5
    condition.longitude = 23.7
    coordinator.data = {"car-1": condition}

    payload = coordinator._snapshot_payload()["conditions"]["car-1"]

    assert "latitude" not in payload
    assert "longitude" not in payload


def test_snapshot_payload_keeps_location_when_the_option_is_on():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.entry.options = {CONF_ENABLE_LOCATION: True}
    condition = VehicleCondition(car_id="car-1", vin="VIN")
    condition.latitude = 37.5
    condition.longitude = 23.7
    coordinator.data = {"car-1": condition}

    payload = coordinator._snapshot_payload()["conditions"]["car-1"]

    assert payload["latitude"] == 37.5
    assert payload["longitude"] == 23.7


@pytest.mark.asyncio
async def test_s05_subsystem_warnings_survive_an_unavailable_app_condition():
    client = _FakeIntlClient([])
    current = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        warnings={"abs": False, "airbag": False, "eps": False},
        last_updated_timestamp=1000,
    )
    coordinator, _ = _coordinator(client, data={"car-1": current})
    vehicle = Vehicle(
        car_id="car-1",
        vin="VIN",
        protocol_type="MQTT",
        model_code="SC6464AAKBEV",
    )
    coordinator.vehicles = [vehicle]
    coordinator._capabilities = {}

    client.mqtt_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=0,
        warnings={"abs": True, "airbag": True, "eps": True},
        last_updated_timestamp=2000,
    )
    client.condition_error = DeepalAPIError("app condition unavailable")

    condition = (await coordinator._async_fetch())["car-1"]

    assert condition.warnings.abs is False
    assert condition.warnings.airbag is False
    assert condition.warnings.eps is False


@pytest.mark.asyncio
async def test_s05_subsystem_warnings_ignore_glitched_mqtt_bits_when_ready():
    client = _FakeIntlClient([])
    current = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        warnings={"abs": False, "airbag": False, "eps": False},
        last_updated_timestamp=1000,
    )
    coordinator, _ = _coordinator(client, data={"car-1": current})
    vehicle = Vehicle(
        car_id="car-1",
        vin="VIN",
        protocol_type="MQTT",
        model_code="SC6464AAKBEV",
    )
    coordinator.vehicles = [vehicle]
    coordinator._capabilities = {}

    # Ready, glitched MQTT bits, and an app report whose subsystem block does
    # not carry the registers: the retained REST value must win, not the bits.
    client.mqtt_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        warnings={"abs": True, "airbag": True, "eps": True},
        last_updated_timestamp=2000,
    )
    client.http_condition = VehicleCondition(
        car_id="car-1",
        vin="VIN",
        power_status=2,
        raw_data={"vehicleStatus": {"powerStatus": 2}},
        last_updated_timestamp=2000,
    )

    condition = (await coordinator._async_fetch())["car-1"]

    assert condition.warnings.abs is False
    assert condition.warnings.airbag is False
    assert condition.warnings.eps is False


@pytest.mark.asyncio
async def test_unreported_telemetry_groups_retain_the_last_known_values():
    client = _FakeIntlClient([])
    current = VehicleCondition(
        car_id="car-1",
        vin="",
        doors={"locked": False, "driver_door_open": True},
        windows={"front_left_open": True},
        lamps={"high_beam": True},
        tires={"front_left": {"alarm": True}},
        battery={"charger_connected": True},
    )
    coordinator, _ = _coordinator(client, data={"car-1": current})

    partial = VehicleCondition(
        car_id="car-1",
        vin="",
        mqtt_raw_data={"soc": 50},
        last_updated_timestamp=2000,
    )
    merged = coordinator._merge_condition("car-1", partial)

    assert merged.doors.locked is False
    assert merged.doors.driver_door_open is True
    assert merged.windows.front_left_open is True
    assert merged.lamps.high_beam is True
    assert merged.tires.front_left.alarm is True
    assert merged.battery.charger_connected is True

    reported = VehicleCondition(
        car_id="car-1",
        vin="",
        doors={"locked": True},
        mqtt_raw_data={"driverDoorLock": 0},
        last_updated_timestamp=3000,
    )
    merged = coordinator._merge_condition("car-1", reported)

    assert merged.doors.locked is True
    assert merged.doors.driver_door_open is False
    assert merged.windows.front_left_open is True


def test_expired_optimistic_field_keeps_the_rest_of_its_group():
    client = _FakeIntlClient([])
    current = VehicleCondition(
        car_id="car-1",
        vin="",
        doors={
            "locked": False,
            "trunk_open": True,
            "driver_door_open": True,
            "hood_open": True,
        },
    )
    coordinator, _ = _coordinator(client, data={"car-1": current})
    coordinator._optimistic_pending = {"car-1": {"doors.locked"}}

    partial = VehicleCondition(
        car_id="car-1",
        vin="",
        mqtt_raw_data={"soc": 50},
        last_updated_timestamp=2000,
    )
    merged = coordinator._merge_condition("car-1", partial)

    # The unconfirmed lock field expires to the parser default...
    assert merged.doors.locked is True
    # ...but the rest of the group keeps the last reported value.
    assert merged.doors.trunk_open is True
    assert merged.doors.driver_door_open is True
    assert merged.doors.hood_open is True


def test_expired_optimistic_charge_field_keeps_the_other_charger_flags():
    client = _FakeIntlClient([])
    current = VehicleCondition(
        car_id="car-1",
        vin="",
        battery={"charging_status": "5", "charger_connected": True},
    )
    coordinator, _ = _coordinator(client, data={"car-1": current})
    coordinator._optimistic_pending = {"car-1": {"battery.charging_status"}}

    partial = VehicleCondition(
        car_id="car-1",
        vin="",
        mqtt_raw_data={"soc": 50},
        last_updated_timestamp=2000,
    )
    merged = coordinator._merge_condition("car-1", partial)

    assert merged.battery.charging_status is None
    assert merged.battery.charger_connected is True


@pytest.mark.asyncio
async def test_apply_condition_merges_unreported_telemetry_groups():
    client = _FakeIntlClient([])
    current = VehicleCondition(
        car_id="car-1",
        vin="",
        doors={"locked": False},
    )
    coordinator, _ = _coordinator(client, data={"car-1": current})
    coordinator.vehicles = []
    partial = VehicleCondition(
        car_id="car-1",
        vin="",
        mqtt_raw_data={"soc": 40},
        last_updated_timestamp=2000,
    )

    await coordinator._async_apply_condition("car-1", partial)

    assert coordinator.data["car-1"].doors.locked is False


@pytest.mark.asyncio
async def test_rest_condition_fetch_passes_the_vehicle_model_code():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator.vehicles = [
        Vehicle(
            car_id="car-1",
            vin="VIN-PLACEHOLDER-1",
            protocol_type=None,
            model_code="SC6460AAAA7HEV",
        )
    ]
    coordinator._capabilities = {}

    await coordinator._async_fetch_condition("car-1")

    assert client.condition_model_codes == ["SC6460AAAA7HEV"]


# ---------------------------------------------------------------------------
# Live MQTT session integration
# ---------------------------------------------------------------------------


class _FakeLiveSession:
    """Minimal live-session double for the coordinator lifecycle tests."""

    def __init__(self, vehicles, **kwargs):
        self.vehicles = list(vehicles)
        self.kwargs = kwargs
        self.started = False
        self.stopped = False
        self._state = "stopped"

    async def start(self):
        self.started = True
        self._state = "connected"

    async def stop(self):
        self.stopped = True
        self._state = "stopped"

    @property
    def state(self):
        return self._state

    def stats(self):
        return SimpleNamespace(
            as_dict=lambda: {
                "state": self._state,
                "connects": 1,
                "reconnects": 0,
                "messages": 0,
                "reports": 0,
                "events": 0,
                "dropped": 0,
                "last_error": None,
                "last_message_at": None,
                "connected_since": None,
                "subscriptions": [],
            }
        )


def _live_mqtt_vehicle(protocol: str = "MQTT") -> Vehicle:
    return Vehicle(
        car_id="car-1",
        vin="VIN-PLACEHOLDER-1",
        series_name="S05",
        model_code="SC6464AAKBEV",
        protocol_type=protocol,
    )


@pytest.mark.asyncio
async def test_live_session_starts_and_stops_with_the_entry():
    client = _FakeIntlClient([])
    coordinator, _updates = _coordinator(client)
    coordinator.vehicles = [_live_mqtt_vehicle()]
    session = _FakeLiveSession(coordinator.vehicles)
    client.create_mqtt_session = lambda vehicles, **kwargs: session

    await coordinator.async_start_mqtt_session()
    assert session.started is True
    assert coordinator.mqtt_session_stats()["state"] == "connected"

    await coordinator.async_stop_mqtt_session()
    assert session.stopped is True
    assert coordinator._mqtt_session is None


@pytest.mark.asyncio
async def test_live_session_is_not_started_without_a_user_id_or_for_sda_mqtt():
    client = _FakeIntlClient([])
    coordinator, _updates = _coordinator(client)
    coordinator.vehicles = [_live_mqtt_vehicle()]
    calls: list[object] = []
    client.create_mqtt_session = lambda vehicles, **kwargs: calls.append(vehicles)
    client.user_id = None
    await coordinator.async_start_mqtt_session()
    assert calls == []

    client.user_id = "user-1"
    coordinator.vehicles = [_live_mqtt_vehicle("SDA-MQTT")]
    await coordinator.async_start_mqtt_session()
    assert calls == []


@pytest.mark.asyncio
async def test_live_push_coalesces_and_publishes_the_latest_condition():
    client = _FakeIntlClient([])
    base = VehicleCondition(
        car_id="car-1",
        vin="VIN-PLACEHOLDER-1",
        battery=BatteryCondition(soc_percentage=40),
        last_updated_timestamp=1000,
    )
    coordinator, updates = _coordinator(client, data={"car-1": base})

    first = VehicleCondition(
        car_id="car-1",
        vin="VIN-PLACEHOLDER-1",
        battery=BatteryCondition(soc_percentage=41),
        last_updated_timestamp=1001,
    )
    second = VehicleCondition(
        car_id="car-1",
        vin="VIN-PLACEHOLDER-1",
        battery=BatteryCondition(soc_percentage=42),
        last_updated_timestamp=1002,
    )
    coordinator._on_live_condition("car-1", first)
    coordinator._on_live_condition("car-1", second)
    await asyncio.sleep(0.7)

    assert len(updates) == 1
    assert updates[-1]["car-1"].battery.soc_percentage == 42


@pytest.mark.asyncio
async def test_live_push_does_not_fetch_the_app_condition():
    client = _FakeIntlClient([])
    vehicle = _live_mqtt_vehicle()
    base = VehicleCondition(
        car_id="car-1",
        vin="VIN-PLACEHOLDER-1",
        battery=BatteryCondition(soc_percentage=40),
        last_updated_timestamp=1000,
    )
    coordinator, updates = _coordinator(client, data={"car-1": base})
    coordinator.vehicles = [vehicle]

    pushed = VehicleCondition(
        car_id="car-1",
        vin="VIN-PLACEHOLDER-1",
        battery=BatteryCondition(soc_percentage=41),
        last_updated_timestamp=1001,
    )
    coordinator._on_live_condition("car-1", pushed)
    await asyncio.sleep(0.7)

    assert updates
    assert updates[-1]["car-1"].battery.soc_percentage == 41
    assert client.condition_calls == 0


@pytest.mark.asyncio
async def test_poll_does_not_replace_a_newer_pushed_condition(monkeypatch):
    client = _FakeIntlClient([])
    newer = VehicleCondition(
        car_id="car-1",
        vin="VIN-PLACEHOLDER-1",
        battery=BatteryCondition(soc_percentage=72),
        last_updated_timestamp=2000,
    )
    older = VehicleCondition(
        car_id="car-1",
        vin="VIN-PLACEHOLDER-1",
        battery=BatteryCondition(
            soc_percentage=40,
            charge_plan_id="9",
            charge_plan_valid=True,
            charge_schedule_start="0100",
            charge_schedule_end="0200",
            charge_schedule_enabled=True,
        ),
        last_updated_timestamp=1000,
    )
    coordinator, _updates = _coordinator(client, data={"car-1": newer})
    coordinator.vehicles = [_mqtt_vehicle()]

    async def noop() -> None:
        return None

    async def fake_fetch() -> dict[str, VehicleCondition]:
        return {"car-1": older}

    monkeypatch.setattr(coordinator, "_async_load_snapshot", noop)
    monkeypatch.setattr(coordinator, "_async_maybe_refresh_tokens", noop)
    monkeypatch.setattr(coordinator, "_async_fetch", fake_fetch)

    data = await coordinator._async_update_data()

    assert data["car-1"].battery.soc_percentage == 72
    assert data["car-1"].last_updated_timestamp == 2000
    assert data["car-1"].battery.charge_plan_id == "9"
    assert data["car-1"].battery.charge_schedule_start == "0100"


@pytest.mark.asyncio
async def test_stop_mqtt_session_waits_for_background_tasks():
    client = _FakeIntlClient([])
    coordinator, _updates = _coordinator(client)
    cancelled = asyncio.Event()

    async def worker() -> None:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    coordinator._push_tasks["car-1"] = asyncio.create_task(worker())
    await asyncio.sleep(0)
    await coordinator.async_stop_mqtt_session()

    assert cancelled.is_set()
    assert coordinator._push_tasks == {}


def test_mqtt_session_stats_is_none_when_the_session_never_started():
    client = _FakeIntlClient([])
    coordinator, _updates = _coordinator(client)

    assert coordinator.live_session_enabled is True
    assert coordinator.mqtt_session_stats() is None


def test_mqtt_session_stats_reports_the_conflict_state():
    client = _FakeIntlClient([])
    coordinator, _updates = _coordinator(client)
    session = _FakeLiveSession([])
    session._state = "conflict"
    coordinator._mqtt_session = session

    stats = coordinator.mqtt_session_stats()

    assert stats is not None
    assert stats["state"] == "conflict"
    assert stats["enabled"] is True


def test_mqtt_session_stats_is_none_when_the_option_is_disabled():
    client = _FakeIntlClient([])
    coordinator, _updates = _coordinator(client)
    coordinator.live_session_enabled = False

    assert coordinator.mqtt_session_stats() is None


@pytest.mark.asyncio
async def test_live_push_coalesces_a_burst_into_a_bounded_number_of_updates():
    client = _FakeIntlClient([])
    base = VehicleCondition(
        car_id="car-1",
        vin="VIN-PLACEHOLDER-1",
        battery=BatteryCondition(soc_percentage=40),
        last_updated_timestamp=1000,
    )
    coordinator, updates = _coordinator(client, data={"car-1": base})

    for index in range(4):
        coordinator._on_live_condition(
            "car-1",
            VehicleCondition(
                car_id="car-1",
                vin="VIN-PLACEHOLDER-1",
                battery=BatteryCondition(soc_percentage=41 + index),
                last_updated_timestamp=1001 + index,
            ),
        )
        await asyncio.sleep(0.3)
    await asyncio.sleep(0.8)

    assert updates
    assert updates[-1]["car-1"].battery.soc_percentage == 44
    assert len(updates) <= 3


@pytest.mark.asyncio
async def test_live_session_is_not_started_when_the_option_is_disabled():
    client = _FakeIntlClient([])
    coordinator, _updates = _coordinator(client)
    coordinator.vehicles = [_live_mqtt_vehicle()]
    coordinator.live_session_enabled = False
    calls: list[object] = []
    client.create_mqtt_session = lambda vehicles, **kwargs: calls.append(vehicles)

    await coordinator.async_start_mqtt_session()

    assert calls == []
    assert coordinator._mqtt_session is None


@pytest.mark.asyncio
async def test_live_session_factory_failure_does_not_break_the_entry():
    client = _FakeIntlClient([])
    coordinator, _updates = _coordinator(client)
    coordinator.vehicles = [_live_mqtt_vehicle()]

    def boom(vehicles, **kwargs):
        raise RuntimeError("broker unavailable")

    client.create_mqtt_session = boom

    await coordinator.async_start_mqtt_session()

    assert coordinator._mqtt_session is None


@pytest.mark.asyncio
async def test_poll_keeps_a_same_timestamp_push_that_arrived_in_flight(monkeypatch):
    client = _FakeIntlClient([])
    pushed = VehicleCondition(
        car_id="car-1",
        vin="VIN-PLACEHOLDER-1",
        battery=BatteryCondition(soc_percentage=99),
        last_updated_timestamp=2000,
    )
    polled = VehicleCondition(
        car_id="car-1",
        vin="VIN-PLACEHOLDER-1",
        battery=BatteryCondition(
            soc_percentage=41,
            charge_plan_id="7",
            charge_schedule_start="0500",
            charge_schedule_end="0600",
        ),
        last_updated_timestamp=2000,
    )
    coordinator, _updates = _coordinator(client, data={"car-1": pushed})
    coordinator.vehicles = [_mqtt_vehicle()]

    async def noop() -> None:
        return None

    async def fake_fetch() -> dict[str, VehicleCondition]:
        coordinator._vehicle_generation["car-1"] = (
            coordinator._vehicle_generation.get("car-1", 0) + 1
        )
        return {"car-1": polled}

    monkeypatch.setattr(coordinator, "_async_load_snapshot", noop)
    monkeypatch.setattr(coordinator, "_async_maybe_refresh_tokens", noop)
    monkeypatch.setattr(coordinator, "_async_fetch", fake_fetch)

    data = await coordinator._async_update_data()

    assert data["car-1"].battery.soc_percentage == 99
    assert data["car-1"].battery.charge_plan_id == "7"


@pytest.mark.asyncio
async def test_apply_condition_does_not_replace_a_same_timestamp_push(monkeypatch):
    client = _FakeIntlClient([])
    pushed = VehicleCondition(
        car_id="car-1",
        vin="VIN-PLACEHOLDER-1",
        battery=BatteryCondition(soc_percentage=99),
        last_updated_timestamp=2000,
    )
    pushed_in_flight = VehicleCondition(
        car_id="car-1",
        vin="VIN-PLACEHOLDER-1",
        battery=BatteryCondition(soc_percentage=99),
        last_updated_timestamp=2000,
    )
    incoming = VehicleCondition(
        car_id="car-1",
        vin="VIN-PLACEHOLDER-1",
        battery=BatteryCondition(soc_percentage=41),
        last_updated_timestamp=2000,
    )
    coordinator, updates = _coordinator(client, data={"car-1": pushed})
    coordinator.vehicles = [_mqtt_vehicle()]

    async def overlay(vehicle, condition, **kwargs):
        coordinator.async_set_updated_data({"car-1": pushed_in_flight})
        return condition

    monkeypatch.setattr(coordinator, "_overlay_app_comfort", overlay)

    await coordinator._async_apply_condition("car-1", incoming)

    assert all(
        update["car-1"].battery.soc_percentage == 99 for update in updates
    )
    assert coordinator.data["car-1"].battery.soc_percentage == 99


@pytest.mark.asyncio
async def test_poll_applies_a_strictly_newer_result_even_after_a_push(monkeypatch):
    client = _FakeIntlClient([])
    pushed = VehicleCondition(
        car_id="car-1",
        vin="VIN-PLACEHOLDER-1",
        battery=BatteryCondition(soc_percentage=99),
        last_updated_timestamp=2000,
    )
    fetched = VehicleCondition(
        car_id="car-1",
        vin="VIN-PLACEHOLDER-1",
        battery=BatteryCondition(soc_percentage=55),
        last_updated_timestamp=3000,
    )
    coordinator, _updates = _coordinator(client, data={"car-1": pushed})
    coordinator.vehicles = [_mqtt_vehicle()]

    async def noop() -> None:
        return None

    async def fake_fetch() -> dict[str, VehicleCondition]:
        coordinator._vehicle_generation["car-1"] = (
            coordinator._vehicle_generation.get("car-1", 0) + 1
        )
        return {"car-1": fetched}

    monkeypatch.setattr(coordinator, "_async_load_snapshot", noop)
    monkeypatch.setattr(coordinator, "_async_maybe_refresh_tokens", noop)
    monkeypatch.setattr(coordinator, "_async_fetch", fake_fetch)

    data = await coordinator._async_update_data()

    assert data["car-1"].battery.soc_percentage == 55
    assert data["car-1"].last_updated_timestamp == 3000


@pytest.mark.asyncio
async def test_live_push_keeps_the_rest_authored_steering_wheel_state():
    client = _FakeIntlClient([])
    base = VehicleCondition(
        car_id="car-1",
        vin="VIN-PLACEHOLDER-1",
        battery=BatteryCondition(soc_percentage=40),
        last_updated_timestamp=1000,
    )
    coordinator, updates = _coordinator(client, data={"car-1": base})
    coordinator.vehicles = [_mqtt_vehicle()]
    coordinator._last_steering_wheel["car-1"] = (False, None)

    pushed = VehicleCondition(
        car_id="car-1",
        vin="VIN-PLACEHOLDER-1",
        battery=BatteryCondition(soc_percentage=41),
        climate=ClimateCondition(steering_wheel_heater_on=True),
        last_updated_timestamp=1001,
        mqtt_raw_data={"steeringWheelHeating": 2},
    )
    coordinator._on_live_condition("car-1", pushed)
    await asyncio.sleep(0.7)

    assert updates
    assert updates[-1]["car-1"].climate.steering_wheel_heater_on is True


@pytest.mark.asyncio
async def test_merge_condition_accepts_zero_after_the_seat_sleep_sentinel():
    client = _FakeIntlClient([])
    previous = VehicleCondition(car_id="car-1", vin="")
    previous.seats.front_left.ventilation_level = 1
    coordinator, _ = _coordinator(client, data={"car-1": previous})

    off = VehicleCondition(car_id="car-1", vin="")
    off.seats.front_left.ventilation_level = 0
    merged = coordinator._merge_condition("car-1", off)

    assert merged.seats.front_left.ventilation_level == 0


@pytest.mark.asyncio
async def test_charging_read_never_wakes_an_mqtt_vehicle():
    client = _FakeIntlClient([])
    now = int(time.time())
    current = VehicleCondition(
        car_id="car-1",
        vin="VIN-PLACEHOLDER-1",
        battery=BatteryCondition(soc_percentage=40),
        last_updated_timestamp=now,
    )
    coordinator, _updates = _coordinator(client, data={"car-1": current})
    coordinator.vehicles = [_live_mqtt_vehicle()]
    coordinator._wake_report_timeout = 0.01
    coordinator._wake_poll_interval = 0.001
    fresh = VehicleCondition(
        car_id="car-1",
        vin="VIN-PLACEHOLDER-1",
        battery=BatteryCondition(soc_percentage=41),
        last_updated_timestamp=now + 10,
    )
    client.mqtt_condition = fresh
    client.http_condition = fresh

    await coordinator._async_read_charging_vehicle("car-1")

    assert client.wake_calls == 0
    assert client.events.count("mqtt_condition") == 1


def _tires(**pressures: float) -> TiresCondition:
    """Build a tire group from the four position pressures."""
    return TiresCondition(
        front_left=TireStatus(pressure_bar=pressures.get("front_left")),
        front_right=TireStatus(pressure_bar=pressures.get("front_right")),
        rear_left=TireStatus(pressure_bar=pressures.get("rear_left")),
        rear_right=TireStatus(pressure_bar=pressures.get("rear_right")),
    )


def test_wake_burst_tire_zero_keeps_the_last_valid_pressure():
    client = _FakeIntlClient([])
    previous = VehicleCondition(
        car_id="car-1",
        vin="",
        tires=_tires(
            front_left=2.71, front_right=2.72, rear_left=2.73, rear_right=2.74
        ),
        mqtt_raw_data={"lfTyrePressure": 271.0},
    )
    coordinator, _ = _coordinator(client, data={"car-1": previous})
    burst = VehicleCondition(
        car_id="car-1",
        vin="",
        tires=_tires(
            front_left=0.0, front_right=0.0, rear_left=0.0, rear_right=0.0
        ),
        mqtt_raw_data={"lfTyrePressure": 0.0},
    )

    coordinator._retain_valid_tire_pressures("car-1", previous, burst, now=100.0)

    assert burst.tires.front_left.pressure_bar == 2.71
    assert burst.tires.front_right.pressure_bar == 2.72
    assert burst.tires.rear_left.pressure_bar == 2.73
    assert burst.tires.rear_right.pressure_bar == 2.74


def test_persistent_tire_zero_is_published_after_a_minute():
    client = _FakeIntlClient([])
    previous = VehicleCondition(
        car_id="car-1",
        vin="",
        tires=_tires(front_left=2.71),
        mqtt_raw_data={"lfTyrePressure": 271.0},
    )
    coordinator, _ = _coordinator(client, data={"car-1": previous})
    first = VehicleCondition(
        car_id="car-1",
        vin="",
        tires=_tires(front_left=0.0),
        mqtt_raw_data={"lfTyrePressure": 0.0},
    )
    coordinator._retain_valid_tire_pressures("car-1", previous, first, now=100.0)
    assert first.tires.front_left.pressure_bar == 2.71

    persisted = VehicleCondition(
        car_id="car-1",
        vin="",
        tires=_tires(front_left=0.0),
        mqtt_raw_data={"lfTyrePressure": 0.0},
    )
    coordinator._retain_valid_tire_pressures("car-1", previous, persisted, now=161.0)
    assert persisted.tires.front_left.pressure_bar == 0.0


def test_tire_zero_timer_clears_with_a_positive_reading():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client, data={})
    zero = VehicleCondition(
        car_id="car-1",
        vin="",
        tires=_tires(front_left=0.0),
        mqtt_raw_data={"lfTyrePressure": 0.0},
    )

    coordinator._retain_valid_tire_pressures("car-1", None, zero, now=100.0)
    assert zero.tires.front_left.pressure_bar is None
    assert "front_left" in coordinator._tire_zero_since["car-1"]

    healthy = VehicleCondition(
        car_id="car-1",
        vin="",
        tires=_tires(front_left=2.7),
        mqtt_raw_data={"lfTyrePressure": 270.0},
    )
    coordinator._retain_valid_tire_pressures("car-1", None, healthy, now=110.0)
    assert healthy.tires.front_left.pressure_bar == 2.7
    assert "front_left" not in coordinator._tire_zero_since["car-1"]


def test_first_zero_without_a_previous_value_stays_unknown():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client, data={})
    zero = VehicleCondition(
        car_id="car-1",
        vin="",
        tires=_tires(front_left=0.0),
        mqtt_raw_data={"lfTyrePressure": 0.0},
    )

    coordinator._retain_valid_tire_pressures("car-1", None, zero, now=100.0)

    assert zero.tires.front_left.pressure_bar is None


@pytest.mark.asyncio
async def test_a_second_merge_of_the_same_report_keeps_the_tire_timer():
    client = _FakeIntlClient([])
    previous = VehicleCondition(
        car_id="car-1",
        vin="",
        last_updated_timestamp=999,
        tires=_tires(front_left=2.71),
        mqtt_raw_data={"lfTyrePressure": 271.0},
    )
    coordinator, updates = _coordinator(client, data={"car-1": previous})
    raw = VehicleCondition(
        car_id="car-1",
        vin="",
        last_updated_timestamp=1000,
        tires=_tires(front_left=0.0),
        mqtt_raw_data={"lfTyrePressure": 0.0},
    )

    # The poll path merges twice: the fetch merges the report and the apply
    # merges the already-restored condition again.
    merged = coordinator._merge_condition("car-1", raw)
    assert merged.tires.front_left.pressure_bar == 2.71
    await coordinator._async_apply_condition("car-1", merged)

    assert "front_left" in coordinator._tire_zero_since["car-1"]
    assert updates[-1]["car-1"].tires.front_left.pressure_bar == 2.71

    recovered = VehicleCondition(
        car_id="car-1",
        vin="",
        last_updated_timestamp=1001,
        tires=_tires(front_left=2.75),
        mqtt_raw_data={"lfTyrePressure": 275.0},
    )
    await coordinator._async_apply_condition("car-1", recovered)

    assert "front_left" not in coordinator._tire_zero_since["car-1"]
    assert updates[-1]["car-1"].tires.front_left.pressure_bar == 2.75


@pytest.mark.asyncio
async def test_a_persistent_tire_zero_is_published_through_the_apply_path():
    client = _FakeIntlClient([])
    previous = VehicleCondition(
        car_id="car-1",
        vin="",
        last_updated_timestamp=999,
        tires=_tires(front_left=2.71),
        mqtt_raw_data={"lfTyrePressure": 271.0},
    )
    coordinator, updates = _coordinator(client, data={"car-1": previous})
    coordinator._tire_zero_since = {
        "car-1": {"front_left": time.monotonic() - 61}
    }
    flat = VehicleCondition(
        car_id="car-1",
        vin="",
        last_updated_timestamp=2000,
        tires=_tires(front_left=0.0),
        mqtt_raw_data={"lfTyrePressure": 0.0},
    )

    await coordinator._async_apply_condition("car-1", flat)

    assert updates[-1]["car-1"].tires.front_left.pressure_bar == 0.0


def test_a_delta_without_tire_keys_keeps_the_tire_timer():
    client = _FakeIntlClient([])
    previous = VehicleCondition(
        car_id="car-1",
        vin="",
        tires=_tires(front_left=2.71),
        mqtt_raw_data={"lfTyrePressure": 271.0},
    )
    coordinator, _ = _coordinator(client, data={"car-1": previous})
    zero = VehicleCondition(
        car_id="car-1",
        vin="",
        last_updated_timestamp=1000,
        tires=_tires(front_left=0.0),
        mqtt_raw_data={"lfTyrePressure": 0.0},
    )
    coordinator._merge_condition("car-1", zero)
    assert "front_left" in coordinator._tire_zero_since["car-1"]

    # A one-key delta that does not carry the tire group must not clear the
    # timer: the group retention copies the last published (valid) pressure.
    delta = VehicleCondition(
        car_id="car-1",
        vin="",
        last_updated_timestamp=1001,
        mqtt_raw_data={"soc": 50},
    )
    merged = coordinator._merge_condition("car-1", delta)

    assert "front_left" in coordinator._tire_zero_since["car-1"]
    assert merged.tires.front_left.pressure_bar == 2.71


def test_two_tire_reports_in_the_same_second_are_both_guarded():
    client = _FakeIntlClient([])
    previous = VehicleCondition(
        car_id="car-1",
        vin="",
        last_updated_timestamp=999,
        tires=_tires(front_left=2.71),
        mqtt_raw_data={"lfTyrePressure": 271.0},
    )
    coordinator, _ = _coordinator(client, data={"car-1": previous})
    first_zero = VehicleCondition(
        car_id="car-1",
        vin="",
        last_updated_timestamp=1000,
        tires=_tires(front_left=0.0),
        mqtt_raw_data={"lfTyrePressure": 0.0},
    )
    coordinator._merge_condition("car-1", first_zero)

    # A second, distinct report inside the same second must still be guarded
    # (the dedupe is per report object, not per timestamp).
    second_zero = VehicleCondition(
        car_id="car-1",
        vin="",
        last_updated_timestamp=1000,
        tires=_tires(front_left=0.0),
        mqtt_raw_data={"lfTyrePressure": 0.0},
    )
    merged = coordinator._merge_condition("car-1", second_zero)
    assert merged.tires.front_left.pressure_bar == 2.71
    assert "front_left" in coordinator._tire_zero_since["car-1"]

    # A positive report in that same second clears the timer.
    recovered = VehicleCondition(
        car_id="car-1",
        vin="",
        last_updated_timestamp=1000,
        tires=_tires(front_left=2.75),
        mqtt_raw_data={"lfTyrePressure": 275.0},
    )
    coordinator._merge_condition("car-1", recovered)

    assert "front_left" not in coordinator._tire_zero_since["car-1"]
