"""Binary sensor platform for Changan Deepal integration."""

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
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
    """Set up Deepal binary sensors based on a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: DeepalDataUpdateCoordinator = data["coordinator"]

    entities: list[BinarySensorEntity] = []

    for vehicle in coordinator.vehicles:
        entities.extend([
            DeepalChargerPluggedBinarySensor(coordinator, vehicle),
            DeepalDoorsLockedBinarySensor(coordinator, vehicle),
        ])

        if isinstance(coordinator.client, DeepalIntlClient):
            for key, label in (
                ("front_left", "Front Left"),
                ("front_right", "Front Right"),
                ("rear_left", "Rear Left"),
                ("rear_right", "Rear Right"),
            ):
                entities.append(DeepalTireAlarmBinarySensor(coordinator, vehicle, key, label))

            for key, label in (
                ("front_left_open", "Front Left"),
                ("front_right_open", "Front Right"),
                ("rear_left_open", "Rear Left"),
                ("rear_right_open", "Rear Right"),
            ):
                entities.append(DeepalWindowBinarySensor(coordinator, vehicle, key, label))

            entities.append(DeepalSteeringWheelHeaterBinarySensor(coordinator, vehicle))

    async_add_entities(entities)


class DeepalBaseBinarySensor(CoordinatorEntity[DeepalDataUpdateCoordinator], BinarySensorEntity):
    """Base binary sensor for Deepal."""

    def __init__(self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any) -> None:
        super().__init__(coordinator)
        self.vehicle = vehicle
        self._car_id = vehicle.car_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.vehicle.car_id)},
            name=self.vehicle.series_name or DEFAULT_MODEL,
            manufacturer=MANUFACTURER,
            model=self.vehicle.series_name or DEFAULT_MODEL,
        )


class DeepalChargerPluggedBinarySensor(DeepalBaseBinarySensor):
    """Charging cable plugged in binary sensor."""

    _attr_device_class = BinarySensorDeviceClass.PLUG
    _attr_icon = "mdi:ev-plug-ccs2"

    def __init__(self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any) -> None:
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_charger_plugged"
        self._attr_name = f"{vehicle.series_name} Charger Plugged"

    @property
    def is_on(self) -> bool | None:
        """Return True if charging cable is connected."""
        cond = self.coordinator.data.get(self._car_id)
        return cond.battery.charger_connected if cond else None


class DeepalDoorsLockedBinarySensor(DeepalBaseBinarySensor):
    """Doors lock binary sensor."""

    _attr_device_class = BinarySensorDeviceClass.LOCK
    _attr_icon = "mdi:car-door-lock"

    def __init__(self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any) -> None:
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_doors_locked"
        self._attr_name = f"{vehicle.series_name} Doors Lock State"

    @property
    def is_on(self) -> bool | None:
        """Return True if unlocked (BinarySensorDeviceClass.LOCK is_on means UNLOCKED)."""
        cond = self.coordinator.data.get(self._car_id)
        return not cond.doors.locked if cond else None


class DeepalTireAlarmBinarySensor(DeepalBaseBinarySensor):
    """Tire pressure alarm binary sensor for international vehicles."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:car-tire-alert"

    def __init__(self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any, key: str, label: str) -> None:
        super().__init__(coordinator, vehicle)
        self._key = key
        self._attr_unique_id = f"deepal_{vehicle.car_id}_tire_{key}_alarm"
        self._attr_name = f"{vehicle.series_name} Tire {label} Alarm"

    @property
    def is_on(self) -> bool | None:
        """Return True if the tire reports an alarm."""
        cond = self.coordinator.data.get(self._car_id)
        if not cond:
            return None
        return getattr(cond.tires, self._key).alarm


class DeepalWindowBinarySensor(DeepalBaseBinarySensor):
    """Window open binary sensor for international vehicles."""

    _attr_device_class = BinarySensorDeviceClass.WINDOW
    _attr_icon = "mdi:window-closed-variant"

    def __init__(self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any, key: str, label: str) -> None:
        super().__init__(coordinator, vehicle)
        self._key = key
        self._attr_unique_id = f"deepal_{vehicle.car_id}_window_{key}"
        self._attr_name = f"{vehicle.series_name} Window {label} Open"

    @property
    def is_on(self) -> bool | None:
        """Return True if the window is open."""
        cond = self.coordinator.data.get(self._car_id)
        if not cond:
            return None
        return getattr(cond.windows, self._key)


class DeepalSteeringWheelHeaterBinarySensor(DeepalBaseBinarySensor):
    """Steering wheel heater binary sensor for international vehicles."""

    _attr_device_class = BinarySensorDeviceClass.HEAT
    _attr_icon = "mdi:steering"

    def __init__(self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any) -> None:
        super().__init__(coordinator, vehicle)
        self._attr_unique_id = f"deepal_{vehicle.car_id}_steering_wheel_heater"
        self._attr_name = f"{vehicle.series_name} Steering Wheel Heater"

    @property
    def is_on(self) -> bool | None:
        """Return True if the steering wheel heater is on."""
        cond = self.coordinator.data.get(self._car_id)
        return cond.climate.steering_wheel_heater_on if cond else None
