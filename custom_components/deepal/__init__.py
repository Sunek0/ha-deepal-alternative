"""Component for Changan Deepal integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .deepal import DeepalClient, DeepalIntlClient
from .const import (
    DOMAIN,
    PLATFORM_SDA,
    PLATFORM_INTL,
    CONF_PLATFORM,
    CONF_COUNTRY,
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_CAC_TOKEN,
    DEFAULT_COUNTRY,
)
from .coordinator import DeepalDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]


def _build_client(entry: ConfigEntry) -> DeepalClient | DeepalIntlClient:
    """Build the API client for the entry's platform."""
    if entry.data.get(CONF_PLATFORM, PLATFORM_SDA) == PLATFORM_INTL:
        client = DeepalIntlClient(
            country=entry.data.get(CONF_COUNTRY) or DEFAULT_COUNTRY,
        )
        client.access_token = entry.data[CONF_ACCESS_TOKEN]
        client.refresh_token = entry.data.get(CONF_REFRESH_TOKEN) or None
        client.cac_token = entry.data.get(CONF_CAC_TOKEN) or None
        return client

    return DeepalClient(access_token=entry.data[CONF_ACCESS_TOKEN])


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Changan Deepal from a config entry."""
    client = _build_client(entry)
    coordinator = DeepalDataUpdateCoordinator(hass, entry, client)

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        client = data["client"]
        await client.close()

    return unload_ok
