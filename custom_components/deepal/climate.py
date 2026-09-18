"""Climate platform for Changan Deepal integration."""

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, DEFAULT_MODEL
from .coordinator import DeepalDataUpdateCoordinator
from .deepal import DeepalError, DeepalIntlClient


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Deepal climate entity for international entries."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: DeepalDataUpdateCoordinator = data["coordinator"]

    if not isinstance(coordinator.client, DeepalIntlClient):
        return
    if not coordinator.client.private_key_pem:
        return

    async_add_entities(
        DeepalCabinClimateEntity(coordinator, vehicle)
        for vehicle in coordinator.vehicles
    )


class DeepalCabinClimateEntity(
    CoordinatorEntity[DeepalDataUpdateCoordinator], ClimateEntity
):
    """Cabin climate control for international vehicles."""

    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT_COOL]
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 16
    _attr_max_temp = 30
    _attr_icon = "mdi:air-conditioner"

    def __init__(self, coordinator: DeepalDataUpdateCoordinator, vehicle: Any) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self.vehicle = vehicle
        self._car_id = vehicle.car_id
        self._attr_unique_id = f"deepal_{vehicle.car_id}_cabin_climate"
        self._attr_name = f"{vehicle.series_name} Cabin Climate"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.vehicle.car_id)},
            name=self.vehicle.series_name or DEFAULT_MODEL,
            manufacturer=MANUFACTURER,
            model=self.vehicle.series_name or DEFAULT_MODEL,
        )

    @property
    def _condition(self):
        return self.coordinator.data.get(self._car_id)

    @property
    def _is_mqtt(self) -> bool:
        """Return whether the vehicle uses the MQTT telemetry backend."""
        return (self.vehicle.protocol_type or "").upper() == "MQTT"

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return no features for MQTT-backed vehicles until controls are verified."""
        if self._is_mqtt:
            return ClimateEntityFeature(0)
        return ClimateEntityFeature.TARGET_TEMPERATURE

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return the current HVAC mode."""
        cond = self._condition
        if not cond:
            return None
        return HVACMode.HEAT_COOL if cond.climate.power_on else HVACMode.OFF

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        cond = self._condition
        return cond.climate.target_temperature_c if cond else None

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
            return
        if hvac_mode == HVACMode.HEAT_COOL:
            await self.async_turn_on()
            return
        raise HomeAssistantError(f"Unsupported HVAC mode: {hvac_mode}")

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature."""
        temperature = kwargs.get("temperature")
        if temperature is None:
            return
        await self._async_send(True, float(temperature))

    async def async_turn_on(self) -> None:
        """Turn the AC on."""
        await self._async_send(True, self.target_temperature or 21.0)

    async def async_turn_off(self) -> None:
        """Turn the AC off."""
        await self._async_send(False, self.target_temperature or 21.0)

    async def _async_send(self, enabled: bool, temperature: float) -> None:
        if self._is_mqtt:
            raise HomeAssistantError(
                "S05 MQTT vehicles are read-only in this version"
            )
        try:
            await self.coordinator.async_execute_command(
                self._car_id,
                lambda: self.coordinator.client.control_air_conditioner(
                    self._car_id, enabled, temperature
                ),
            )
        except HomeAssistantError:
            raise
        except DeepalError as err:
            raise HomeAssistantError(f"Deepal climate command failed: {err}") from err
