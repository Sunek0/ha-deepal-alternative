"""Runtime data for the Deepal Alternative integration."""

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry

from .coordinator import DeepalDataUpdateCoordinator
from .deepal import DeepalClient, DeepalIntlClient


@dataclass
class DeepalRuntimeData:
    """Objects shared by the Deepal entity platforms."""

    client: DeepalClient | DeepalIntlClient
    coordinator: DeepalDataUpdateCoordinator


type DeepalConfigEntry = ConfigEntry[DeepalRuntimeData]
