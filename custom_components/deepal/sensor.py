"""Sensor platform for Changan Deepal integration."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfLength,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DEFAULT_MODEL,
    DENSITY_MICROGRAMS_PER_CUBIC_METER,
    DOMAIN,
    MANUFACTURER,
    PERCENTAGE_UNIT,
)
from .coordinator import DeepalDataUpdateCoordinator
from .deepal import DeepalIntlClient
from .deepal.mqtt import (
    CHARGE_STATE_AC_CHARGING,
    CHARGE_STATE_AC_CONNECTED,
    CHARGE_STATE_DC_CHARGING,
    CHARGE_STATE_DC_CONNECTED,
    CHARGE_STATE_NOT_CHARGING,
    charge_state,
)
from .runtime_data import DeepalConfigEntry
from .vehicle_model import is_s05, supports_fuel

_LOGGER = logging.getLogger(__name__)

# Coordinator is used to centralize the data updates
PARALLEL_UPDATES = 0

#: Charging-state enum options (translated under entity.sensor.charge_status.state).
CHARGE_STATUS_OPTIONS = (
    "not_charging",
    "connected_ac",
    "connected_dc",
    "charging_ac",
    "charging_dc",
)
CHARGE_STATUS_OPTION_BY_STATE = {
    CHARGE_STATE_NOT_CHARGING: "not_charging",
    CHARGE_STATE_AC_CONNECTED: "connected_ac",
    CHARGE_STATE_DC_CONNECTED: "connected_dc",
    CHARGE_STATE_AC_CHARGING: "charging_ac",
    CHARGE_STATE_DC_CHARGING: "charging_dc",
}

#: Power-state enum options: only the verified 0/2 mapping is translated.
POWER_STATUS_OPTIONS = ("off", "on")
POWER_STATUS_OPTION_BY_VALUE = {0: "off", 2: "on"}


# Sensors the S05 does not report (verified live on a C857-EU): the MQTT
# payload has no speed, gear, outside temperature, PM2.5, air quality, charge
# limit, parking brake or vehicle status fields, so the entities would stay
# unknown forever.
S05_UNSUPPORTED_SENSOR_KEYS = frozenset(
    {
        "air_quality_level",
        "charge_limit",
        "epb_status",
        "gear",
        "inside_pm25",
        "outside_temperature",
        "speed",
        "vehicle_status",
    }
)

# The S05 has no rear seat heating hardware (the app disables those controls).
S05_UNSUPPORTED_SEAT_POSITIONS = ("rear_left", "rear_right")

# Sensors the S05 gets from a typed enum class instead of the raw description,
# because its wire values (the ChrgSts states) are verified for that model only.
S05_ENUM_SENSOR_KEYS = frozenset({"charge_status"})

# Fuel sensors exist only for fuel vehicles (see supports_fuel).
FUEL_SENSOR_KEYS = frozenset({"fuel_level", "fuel_range", "fuel_tank_capacity"})


def format_hours_minutes(minutes: int | None) -> str | None:
    """Format reported minutes as ``H:MM``, or None when there is no estimate.

    The API reports the remaining charge time in whole minutes; the duration
    sensor exposes them for statistics while this text form is what dashboards
    show without the seconds the frontend adds to duration values.
    """
    if minutes is None:
        return None
    total = max(0, int(minutes))
    return f"{total // 60}:{total % 60:02d}"


def build_sensors(
    coordinator: DeepalDataUpdateCoordinator, vehicle: Any
) -> list[SensorEntity]:
    """Build the sensors for one vehicle, skipping what its model does not report."""
    entities: list[SensorEntity] = [
        DeepalBatterySocSensor(coordinator, vehicle),
        DeepalRemainingRangeSensor(coordinator, vehicle),
        DeepalOdometerSensor(coordinator, vehicle),
    ]

    s05 = is_s05(vehicle)

    if coordinator.vehicle_uses_mqtt(vehicle.car_id) and not s05:
        entities.extend([
            DeepalMileageYesterdaySensor(coordinator, vehicle),
            DeepalTripMileageSensor(coordinator, vehicle),
        ])

    if isinstance(coordinator.client, DeepalIntlClient):
        entities.append(DeepalPowerStatusSensor(coordinator, vehicle))
        if s05:
            entities.append(DeepalChargeStatusSensor(coordinator, vehicle))
            entities.append(DeepalChargeModeSensor(coordinator, vehicle))

        for key in ("front_left", "front_right", "rear_left", "rear_right"):
            entities.append(DeepalTirePressureSensor(coordinator, vehicle, key))

        for position in ("front_left", "front_right", "rear_left", "rear_right"):
            if s05 and position in S05_UNSUPPORTED_SEAT_POSITIONS:
                continue
            entities.append(
                DeepalSeatLevelSensor(coordinator, vehicle, position, "heating_level")
            )
        for position in ("front_left", "front_right"):
            entities.append(
                DeepalSeatLevelSensor(coordinator, vehicle, position, "ventilation_level")
            )

        entities.append(DeepalSteeringWheelHeaterLevelSensor(coordinator, vehicle))

        fuel = supports_fuel(
            vehicle, coordinator.vehicle_capabilities(vehicle.car_id)
        )

        entities.extend(
            DeepalSensor(coordinator, vehicle, description)
            for description in SENSORS
            if not (
                s05
                and description.key
                in (S05_UNSUPPORTED_SENSOR_KEYS | S05_ENUM_SENSOR_KEYS)
            )
            and not (description.key in FUEL_SENSOR_KEYS and not fuel)
        )

    return entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeepalConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Deepal sensors based on a config entry."""
    coordinator: DeepalDataUpdateCoordinator = entry.runtime_data.coordinator

    entities: list[SensorEntity] = []

    for vehicle in coordinator.vehicles:
        entities.extend(build_sensors(coordinator, vehicle))

    async_add_entities(entities)


class DeepalBaseSensor(CoordinatorEntity[DeepalDataUpdateCoordinator], SensorEntity):
    """Base class for Deepal sensors."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any) -> None:
        """Initialize base sensor."""
        super().__init__(coordinator)
        self.vehicle = vehicle
        self._car_id = vehicle.car_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for Home Assistant."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.vehicle.car_id)},
            name=self.vehicle.series_name or DEFAULT_MODEL,
            manufacturer=MANUFACTURER,
            model=self.vehicle.series_name or DEFAULT_MODEL,
        )


class DeepalBatterySocSensor(DeepalBaseSensor):
    """Battery State of Charge (%) sensor."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE_UNIT

    def __init__(self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any) -> None:
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_battery_soc"
        self._attr_translation_key = "battery_level"

    @property
    def native_value(self) -> int | None:
        """Return battery SoC %."""
        cond = self.coordinator.data.get(self._car_id)
        return cond.battery.soc_percentage if cond else None


class DeepalRemainingRangeSensor(DeepalBaseSensor):
    """Remaining range (km) sensor."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS

    def __init__(self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any) -> None:
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_remaining_range"
        self._attr_translation_key = "remaining_range"

    @property
    def native_value(self) -> int | None:
        """Return estimated range in km."""
        cond = self.coordinator.data.get(self._car_id)
        return cond.battery.remaining_range_km if cond else None


class DeepalOdometerSensor(DeepalBaseSensor):
    """Total mileage / odometer (km) sensor."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS

    def __init__(self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any) -> None:
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_total_odometer"
        self._attr_translation_key = "total_odometer"

    @property
    def native_value(self) -> float | None:
        """Return the total odometer in km."""
        cond = self.coordinator.data.get(self._car_id)
        return cond.total_odometer_km if cond else None


class DeepalMileageYesterdaySensor(DeepalBaseSensor):
    """Mileage driven yesterday (km) sensor, MQTT-backed vehicles only."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS

    def __init__(self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any) -> None:
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_mileage_yesterday"
        self._attr_translation_key = "mileage_yesterday"

    @property
    def native_value(self) -> float | None:
        """Return yesterday's mileage in km."""
        cond = self.coordinator.data.get(self._car_id)
        return cond.mileage_yesterday_km if cond else None


class DeepalTripMileageSensor(DeepalBaseSensor):
    """Mileage since the current ignition cycle (km), MQTT-backed vehicles only."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS

    def __init__(self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any) -> None:
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_trip_mileage"
        self._attr_translation_key = "trip_mileage"

    @property
    def native_value(self) -> float | None:
        """Return the trip mileage in km."""
        cond = self.coordinator.data.get(self._car_id)
        return cond.trip_mileage_km if cond else None


class DeepalTirePressureSensor(DeepalBaseSensor):
    """Tire pressure (bar) sensor for international vehicles."""

    _attr_device_class = SensorDeviceClass.PRESSURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "bar"

    def __init__(self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any, key: str) -> None:
        super().__init__(coordinator, vehicle)
        self._key = key
        self._attr_unique_id = f"deepal_{vehicle.car_id}_tire_{key}_pressure"
        self._attr_translation_key = f"tire_pressure_{key}"

    @property
    def native_value(self) -> float | None:
        """Return tire pressure in bar."""
        cond = self.coordinator.data.get(self._car_id)
        if not cond:
            return None
        return getattr(cond.tires, self._key).pressure_bar


class DeepalSeatLevelSensor(DeepalBaseSensor):
    """Seat heating or ventilation level sensor for international vehicles."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: DeepalDataUpdateCoordinator,
        vehicle: Any,
        position: str,
        kind: str,
    ) -> None:
        super().__init__(coordinator, vehicle)
        self._position = position
        self._kind = kind
        self._attr_unique_id = f"deepal_{vehicle.car_id}_seat_{position}_{kind}"
        self._attr_translation_key = f"seat_{kind}_{position}"

    @property
    def native_value(self) -> int | None:
        """Return the seat level."""
        cond = self.coordinator.data.get(self._car_id)
        if not cond:
            return None
        return getattr(getattr(cond.seats, self._position), self._kind)


class DeepalSteeringWheelHeaterLevelSensor(DeepalBaseSensor):
    """Steering wheel heater level sensor for international vehicles."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any) -> None:
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_steering_wheel_heater_level"
        self._attr_translation_key = "steering_wheel_heater_level"

    @property
    def native_value(self) -> int | None:
        """Return the steering wheel heater level."""
        cond = self.coordinator.data.get(self._car_id)
        return cond.climate.steering_wheel_heater_level if cond else None


class DeepalChargeStatusSensor(DeepalBaseSensor):
    """S05 charging-state sensor with the app's translated states.

    The wire values are the ``ChrgSts`` enum: 0 not charging, 1 AC gun
    connected, 2 DC gun connected, 3 AC charging and 4 DC charging. A value
    outside the enum is unknown, logged once per distinct value and kept
    visible through the raw attribute; it is never translated into a state.
    """

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(CHARGE_STATUS_OPTIONS)
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any) -> None:
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_charge_status"
        self._attr_translation_key = "charge_status"
        self._last_unrecognized: str | None = None

    @property
    def native_value(self) -> str | None:
        """Return the translated charging state, unknown when unrecognized."""
        cond = self.coordinator.data.get(self._car_id)
        raw = cond.battery.charging_status if cond else None
        if raw is None:
            return None
        state = charge_state(raw)
        if state is None:
            if raw != self._last_unrecognized:
                _LOGGER.warning(
                    "Deepal: unrecognized charging state %r for %s; "
                    "reporting unknown",
                    raw,
                    self._car_id,
                )
                self._last_unrecognized = raw
            return None
        self._last_unrecognized = None
        return CHARGE_STATUS_OPTION_BY_STATE[state]

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the raw charging-state value the enum was derived from."""
        cond = self.coordinator.data.get(self._car_id)
        raw = cond.battery.charging_status if cond else None
        return {"raw_charge_status": raw} if raw is not None else None


class DeepalPowerStatusSensor(DeepalBaseSensor):
    """Power-state sensor: 0 off, 2 on, any other value unknown and logged.

    Only the two values verified on a live car are translated; anything else
    (for example an accessory state another model may report) stays unknown
    instead of being published as a number, and remains visible through the
    raw attribute.
    """

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(POWER_STATUS_OPTIONS)
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any) -> None:
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_power_status"
        self._attr_translation_key = "power_status"
        self._last_unrecognized: int | None = None

    @property
    def native_value(self) -> str | None:
        """Return the translated power state, unknown when unrecognized."""
        cond = self.coordinator.data.get(self._car_id)
        status = cond.power_status if cond else None
        if status is None:
            return None
        option = POWER_STATUS_OPTION_BY_VALUE.get(status)
        if option is None:
            if status != self._last_unrecognized:
                _LOGGER.warning(
                    "Deepal: unrecognized power state %r for %s; "
                    "reporting unknown",
                    status,
                    self._car_id,
                )
                self._last_unrecognized = status
            return None
        self._last_unrecognized = None
        return option

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the raw power-state value the enum was derived from."""
        cond = self.coordinator.data.get(self._car_id)
        status = cond.power_status if cond else None
        return {"raw_power_status": status} if status is not None else None


class DeepalChargeModeSensor(DeepalBaseSensor):
    """Charging type (AC/DC) derived from the S05 charging state.

    Unknown while the car is not connected or charging: the entity reports the
    type of the current session, not a guess.
    """

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["ac", "dc"]
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any) -> None:
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_charge_mode"
        self._attr_translation_key = "charge_mode"

    @property
    def native_value(self) -> str | None:
        """Return ``ac``/``dc`` while connected or charging, else unknown."""
        cond = self.coordinator.data.get(self._car_id)
        state = charge_state(cond.battery.charging_status) if cond else None
        if state in (CHARGE_STATE_AC_CONNECTED, CHARGE_STATE_AC_CHARGING):
            return "ac"
        if state in (CHARGE_STATE_DC_CONNECTED, CHARGE_STATE_DC_CHARGING):
            return "dc"
        return None


@dataclass(frozen=True, kw_only=True)
class DeepalSensorDescription(SensorEntityDescription):
    """Description of an extended international sensor."""

    value_fn: Callable[[Any, Any], Any]
    enabled_default: bool = True


SENSORS: tuple[DeepalSensorDescription, ...] = (
    DeepalSensorDescription(
        key="speed",
        name="Speed",
        value_fn=lambda cond, vehicle: cond.speed_kmh,
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
    ),
    DeepalSensorDescription(
        key="inside_temperature",
        name="Inside Temperature",
        value_fn=lambda cond, vehicle: cond.climate.inside_temperature_c,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    DeepalSensorDescription(
        key="outside_temperature",
        name="Outside Temperature",
        value_fn=lambda cond, vehicle: cond.climate.outside_temperature_c,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    DeepalSensorDescription(
        key="cabin_humidity",
        name="Cabin Humidity",
        value_fn=lambda cond, vehicle: cond.climate.humidity,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE_UNIT,
    ),
    DeepalSensorDescription(
        key="inside_pm25",
        name="Inside PM2.5",
        value_fn=lambda cond, vehicle: cond.climate.inside_pm25,
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=DENSITY_MICROGRAMS_PER_CUBIC_METER,
    ),
    DeepalSensorDescription(
        key="air_quality_level",
        name="Air Quality Level",
        value_fn=lambda cond, vehicle: cond.climate.air_quality_level,
        device_class=None,
        state_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeepalSensorDescription(
        key="charge_status",
        name="Charge Status",
        value_fn=lambda cond, vehicle: cond.battery.charging_status,
        device_class=None,
        state_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeepalSensorDescription(
        key="charge_current",
        name="Charge Current",
        value_fn=lambda cond, vehicle: cond.battery.charge_current_a,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
    ),
    DeepalSensorDescription(
        key="ac_charge_current",
        name="AC Charge Current",
        value_fn=lambda cond, vehicle: cond.battery.ac_charge_current_a,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
    ),
    DeepalSensorDescription(
        key="dc_charge_current",
        name="DC Charge Current",
        value_fn=lambda cond, vehicle: cond.battery.dc_charge_current_a,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
    ),
    DeepalSensorDescription(
        key="remaining_charge_time",
        name="Remaining Charge Time",
        value_fn=lambda cond, vehicle: cond.battery.remaining_charge_time_min,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.MINUTES,
    ),
    DeepalSensorDescription(
        key="remaining_charge_time_formatted",
        name="Remaining Charge Time (H:MM)",
        value_fn=lambda cond, vehicle: format_hours_minutes(
            cond.battery.remaining_charge_time_min
        ),
        device_class=None,
        state_class=None,
        native_unit_of_measurement=None,
    ),
    DeepalSensorDescription(
        key="charge_limit",
        name="Charge Limit",
        value_fn=lambda cond, vehicle: cond.battery.charge_limit_percent,
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE_UNIT,
    ),
    DeepalSensorDescription(
        key="charge_schedule_start",
        name="Charge Schedule Start",
        value_fn=lambda cond, vehicle: cond.battery.charge_schedule_start,
        device_class=None,
        state_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeepalSensorDescription(
        key="charge_schedule_end",
        name="Charge Schedule End",
        value_fn=lambda cond, vehicle: cond.battery.charge_schedule_end,
        device_class=None,
        state_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeepalSensorDescription(
        key="fuel_level",
        name="Fuel Level",
        value_fn=lambda cond, vehicle: cond.fuel.level_percent,
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE_UNIT,
    ),
    DeepalSensorDescription(
        key="fuel_range",
        name="Fuel Range",
        value_fn=lambda cond, vehicle: cond.fuel.remaining_range_km,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
    ),
    DeepalSensorDescription(
        key="fuel_tank_capacity",
        name="Fuel Tank Capacity",
        value_fn=lambda cond, vehicle: cond.fuel.tank_capacity_l,
        device_class=SensorDeviceClass.VOLUME,
        state_class=None,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeepalSensorDescription(
        key="vehicle_status",
        name="Vehicle Status",
        value_fn=lambda cond, vehicle: cond.vehicle_status,
        device_class=None,
        state_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeepalSensorDescription(
        key="gear",
        name="Gear",
        value_fn=lambda cond, vehicle: cond.gear,
        device_class=None,
        state_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeepalSensorDescription(
        key="epb_status",
        name="Electronic Parking Brake",
        value_fn=lambda cond, vehicle: cond.epb_status,
        device_class=None,
        state_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeepalSensorDescription(
        key="last_updated",
        name="Last Updated",
        value_fn=lambda cond, vehicle: (
            datetime.fromtimestamp(cond.last_updated_timestamp, tz=UTC)
            if cond.last_updated_timestamp is not None
            else None
        ),
        device_class=SensorDeviceClass.TIMESTAMP,
        state_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeepalSensorDescription(
        key="climate_target_temperature",
        name="Climate Target Temperature",
        value_fn=lambda cond, vehicle: cond.climate.target_temperature_c,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    DeepalSensorDescription(
        key="fan_level",
        name="Climate Fan Level",
        value_fn=lambda cond, vehicle: cond.climate.fan_level,
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=None,
    ),
    DeepalSensorDescription(
        key="license_plate",
        name="License Plate",
        value_fn=lambda cond, vehicle: vehicle.license_plate,
        device_class=None,
        state_class=None,
        native_unit_of_measurement=None,
    ),
    # Window opening degrees. The scale is not confirmed on a real car yet
    # (ventilation around 20, half open around 92), so they ship disabled by
    # default and only pass the reported number through.
    DeepalSensorDescription(
        key="window_opening_front_left",
        name="Front Left Window Opening",
        value_fn=lambda cond, vehicle: cond.window_openings.front_left,
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE_UNIT,
        enabled_default=False,
    ),
    DeepalSensorDescription(
        key="window_opening_front_right",
        name="Front Right Window Opening",
        value_fn=lambda cond, vehicle: cond.window_openings.front_right,
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE_UNIT,
        enabled_default=False,
    ),
    DeepalSensorDescription(
        key="window_opening_rear_left",
        name="Rear Left Window Opening",
        value_fn=lambda cond, vehicle: cond.window_openings.rear_left,
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE_UNIT,
        enabled_default=False,
    ),
    DeepalSensorDescription(
        key="window_opening_rear_right",
        name="Rear Right Window Opening",
        value_fn=lambda cond, vehicle: cond.window_openings.rear_right,
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE_UNIT,
        enabled_default=False,
    ),
)


class DeepalSensor(DeepalBaseSensor):
    """Extended international sensor driven by a description."""

    entity_description: DeepalSensorDescription

    def __init__(
        self,
        coordinator: DeepalDataUpdateCoordinator,
        vehicle: Any,
        description: DeepalSensorDescription,
    ) -> None:
        super().__init__(coordinator, vehicle)
        self.entity_description = description
        self._attr_unique_id = f"deepal_{vehicle.car_id}_{description.key}"
        self._attr_translation_key = description.key
        self._attr_entity_registry_enabled_default = description.enabled_default
        if description.device_class is not None:
            self._attr_device_class = description.device_class
        if description.state_class is not None:
            self._attr_state_class = description.state_class
        if description.native_unit_of_measurement is not None:
            self._attr_native_unit_of_measurement = (
                description.native_unit_of_measurement
            )
        if description.entity_category is not None:
            self._attr_entity_category = description.entity_category

    @property
    def native_value(self) -> Any:
        """Return the described value."""
        cond = self.coordinator.data.get(self._car_id)
        if not cond:
            return None
        return self.entity_description.value_fn(cond, self.vehicle)
