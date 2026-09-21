"""Binary sensor platform for Changan Deepal integration."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
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
    """Set up Deepal binary sensors based on a config entry."""
    coordinator: DeepalDataUpdateCoordinator = entry.runtime_data.coordinator

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

    _attr_has_entity_name = True

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
        self._attr_translation_key = "charger_plugged"

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
        self._attr_translation_key = "doors_lock_state"

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
        self._attr_translation_key = "tire_alarm"
        self._attr_translation_placeholders = {"position": label}

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
        self._attr_translation_key = "window_open"
        self._attr_translation_placeholders = {"position": label}

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
        self._attr_translation_key = "steering_wheel_heater"

    @property
    def is_on(self) -> bool | None:
        """Return True if the steering wheel heater is on."""
        cond = self.coordinator.data.get(self._car_id)
        return cond.climate.steering_wheel_heater_on if cond else None


@dataclass(frozen=True, kw_only=True)
class DeepalBinarySensorDescription(BinarySensorEntityDescription):
    """Description of an extended international binary sensor."""

    value_fn: Callable[[Any, Any], bool | None]


def _charging(condition: Any, vehicle: Any) -> bool | None:
    status = condition.battery.charging_status
    if status is None:
        return None
    return str(status) not in ("0", "None")


def _not_locked(value: bool | None) -> bool | None:
    return None if value is None else not value


BINARY_SENSORS: tuple[DeepalBinarySensorDescription, ...] = (
    DeepalBinarySensorDescription(
        key="engine",
        name="Engine",
        value_fn=lambda cond, vehicle: cond.engine_on,
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:engine",
    ),
    DeepalBinarySensorDescription(
        key="defrost",
        name="Front Defrost",
        value_fn=lambda cond, vehicle: cond.climate.defrost_on,
        device_class=None,
        icon="mdi:car-defrost-front",
    ),
    DeepalBinarySensorDescription(
        key="connected",
        name="Cloud Connection",
        value_fn=lambda cond, vehicle: cond.connected,
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        icon="mdi:cloud-check",
    ),
    DeepalBinarySensorDescription(
        key="high_beam",
        name="High Beam",
        value_fn=lambda cond, vehicle: cond.lamps.high_beam,
        device_class=BinarySensorDeviceClass.LIGHT,
        icon="mdi:car-high-beam",
    ),
    DeepalBinarySensorDescription(
        key="low_beam",
        name="Low Beam",
        value_fn=lambda cond, vehicle: cond.lamps.low_beam,
        device_class=BinarySensorDeviceClass.LIGHT,
        icon="mdi:car-low-beam",
    ),
    DeepalBinarySensorDescription(
        key="position_lamp",
        name="Position Lamp",
        value_fn=lambda cond, vehicle: cond.lamps.position_lamp,
        device_class=BinarySensorDeviceClass.LIGHT,
        icon="mdi:car-parking-lights",
    ),
    DeepalBinarySensorDescription(
        key="left_turn_signal",
        name="Left Turn Signal",
        value_fn=lambda cond, vehicle: cond.lamps.left_turn,
        device_class=BinarySensorDeviceClass.LIGHT,
        icon="mdi:arrow-left",
    ),
    DeepalBinarySensorDescription(
        key="right_turn_signal",
        name="Right Turn Signal",
        value_fn=lambda cond, vehicle: cond.lamps.right_turn,
        device_class=BinarySensorDeviceClass.LIGHT,
        icon="mdi:arrow-right",
    ),
    DeepalBinarySensorDescription(
        key="any_door_open",
        name="Any Door Open",
        value_fn=lambda cond, vehicle: any(
            (
                cond.doors.driver_door_open,
                cond.doors.passenger_door_open,
                cond.doors.rear_left_door_open,
                cond.doors.rear_right_door_open,
                cond.doors.trunk_open,
            )
        ),
        device_class=BinarySensorDeviceClass.DOOR,
        icon="mdi:car-door",
    ),
    DeepalBinarySensorDescription(
        key="door_front_left",
        name="Front Left Door",
        value_fn=lambda cond, vehicle: cond.doors.driver_door_open,
        device_class=BinarySensorDeviceClass.DOOR,
        icon="mdi:car-door",
    ),
    DeepalBinarySensorDescription(
        key="door_front_right",
        name="Front Right Door",
        value_fn=lambda cond, vehicle: cond.doors.passenger_door_open,
        device_class=BinarySensorDeviceClass.DOOR,
        icon="mdi:car-door",
    ),
    DeepalBinarySensorDescription(
        key="door_rear_left",
        name="Rear Left Door",
        value_fn=lambda cond, vehicle: cond.doors.rear_left_door_open,
        device_class=BinarySensorDeviceClass.DOOR,
        icon="mdi:car-door",
    ),
    DeepalBinarySensorDescription(
        key="door_rear_right",
        name="Rear Right Door",
        value_fn=lambda cond, vehicle: cond.doors.rear_right_door_open,
        device_class=BinarySensorDeviceClass.DOOR,
        icon="mdi:car-door",
    ),
    DeepalBinarySensorDescription(
        key="trunk",
        name="Trunk",
        value_fn=lambda cond, vehicle: cond.doors.trunk_open,
        device_class=BinarySensorDeviceClass.DOOR,
        icon="mdi:car-select",
    ),
    DeepalBinarySensorDescription(
        key="hood",
        name="Hood",
        value_fn=lambda cond, vehicle: cond.doors.hood_open,
        device_class=BinarySensorDeviceClass.DOOR,
        icon="mdi:car-cowl",
    ),
    DeepalBinarySensorDescription(
        key="driver_door_unlocked",
        name="Driver Door Unlocked",
        value_fn=lambda cond, vehicle: _not_locked(cond.doors.driver_locked),
        device_class=BinarySensorDeviceClass.LOCK,
        icon="mdi:car-door-lock",
    ),
    DeepalBinarySensorDescription(
        key="passenger_door_unlocked",
        name="Passenger Door Unlocked",
        value_fn=lambda cond, vehicle: _not_locked(cond.doors.passenger_locked),
        device_class=BinarySensorDeviceClass.LOCK,
        icon="mdi:car-door-lock",
    ),
    DeepalBinarySensorDescription(
        key="dc_gun_connected",
        name="DC Gun Connected",
        value_fn=lambda cond, vehicle: cond.battery.dc_gun_connected,
        device_class=BinarySensorDeviceClass.PLUG,
        icon="mdi:ev-plug-ccs2",
    ),
    DeepalBinarySensorDescription(
        key="charging",
        name="Charging",
        value_fn=_charging,
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        icon="mdi:battery-charging",
    ),
    DeepalBinarySensorDescription(
        key="charge_schedule_enabled",
        name="Charge Schedule Enabled",
        value_fn=lambda cond, vehicle: cond.battery.charge_schedule_enabled,
        device_class=None,
        icon="mdi:calendar-clock",
    ),
    DeepalBinarySensorDescription(
        key="front_left_seat_heating",
        name="Front Left Seat Heating",
        value_fn=lambda cond, vehicle: cond.seats.front_left.heating_level > 0,
        device_class=BinarySensorDeviceClass.HEAT,
        icon="mdi:car-seat-heater",
    ),
    DeepalBinarySensorDescription(
        key="front_right_seat_heating",
        name="Front Right Seat Heating",
        value_fn=lambda cond, vehicle: cond.seats.front_right.heating_level > 0,
        device_class=BinarySensorDeviceClass.HEAT,
        icon="mdi:car-seat-heater",
    ),
    DeepalBinarySensorDescription(
        key="rear_left_seat_heating",
        name="Rear Left Seat Heating",
        value_fn=lambda cond, vehicle: cond.seats.rear_left.heating_level > 0,
        device_class=BinarySensorDeviceClass.HEAT,
        icon="mdi:car-seat-heater",
    ),
    DeepalBinarySensorDescription(
        key="rear_right_seat_heating",
        name="Rear Right Seat Heating",
        value_fn=lambda cond, vehicle: cond.seats.rear_right.heating_level > 0,
        device_class=BinarySensorDeviceClass.HEAT,
        icon="mdi:car-seat-heater",
    ),
    DeepalBinarySensorDescription(
        key="front_left_seat_ventilation",
        name="Front Left Seat Ventilation",
        value_fn=lambda cond, vehicle: cond.seats.front_left.ventilation_level > 0,
        device_class=None,
        icon="mdi:car-seat-cooler",
    ),
    DeepalBinarySensorDescription(
        key="front_right_seat_ventilation",
        name="Front Right Seat Ventilation",
        value_fn=lambda cond, vehicle: cond.seats.front_right.ventilation_level > 0,
        device_class=None,
        icon="mdi:car-seat-cooler",
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
        self._attr_translation_key = description.key
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
