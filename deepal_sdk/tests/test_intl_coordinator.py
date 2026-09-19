"""Tests for the Home Assistant coordinator command flow."""

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.deepal.coordinator import DeepalDataUpdateCoordinator
from custom_components.deepal.deepal import (
    CommandResult,
    CommandResultStatus,
    DeepalIntlClient,
    VehicleCondition,
)


class _FakeIntlClient(DeepalIntlClient):
    """Fake international client recording the command flow."""

    def __init__(self, results: list[CommandResult]) -> None:
        self.access_token = "test_token_123"
        self.private_key_pem = "test_private_key"
        self.results = list(results)
        self.events: list[str] = []
        self.condition_calls = 0

    async def control_condition_inquiry(self, vehicle_id: str) -> str:
        self.events.append("condition_inquiry")
        return "cmd-inquiry"

    async def control_result_status(
        self, vehicle_id: str, command_id: str
    ) -> CommandResult:
        self.events.append("poll")
        return self.results.pop(0)

    async def get_vehicle_condition(
        self, vehicle_id: str, vin: str | None = None
    ) -> VehicleCondition:
        self.events.append("condition")
        self.condition_calls += 1
        return VehicleCondition(
            car_id=vehicle_id,
            vin=vin or "",
            last_updated_timestamp=1000 + self.condition_calls,
        )


def _coordinator(
    client: _FakeIntlClient,
    data: dict[str, VehicleCondition] | None = None,
) -> tuple[DeepalDataUpdateCoordinator, list[dict[str, VehicleCondition]]]:
    coordinator = object.__new__(DeepalDataUpdateCoordinator)
    coordinator.client = client
    coordinator.vehicles = []
    coordinator.data = data or {}
    coordinator._command_in_progress = False
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
        "car-1", send_command, timeout=1.0, interval=0.01
    )

    assert sent == ["cmd-1"]
    assert client.events.count("poll") == 2
    assert updates
    assert coordinator.data["car-1"].last_updated_timestamp is not None


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


@pytest.mark.asyncio
async def test_concurrent_command_is_blocked():
    client = _FakeIntlClient([])
    coordinator, _ = _coordinator(client)
    coordinator._command_in_progress = True

    async def send_command() -> str:
        return "cmd-1"

    with pytest.raises(HomeAssistantError):
        await coordinator.async_execute_command("car-1", send_command)
