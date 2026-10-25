"""Runtime data for the Deepal Alternative integration."""

from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform

from .charging import ChargingSessionManager
from .coordinator import DeepalDataUpdateCoordinator
from .deepal import DeepalClient, DeepalIntlClient


@dataclass
class DeepalRuntimeData:
    """Objects shared by the Deepal entity platforms."""

    client: DeepalClient | DeepalIntlClient
    coordinator: DeepalDataUpdateCoordinator
    charging: ChargingSessionManager | None = None
    model_assets: Any = None
    capture: Any = None
    platforms: list[Platform] | None = None


type DeepalConfigEntry = ConfigEntry[DeepalRuntimeData]
