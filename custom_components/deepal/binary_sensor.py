"""Binary sensor platform for Changan Deepal integration."""

from collections.abc import Callable
from dataclasses import dataclass
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

            entities.extend(
                DeepalBinarySensor(coordinator, vehicle, description)
                for description in BINARY_SENSORS
            )

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


@dataclass(frozen=True)
class DeepalBinarySensorDescription:
    """Description of an extended international binary sensor."""

    key: str
    name: str
    value_fn: Callable[[Any, Any], bool | None]
    device_class: BinarySensorDeviceClass | None = None
    icon: str | None = None


def _charging(condition: Any, vehicle: Any) -> bool | None:
    status = condition.battery.charging_status
    if status is None:
        return None
    return str(status) not in ("0", "None")


def _not_locked(value: bool | None) -> bool | None:
    return None if value is None else not value


BINARY_SENSORS: tuple[DeepalBinarySensorDescription, ...] = (
    DeepalBinarySensorDescription(
        "engine", "Engine", lambda cond, vehicle: cond.engine_on,
        BinarySensorDeviceClass.RUNNING, "mdi:engine",
    ),
    DeepalBinarySensorDescription(
        "defrost", "Front Defrost", lambda cond, vehicle: cond.climate.defrost_on,
        None, "mdi:car-defrost-front",
    ),
    DeepalBinarySensorDescription(
        "connected", "Cloud Connection", lambda cond, vehicle: cond.connected,
        BinarySensorDeviceClass.CONNECTIVITY, "mdi:cloud-check",
    ),
    DeepalBinarySensorDescription(
        "high_beam", "High Beam", lambda cond, vehicle: cond.lamps.high_beam,
        BinarySensorDeviceClass.LIGHT, "mdi:car-high-beam",
    ),
    DeepalBinarySensorDescription(
        "low_beam", "Low Beam", lambda cond, vehicle: cond.lamps.low_beam,
        BinarySensorDeviceClass.LIGHT, "mdi:car-low-beam",
    ),
    DeepalBinarySensorDescription(
        "position_lamp", "Position Lamp",
        lambda cond, vehicle: cond.lamps.position_lamp,
        BinarySensorDeviceClass.LIGHT, "mdi:car-parking-lights",
    ),
    DeepalBinarySensorDescription(
        "left_turn_signal", "Left Turn Signal",
        lambda cond, vehicle: cond.lamps.left_turn,
        BinarySensorDeviceClass.LIGHT, "mdi:arrow-left",
    ),
    DeepalBinarySensorDescription(
        "right_turn_signal", "Right Turn Signal",
        lambda cond, vehicle: cond.lamps.right_turn,
        BinarySensorDeviceClass.LIGHT, "mdi:arrow-right",
    ),
    DeepalBinarySensorDescription(
        "any_door_open", "Any Door Open",
        lambda cond, vehicle: any(
            (
                cond.doors.driver_door_open,
                cond.doors.passenger_door_open,
                cond.doors.rear_left_door_open,
                cond.doors.rear_right_door_open,
                cond.doors.trunk_open,
            )
        ),
        BinarySensorDeviceClass.DOOR, "mdi:car-door",
    ),
    DeepalBinarySensorDescription(
        "door_front_left", "Front Left Door",
        lambda cond, vehicle: cond.doors.driver_door_open,
        BinarySensorDeviceClass.DOOR, "mdi:car-door",
    ),
    DeepalBinarySensorDescription(
        "door_front_right", "Front Right Door",
        lambda cond, vehicle: cond.doors.passenger_door_open,
        BinarySensorDeviceClass.DOOR, "mdi:car-door",
    ),
    DeepalBinarySensorDescription(
        "door_rear_left", "Rear Left Door",
        lambda cond, vehicle: cond.doors.rear_left_door_open,
        BinarySensorDeviceClass.DOOR, "mdi:car-door",
    ),
    DeepalBinarySensorDescription(
        "door_rear_right", "Rear Right Door",
        lambda cond, vehicle: cond.doors.rear_right_door_open,
        BinarySensorDeviceClass.DOOR, "mdi:car-door",
    ),
    DeepalBinarySensorDescription(
        "trunk", "Trunk", lambda cond, vehicle: cond.doors.trunk_open,
        BinarySensorDeviceClass.DOOR, "mdi:car-back",
    ),
    DeepalBinarySensorDescription(
        "hood", "Hood", lambda cond, vehicle: cond.doors.hood_open,
        BinarySensorDeviceClass.DOOR, "mdi:car-cowl",
    ),
    DeepalBinarySensorDescription(
        "driver_door_unlocked", "Driver Door Unlocked",
        lambda cond, vehicle: _not_locked(cond.doors.driver_locked),
        BinarySensorDeviceClass.LOCK, "mdi:car-door-lock",
    ),
    DeepalBinarySensorDescription(
        "passenger_door_unlocked", "Passenger Door Unlocked",
        lambda cond, vehicle: _not_locked(cond.doors.passenger_locked),
        BinarySensorDeviceClass.LOCK, "mdi:car-door-lock",
    ),
    DeepalBinarySensorDescription(
        "dc_gun_connected", "DC Gun Connected",
        lambda cond, vehicle: cond.battery.dc_gun_connected,
        BinarySensorDeviceClass.PLUG, "mdi:ev-plug-ccs2",
    ),
    DeepalBinarySensorDescription(
        "charging", "Charging", _charging,
        BinarySensorDeviceClass.BATTERY_CHARGING, "mdi:battery-charging",
    ),
    DeepalBinarySensorDescription(
        "charge_schedule_enabled", "Charge Schedule Enabled",
        lambda cond, vehicle: cond.battery.charge_schedule_enabled,
        None, "mdi:calendar-clock",
    ),
    DeepalBinarySensorDescription(
        "front_left_seat_heating", "Front Left Seat Heating",
        lambda cond, vehicle: cond.seats.front_left.heating_level > 0,
        BinarySensorDeviceClass.HEAT, "mdi:car-seat-heater",
    ),
    DeepalBinarySensorDescription(
        "front_right_seat_heating", "Front Right Seat Heating",
        lambda cond, vehicle: cond.seats.front_right.heating_level > 0,
        BinarySensorDeviceClass.HEAT, "mdi:car-seat-heater",
    ),
    DeepalBinarySensorDescription(
        "rear_left_seat_heating", "Rear Left Seat Heating",
        lambda cond, vehicle: cond.seats.rear_left.heating_level > 0,
        BinarySensorDeviceClass.HEAT, "mdi:car-seat-heater",
    ),
    DeepalBinarySensorDescription(
        "rear_right_seat_heating", "Rear Right Seat Heating",
        lambda cond, vehicle: cond.seats.rear_right.heating_level > 0,
        BinarySensorDeviceClass.HEAT, "mdi:car-seat-heater",
    ),
    DeepalBinarySensorDescription(
        "front_left_seat_ventilation", "Front Left Seat Ventilation",
        lambda cond, vehicle: cond.seats.front_left.ventilation_level > 0,
        None, "mdi:car-seat-cooler",
    ),
    DeepalBinarySensorDescription(
        "front_right_seat_ventilation", "Front Right Seat Ventilation",
        lambda cond, vehicle: cond.seats.front_right.ventilation_level > 0,
        None, "mdi:car-seat-cooler",
    ),
)


class DeepalBinarySensor(DeepalBaseBinarySensor):
    """Extended international binary sensor driven by a description."""

    entity_description: DeepalBinarySensorDescription

    def __init__(
        self,
        coordinator: DeepalDataUpdateCoordinator,
        vehicle: Any,
        description: DeepalBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, vehicle)
        self.entity_description = description
        self._attr_unique_id = f"deepal_{vehicle.car_id}_{description.key}"
        self._attr_name = f"{vehicle.series_name} {description.name}"
        if description.device_class is not None:
            self._attr_device_class = description.device_class
        if description.icon is not None:
            self._attr_icon = description.icon

    @property
    def is_on(self) -> bool | None:
        """Return the described state."""
        cond = self.coordinator.data.get(self._car_id)
        if not cond:
            return None
        return self.entity_description.value_fn(cond, self.vehicle)
