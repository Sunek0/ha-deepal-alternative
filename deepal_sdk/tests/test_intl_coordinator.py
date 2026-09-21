"""Tests for the Home Assistant coordinator command flow."""

import pytest

pytest.importorskip("homeassistant")

from homeassistant.exceptions import HomeAssistantError

from custom_components.deepal.coordinator import DeepalDataUpdateCoordinator
from custom_components.deepal.deepal import (
    ClimateCondition,
    CommandResult,
    CommandResultStatus,
    DeepalAPIError,
    DeepalIntlClient,
    Vehicle,
    VehicleCapabilities,
    VehicleCondition,
)


class _FakeIntlClient(DeepalIntlClient):
    """Fake international client recording the command flow."""

    def __init__(self, results: list[CommandResult]) -> None:
        self.access_token = "test_token_123"
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
    coordinator._command_in_progress = False
    coordinator._optimistic_holds = {}
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
