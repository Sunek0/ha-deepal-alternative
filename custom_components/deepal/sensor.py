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
