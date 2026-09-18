"""Sensor platform for Changan Deepal integration."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfDensity,
    UnitOfElectricCurrent,
    UnitOfLength,
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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Deepal sensors based on a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: DeepalDataUpdateCoordinator = data["coordinator"]

    entities: list[SensorEntity] = []

    for vehicle in coordinator.vehicles:
        entities.extend([
            DeepalBatterySocSensor(coordinator, vehicle),
            DeepalRemainingRangeSensor(coordinator, vehicle),
            DeepalOdometerSensor(coordinator, vehicle),
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
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:car-battery"

    def __init__(self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any) -> None:
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_battery_soc"
        self._attr_name = f"{vehicle.series_name} Battery Level"

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
        self._attr_name = f"{vehicle.series_name} Remaining Range"

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
        self._attr_name = f"{vehicle.series_name} Total Mileage"

    @property
    def native_value(self) -> float | None:
        """Return odometer value (CdcTotMilg)."""
        cond = self.coordinator.data.get(self._car_id)
        return cond.total_odometer_km if cond else None


class DeepalTirePressureSensor(DeepalBaseSensor):
    """Tire pressure (bar) sensor for international vehicles."""

    _attr_device_class = SensorDeviceClass.PRESSURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "bar"
    _attr_icon = "mdi:car-tire-alert"

    def __init__(self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any, key: str, label: str) -> None:
        super().__init__(coordinator, vehicle)
        self._key = key
        self._attr_unique_id = f"deepal_{vehicle.car_id}_tire_{key}_pressure"
        self._attr_name = f"{vehicle.series_name} Tire {label} Pressure"

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
        self._attr_name = f"{vehicle.series_name} {label} Seat {title}"

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
        self._attr_name = f"{vehicle.series_name} Steering Wheel Heater Level"

    @property
    def native_value(self) -> int | None:
        """Return the steering wheel heater level."""
        cond = self.coordinator.data.get(self._car_id)
        return cond.climate.steering_wheel_heater_level if cond else None


@dataclass(frozen=True)
class DeepalSensorDescription:
    """Description of an extended international sensor."""

    key: str
    name: str
    value_fn: Callable[[Any, Any], Any]
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None
    unit: str | None = None
    icon: str | None = None
    entity_category: EntityCategory | None = None


SENSORS: tuple[DeepalSensorDescription, ...] = (
    DeepalSensorDescription(
        "speed",
        "Speed",
        lambda cond, vehicle: cond.speed_kmh,
        SensorDeviceClass.SPEED,
        SensorStateClass.MEASUREMENT,
        UnitOfSpeed.KILOMETERS_PER_HOUR,
        "mdi:speedometer",
    ),
    DeepalSensorDescription(
        "inside_temperature",
        "Inside Temperature",
        lambda cond, vehicle: cond.climate.inside_temperature_c,
        SensorDeviceClass.TEMPERATURE,
        SensorStateClass.MEASUREMENT,
        UnitOfTemperature.CELSIUS,
        "mdi:thermometer",
    ),
    DeepalSensorDescription(
        "outside_temperature",
        "Outside Temperature",
        lambda cond, vehicle: cond.climate.outside_temperature_c,
        SensorDeviceClass.TEMPERATURE,
        SensorStateClass.MEASUREMENT,
        UnitOfTemperature.CELSIUS,
        "mdi:thermometer-lines",
    ),
    DeepalSensorDescription(
        "cabin_humidity",
        "Cabin Humidity",
        lambda cond, vehicle: cond.climate.humidity,
        SensorDeviceClass.HUMIDITY,
        SensorStateClass.MEASUREMENT,
        PERCENTAGE,
        "mdi:water-percent",
    ),
    DeepalSensorDescription(
        "inside_pm25",
        "Inside PM2.5",
        lambda cond, vehicle: cond.climate.inside_pm25,
        None,
        SensorStateClass.MEASUREMENT,
        UnitOfDensity.MICROGRAMS_PER_CUBIC_METER,
        "mdi:blur",
    ),
    DeepalSensorDescription(
        "air_quality_level",
        "Air Quality Level",
        lambda cond, vehicle: cond.climate.air_quality_level,
        None,
        None,
        None,
        "mdi:air-filter",
        EntityCategory.DIAGNOSTIC,
    ),
    DeepalSensorDescription(
        "charge_status",
        "Charge Status",
        lambda cond, vehicle: cond.battery.charging_status,
        None,
        None,
        None,
        "mdi:battery-charging",
        EntityCategory.DIAGNOSTIC,
    ),
    DeepalSensorDescription(
        "charge_current",
        "Charge Current",
        lambda cond, vehicle: cond.battery.charge_current_a,
        SensorDeviceClass.CURRENT,
        SensorStateClass.MEASUREMENT,
        UnitOfElectricCurrent.AMPERE,
        "mdi:current-ac",
    ),
    DeepalSensorDescription(
        "ac_charge_current",
        "AC Charge Current",
        lambda cond, vehicle: cond.battery.ac_charge_current_a,
        SensorDeviceClass.CURRENT,
        SensorStateClass.MEASUREMENT,
        UnitOfElectricCurrent.AMPERE,
        "mdi:current-ac",
    ),
    DeepalSensorDescription(
        "dc_charge_current",
        "DC Charge Current",
        lambda cond, vehicle: cond.battery.dc_charge_current_a,
        SensorDeviceClass.CURRENT,
        SensorStateClass.MEASUREMENT,
        UnitOfElectricCurrent.AMPERE,
        "mdi:current-dc",
    ),
    DeepalSensorDescription(
        "remaining_charge_time",
        "Remaining Charge Time",
        lambda cond, vehicle: cond.battery.remaining_charge_time_min,
        SensorDeviceClass.DURATION,
        SensorStateClass.MEASUREMENT,
        UnitOfTime.MINUTES,
        "mdi:timer-sand",
    ),
    DeepalSensorDescription(
        "charge_limit",
        "Charge Limit",
        lambda cond, vehicle: cond.battery.charge_limit_percent,
        None,
        SensorStateClass.MEASUREMENT,
        PERCENTAGE,
        "mdi:battery-lock",
    ),
    DeepalSensorDescription(
        "charge_schedule_start",
        "Charge Schedule Start",
        lambda cond, vehicle: cond.battery.charge_schedule_start,
        None,
        None,
        None,
        "mdi:clock-start",
        EntityCategory.DIAGNOSTIC,
    ),
    DeepalSensorDescription(
        "charge_schedule_end",
        "Charge Schedule End",
        lambda cond, vehicle: cond.battery.charge_schedule_end,
        None,
        None,
        None,
        "mdi:clock-end",
        EntityCategory.DIAGNOSTIC,
    ),
    DeepalSensorDescription(
        "vehicle_status",
        "Vehicle Status",
        lambda cond, vehicle: cond.vehicle_status,
        None,
        None,
        None,
        "mdi:car-info",
        EntityCategory.DIAGNOSTIC,
    ),
    DeepalSensorDescription(
        "power_status",
        "Power Status",
        lambda cond, vehicle: cond.power_status,
        None,
        None,
        None,
        "mdi:power",
        EntityCategory.DIAGNOSTIC,
    ),
    DeepalSensorDescription(
        "gear",
        "Gear",
        lambda cond, vehicle: cond.gear,
        None,
        None,
        None,
        "mdi:car-shift-pattern",
        EntityCategory.DIAGNOSTIC,
    ),
    DeepalSensorDescription(
        "epb_status",
        "Electronic Parking Brake",
        lambda cond, vehicle: cond.epb_status,
        None,
        None,
        None,
        "mdi:car-brake-parking",
        EntityCategory.DIAGNOSTIC,
    ),
    DeepalSensorDescription(
        "last_updated",
        "Last Updated",
        lambda cond, vehicle: (
            datetime.fromtimestamp(cond.last_updated_timestamp, tz=UTC)
            if cond.last_updated_timestamp is not None
            else None
        ),
        SensorDeviceClass.TIMESTAMP,
        None,
        None,
        "mdi:clock-outline",
        EntityCategory.DIAGNOSTIC,
    ),
)


class DeepalSensor(DeepalBaseSensor):
    """Extended international sensor driven by a description."""

    entity_description: DeepalSensorDescription
    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: DeepalDataUpdateCoordinator,
        vehicle: Any,
        description: DeepalSensorDescription,
    ) -> None:
        super().__init__(coordinator, vehicle)
        self.entity_description = description
        self._attr_unique_id = f"deepal_{vehicle.car_id}_{description.key}"
        self._attr_name = f"{vehicle.series_name} {description.name}"
        if description.device_class is not None:
            self._attr_device_class = description.device_class
        if description.state_class is not None:
            self._attr_state_class = description.state_class
        if description.unit is not None:
            self._attr_native_unit_of_measurement = description.unit
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
