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
