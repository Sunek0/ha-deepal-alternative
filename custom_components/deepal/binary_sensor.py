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
from homeassistant.const import EntityCategory
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, DEFAULT_MODEL
from .charging import charging_flag
from .coordinator import DeepalDataUpdateCoordinator
from .deepal import DeepalIntlClient
from .runtime_data import DeepalConfigEntry
from .vehicle_model import is_s05

# Coordinator is used to centralize the data updates
PARALLEL_UPDATES = 0

# The S05 has no rear seat heating hardware (the app disables those controls).
S05_UNSUPPORTED_BINARY_SENSOR_KEYS = frozenset(
    {
        "rear_left_seat_heating",
        "rear_right_seat_heating",
    }
)

# Keys retired from the platform. Their entity-registry entries are removed on
# setup so they do not linger as orphaned entities: the reference S05 does not
# support the front defrost signal, and its airbag warning bit keeps toggling on
# healthy cars while the coolant bit is a fuel-vehicle signal, so both warning
# entities were retired again on 2026-10-18 (their codes stay visible in the
# unmapped-parameter diagnostics).
REMOVED_BINARY_SENSOR_KEYS = frozenset(
    {"defrost", "warning_airbag", "warning_coolant_temperature"}
)


def build_binary_sensors(
    coordinator: DeepalDataUpdateCoordinator, vehicle: Any
) -> list[BinarySensorEntity]:
    """Build the binary sensors for one vehicle, skipping what its model lacks."""
    entities: list[BinarySensorEntity] = [
        DeepalChargerPluggedBinarySensor(coordinator, vehicle),
        DeepalDoorsLockedBinarySensor(coordinator, vehicle),
    ]

    s05 = is_s05(vehicle)

    if isinstance(coordinator.client, DeepalIntlClient):
        for key in ("front_left", "front_right", "rear_left", "rear_right"):
            entities.append(DeepalTireAlarmBinarySensor(coordinator, vehicle, key))

        for key in (
            "front_left_open",
            "front_right_open",
            "rear_left_open",
            "rear_right_open",
        ):
            entities.append(DeepalWindowBinarySensor(coordinator, vehicle, key))

        entities.append(DeepalSteeringWheelHeaterBinarySensor(coordinator, vehicle))

        entities.extend(
            DeepalBinarySensor(coordinator, vehicle, description)
            for description in BINARY_SENSORS
            if not (s05 and description.key in S05_UNSUPPORTED_BINARY_SENSOR_KEYS)
        )

    return entities


def _remove_retired_entities(registry: Any, vehicle: Any) -> None:
    """Remove entity-registry entries for keys retired from this platform."""
    for key in REMOVED_BINARY_SENSOR_KEYS:
        unique_id = f"deepal_{vehicle.car_id}_{key}"
        if entity_id := registry.async_get_entity_id(
            "binary_sensor", DOMAIN, unique_id
        ):
            registry.async_remove(entity_id)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeepalConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Deepal binary sensors based on a config entry."""
    coordinator: DeepalDataUpdateCoordinator = entry.runtime_data.coordinator
    registry = er.async_get(hass)

    entities: list[BinarySensorEntity] = []

    for vehicle in coordinator.vehicles:
        _remove_retired_entities(registry, vehicle)
        entities.extend(build_binary_sensors(coordinator, vehicle))

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
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any, key: str) -> None:
        super().__init__(coordinator, vehicle)
        self._key = key
        self._attr_unique_id = f"deepal_{vehicle.car_id}_tire_{key}_alarm"
        self._attr_translation_key = f"tire_alarm_{key}"

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

    def __init__(self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any, key: str) -> None:
        super().__init__(coordinator, vehicle)
        self._key = key
        self._attr_unique_id = f"deepal_{vehicle.car_id}_window_{key}"
        self._attr_translation_key = f"window_open_{key.removesuffix('_open')}"

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
    enabled_default: bool = True


def _seat_level_on(position: str, field: str) -> Callable[[Any, Any], bool | None]:
    """Return a value function for a seat function whose level may be unknown."""

    def _value(condition: Any, vehicle: Any) -> bool | None:
        level = getattr(getattr(condition.seats, position), field)
        if level is None or not 0 <= level <= 3:
            return None
        return level > 0

    return _value


def _charging(condition: Any, vehicle: Any) -> bool | None:
    return charging_flag(condition)


def _not_locked(value: bool | None) -> bool | None:
    return None if value is None else not value


BINARY_SENSORS: tuple[DeepalBinarySensorDescription, ...] = (
    DeepalBinarySensorDescription(
        key="engine",
        name="Engine",
        value_fn=lambda cond, vehicle: cond.engine_on,
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    DeepalBinarySensorDescription(
        key="climate_on",
        name="Climate On",
        value_fn=lambda cond, vehicle: cond.climate.power_on,
        device_class=None,
    ),
    DeepalBinarySensorDescription(
        key="connected",
        name="Cloud Connection",
        value_fn=lambda cond, vehicle: cond.connected,
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
    DeepalBinarySensorDescription(
        key="high_beam",
        name="High Beam",
        value_fn=lambda cond, vehicle: cond.lamps.high_beam,
        device_class=BinarySensorDeviceClass.LIGHT,
    ),
    DeepalBinarySensorDescription(
        key="low_beam",
        name="Low Beam",
        value_fn=lambda cond, vehicle: cond.lamps.low_beam,
        device_class=BinarySensorDeviceClass.LIGHT,
    ),
    DeepalBinarySensorDescription(
        key="position_lamp",
        name="Position Lamp",
        value_fn=lambda cond, vehicle: cond.lamps.position_lamp,
        device_class=BinarySensorDeviceClass.LIGHT,
    ),
    DeepalBinarySensorDescription(
        key="left_turn_signal",
        name="Left Turn Signal",
        value_fn=lambda cond, vehicle: cond.lamps.left_turn,
        device_class=BinarySensorDeviceClass.LIGHT,
    ),
    DeepalBinarySensorDescription(
        key="right_turn_signal",
        name="Right Turn Signal",
        value_fn=lambda cond, vehicle: cond.lamps.right_turn,
        device_class=BinarySensorDeviceClass.LIGHT,
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
    ),
    DeepalBinarySensorDescription(
        key="door_front_left",
        name="Front Left Door",
        value_fn=lambda cond, vehicle: cond.doors.driver_door_open,
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    DeepalBinarySensorDescription(
        key="door_front_right",
        name="Front Right Door",
        value_fn=lambda cond, vehicle: cond.doors.passenger_door_open,
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    DeepalBinarySensorDescription(
        key="door_rear_left",
        name="Rear Left Door",
        value_fn=lambda cond, vehicle: cond.doors.rear_left_door_open,
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    DeepalBinarySensorDescription(
        key="door_rear_right",
        name="Rear Right Door",
        value_fn=lambda cond, vehicle: cond.doors.rear_right_door_open,
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    DeepalBinarySensorDescription(
        key="trunk",
        name="Trunk",
        value_fn=lambda cond, vehicle: cond.doors.trunk_open,
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    DeepalBinarySensorDescription(
        key="hood",
        name="Hood",
        value_fn=lambda cond, vehicle: cond.doors.hood_open,
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    DeepalBinarySensorDescription(
        key="driver_door_unlocked",
        name="Driver Door Unlocked",
        value_fn=lambda cond, vehicle: _not_locked(cond.doors.driver_locked),
        device_class=BinarySensorDeviceClass.LOCK,
    ),
    DeepalBinarySensorDescription(
        key="passenger_door_unlocked",
        name="Passenger Door Unlocked",
        value_fn=lambda cond, vehicle: _not_locked(cond.doors.passenger_locked),
        device_class=BinarySensorDeviceClass.LOCK,
    ),
    DeepalBinarySensorDescription(
        key="ac_gun_connected",
        name="AC Gun Connected",
        value_fn=lambda cond, vehicle: cond.battery.ac_gun_connected,
        device_class=BinarySensorDeviceClass.PLUG,
    ),
    DeepalBinarySensorDescription(
        key="dc_gun_connected",
        name="DC Gun Connected",
        value_fn=lambda cond, vehicle: cond.battery.dc_gun_connected,
        device_class=BinarySensorDeviceClass.PLUG,
    ),
    DeepalBinarySensorDescription(
        key="charging",
        name="Charging",
        value_fn=_charging,
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
    ),
    DeepalBinarySensorDescription(
        key="charge_schedule_enabled",
        name="Charge Schedule Enabled",
        value_fn=lambda cond, vehicle: cond.battery.charge_schedule_enabled,
        device_class=None,
    ),
    DeepalBinarySensorDescription(
        key="front_left_seat_heating",
        name="Front Left Seat Heating",
        value_fn=_seat_level_on("front_left", "heating_level"),
        device_class=BinarySensorDeviceClass.HEAT,
    ),
    DeepalBinarySensorDescription(
        key="front_right_seat_heating",
        name="Front Right Seat Heating",
        value_fn=_seat_level_on("front_right", "heating_level"),
        device_class=BinarySensorDeviceClass.HEAT,
    ),
    DeepalBinarySensorDescription(
        key="rear_left_seat_heating",
        name="Rear Left Seat Heating",
        value_fn=_seat_level_on("rear_left", "heating_level"),
        device_class=BinarySensorDeviceClass.HEAT,
    ),
    DeepalBinarySensorDescription(
        key="rear_right_seat_heating",
        name="Rear Right Seat Heating",
        value_fn=_seat_level_on("rear_right", "heating_level"),
        device_class=BinarySensorDeviceClass.HEAT,
    ),
    DeepalBinarySensorDescription(
        key="front_left_seat_ventilation",
        name="Front Left Seat Ventilation",
        value_fn=_seat_level_on("front_left", "ventilation_level"),
        device_class=None,
    ),
    DeepalBinarySensorDescription(
        key="front_right_seat_ventilation",
        name="Front Right Seat Ventilation",
        value_fn=_seat_level_on("front_right", "ventilation_level"),
        device_class=None,
    ),
    DeepalBinarySensorDescription(
        key="key_battery_low",
        name="Key Fob Battery Low",
        value_fn=lambda cond, vehicle: cond.key_battery_low,
        device_class=BinarySensorDeviceClass.BATTERY,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeepalBinarySensorDescription(
        key="air_recirculation",
        name="Air Recirculation",
        value_fn=lambda cond, vehicle: cond.air_recirculation,
        device_class=None,
    ),
    DeepalBinarySensorDescription(
        key="rear_fog_lamp",
        name="Rear Fog Lamp",
        value_fn=lambda cond, vehicle: cond.lamps.rear_fog,
        device_class=BinarySensorDeviceClass.LIGHT,
    ),
    # Dashboard warning lights. They stay unknown when the vehicle does not
    # report them, so an absent signal is never exposed as healthy.
    DeepalBinarySensorDescription(
        key="warning_12v_battery",
        name="12 V Battery Warning Light",
        value_fn=lambda cond, vehicle: cond.warnings.battery_12v,
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeepalBinarySensorDescription(
        key="warning_tpms",
        name="Tire Pressure Warning Light",
        value_fn=lambda cond, vehicle: cond.warnings.tpms,
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeepalBinarySensorDescription(
        key="warning_abs",
        name="ABS Warning Light",
        value_fn=lambda cond, vehicle: cond.warnings.abs,
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeepalBinarySensorDescription(
        key="warning_brake_fluid",
        name="Brake Fluid Warning Light",
        value_fn=lambda cond, vehicle: cond.warnings.brake_fluid,
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeepalBinarySensorDescription(
        key="warning_brake",
        name="Brake Warning Light",
        value_fn=lambda cond, vehicle: cond.warnings.brake,
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeepalBinarySensorDescription(
        key="warning_eps",
        name="Power Steering Warning Light",
        value_fn=lambda cond, vehicle: cond.warnings.eps,
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeepalBinarySensorDescription(
        key="warning_power_limit",
        name="Power Limit Warning Light",
        value_fn=lambda cond, vehicle: cond.warnings.power_limit,
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeepalBinarySensorDescription(
        key="warning_power_system",
        name="Power System Warning Light",
        value_fn=lambda cond, vehicle: cond.warnings.power_system,
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeepalBinarySensorDescription(
        key="warning_traction_battery_low",
        name="Traction Battery Low Warning Light",
        value_fn=lambda cond, vehicle: cond.warnings.traction_battery_low,
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
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
        self._attr_entity_registry_enabled_default = description.enabled_default
        if description.device_class is not None:
            self._attr_device_class = description.device_class

    @property
    def is_on(self) -> bool | None:
        """Return the described state."""
        cond = self.coordinator.data.get(self._car_id)
        if not cond:
            return None
        return self.entity_description.value_fn(cond, self.vehicle)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the tracked charging sessions on the charging sensor."""
        if self.entity_description.key != "charging":
            return None
        manager = getattr(self.coordinator, "charging", None)
        if manager is None:
            return None
        return manager.attributes(self._car_id) or None
