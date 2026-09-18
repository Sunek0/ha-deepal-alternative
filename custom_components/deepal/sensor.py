"""Sensor platform for Changan Deepal integration."""

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfLength,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
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
