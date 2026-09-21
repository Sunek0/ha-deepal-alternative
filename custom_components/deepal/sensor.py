"""Sensor platform for Changan Deepal integration."""

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
    UnitOfDensity,
    UnitOfElectricCurrent,
    UnitOfLength,
    UnitOfRatio,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, DEFAULT_MODEL
from .coordinator import DeepalDataUpdateCoordinator
from .deepal import DeepalIntlClient
from .runtime_data import DeepalConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeepalConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Deepal sensors based on a config entry."""
    coordinator: DeepalDataUpdateCoordinator = entry.runtime_data.coordinator

    entities: list[SensorEntity] = []

    for vehicle in coordinator.vehicles:
        entities.extend([
            DeepalBatterySocSensor(coordinator, vehicle),
            DeepalRemainingRangeSensor(coordinator, vehicle),
            DeepalOdometerSensor(coordinator, vehicle),
        ])

        if coordinator.vehicle_uses_mqtt(vehicle.car_id):
            entities.extend([
                DeepalMileageYesterdaySensor(coordinator, vehicle),
                DeepalTripMileageSensor(coordinator, vehicle),
            ])

        if isinstance(coordinator.client, DeepalIntlClient):
            for key, label in (
                ("front_left", "Front Left"),
                ("front_right", "Front Right"),
                ("rear_left", "Rear Left"),
                ("rear_right", "Rear Right"),
            ):
                entities.append(DeepalTirePressureSensor(coordinator, vehicle, key, label))

            for position, label in (
                ("front_left", "Front Left"),
                ("front_right", "Front Right"),
                ("rear_left", "Rear Left"),
                ("rear_right", "Rear Right"),
            ):
                entities.append(
                    DeepalSeatLevelSensor(coordinator, vehicle, position, "heating_level", label, "Heating")
                )
            for position, label in (
                ("front_left", "Front Left"),
                ("front_right", "Front Right"),
            ):
                entities.append(
                    DeepalSeatLevelSensor(coordinator, vehicle, position, "ventilation_level", label, "Ventilation")
                )

            entities.append(DeepalSteeringWheelHeaterLevelSensor(coordinator, vehicle))

            entities.extend(
                DeepalSensor(coordinator, vehicle, description)
                for description in SENSORS
            )

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
    _attr_native_unit_of_measurement = UnitOfRatio.PERCENTAGE
    _attr_icon = "mdi:car-battery"

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
    _attr_icon = "mdi:gauge"

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
    _attr_icon = "mdi:counter"

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
    _attr_icon = "mdi:calendar-clock"

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
    _attr_icon = "mdi:map-marker-path"

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
    _attr_icon = "mdi:tire"

    def __init__(self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any, key: str, label: str) -> None:
        super().__init__(coordinator, vehicle)
        self._key = key
        self._attr_unique_id = f"deepal_{vehicle.car_id}_tire_{key}_pressure"
        self._attr_translation_key = "tire_pressure"
        self._attr_translation_placeholders = {"position": label}

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
    _attr_icon = "mdi:car-seat"

    def __init__(
        self,
        coordinator: DeepalDataUpdateCoordinator,
        vehicle: Any,
        position: str,
        kind: str,
        label: str,
        title: str,
    ) -> None:
        super().__init__(coordinator, vehicle)
        self._position = position
        self._kind = kind
        self._attr_unique_id = f"deepal_{vehicle.car_id}_seat_{position}_{kind}"
        self._attr_translation_key = (
            "seat_heating_level"
            if kind == "heating_level"
            else "seat_ventilation_level"
        )
        self._attr_translation_placeholders = {"position": label}

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
    _attr_icon = "mdi:steering"

    def __init__(self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any) -> None:
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_steering_wheel_heater_level"
        self._attr_translation_key = "steering_wheel_heater_level"

    @property
    def native_value(self) -> int | None:
        """Return the steering wheel heater level."""
        cond = self.coordinator.data.get(self._car_id)
        return cond.climate.steering_wheel_heater_level if cond else None


@dataclass(frozen=True, kw_only=True)
class DeepalSensorDescription(SensorEntityDescription):
    """Description of an extended international sensor."""

    value_fn: Callable[[Any, Any], Any]


SENSORS: tuple[DeepalSensorDescription, ...] = (
    DeepalSensorDescription(
        key="speed",
        name="Speed",
        value_fn=lambda cond, vehicle: cond.speed_kmh,
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        icon="mdi:speedometer",
    ),
    DeepalSensorDescription(
        key="inside_temperature",
        name="Inside Temperature",
        value_fn=lambda cond, vehicle: cond.climate.inside_temperature_c,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        icon="mdi:thermometer",
    ),
    DeepalSensorDescription(
        key="outside_temperature",
        name="Outside Temperature",
        value_fn=lambda cond, vehicle: cond.climate.outside_temperature_c,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        icon="mdi:thermometer-lines",
    ),
    DeepalSensorDescription(
        key="cabin_humidity",
        name="Cabin Humidity",
        value_fn=lambda cond, vehicle: cond.climate.humidity,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfRatio.PERCENTAGE,
        icon="mdi:water-percent",
    ),
    DeepalSensorDescription(
        key="inside_pm25",
        name="Inside PM2.5",
        value_fn=lambda cond, vehicle: cond.climate.inside_pm25,
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDensity.MICROGRAMS_PER_CUBIC_METER,
        icon="mdi:blur",
    ),
    DeepalSensorDescription(
        key="air_quality_level",
        name="Air Quality Level",
        value_fn=lambda cond, vehicle: cond.climate.air_quality_level,
        device_class=None,
        state_class=None,
        native_unit_of_measurement=None,
        icon="mdi:air-filter",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeepalSensorDescription(
        key="charge_status",
        name="Charge Status",
        value_fn=lambda cond, vehicle: cond.battery.charging_status,
        device_class=None,
        state_class=None,
        native_unit_of_measurement=None,
        icon="mdi:battery-charging",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeepalSensorDescription(
        key="charge_current",
        name="Charge Current",
        value_fn=lambda cond, vehicle: cond.battery.charge_current_a,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
    ),
    DeepalSensorDescription(
        key="ac_charge_current",
        name="AC Charge Current",
        value_fn=lambda cond, vehicle: cond.battery.ac_charge_current_a,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
    ),
    DeepalSensorDescription(
        key="dc_charge_current",
        name="DC Charge Current",
        value_fn=lambda cond, vehicle: cond.battery.dc_charge_current_a,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-dc",
    ),
    DeepalSensorDescription(
        key="remaining_charge_time",
        name="Remaining Charge Time",
        value_fn=lambda cond, vehicle: cond.battery.remaining_charge_time_min,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        icon="mdi:timer-sand",
    ),
    DeepalSensorDescription(
        key="charge_limit",
        name="Charge Limit",
        value_fn=lambda cond, vehicle: cond.battery.charge_limit_percent,
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfRatio.PERCENTAGE,
        icon="mdi:battery-lock",
    ),
    DeepalSensorDescription(
        key="charge_schedule_start",
        name="Charge Schedule Start",
        value_fn=lambda cond, vehicle: cond.battery.charge_schedule_start,
        device_class=None,
        state_class=None,
        native_unit_of_measurement=None,
        icon="mdi:clock-start",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeepalSensorDescription(
        key="charge_schedule_end",
        name="Charge Schedule End",
        value_fn=lambda cond, vehicle: cond.battery.charge_schedule_end,
        device_class=None,
        state_class=None,
        native_unit_of_measurement=None,
        icon="mdi:clock-end",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeepalSensorDescription(
        key="vehicle_status",
        name="Vehicle Status",
        value_fn=lambda cond, vehicle: cond.vehicle_status,
        device_class=None,
        state_class=None,
        native_unit_of_measurement=None,
        icon="mdi:car-info",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeepalSensorDescription(
        key="power_status",
        name="Power Status",
        value_fn=lambda cond, vehicle: cond.power_status,
        device_class=None,
        state_class=None,
        native_unit_of_measurement=None,
        icon="mdi:power",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeepalSensorDescription(
        key="gear",
        name="Gear",
        value_fn=lambda cond, vehicle: cond.gear,
        device_class=None,
        state_class=None,
        native_unit_of_measurement=None,
        icon="mdi:car-shift-pattern",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeepalSensorDescription(
        key="epb_status",
        name="Electronic Parking Brake",
        value_fn=lambda cond, vehicle: cond.epb_status,
        device_class=None,
        state_class=None,
        native_unit_of_measurement=None,
        icon="mdi:car-brake-parking",
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
        icon="mdi:clock-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
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
        if description.device_class is not None:
            self._attr_device_class = description.device_class
        if description.state_class is not None:
            self._attr_state_class = description.state_class
        if description.native_unit_of_measurement is not None:
            self._attr_native_unit_of_measurement = (
                description.native_unit_of_measurement
            )
        if description.icon is not None:
            self._attr_icon = description.icon
        if description.entity_category is not None:
            self._attr_entity_category = description.entity_category

    @property
    def native_value(self) -> Any:
        """Return the described value."""
        cond = self.coordinator.data.get(self._car_id)
        if not cond:
            return None
        return self.entity_description.value_fn(cond, self.vehicle)
