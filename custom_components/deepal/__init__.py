"""Component for Changan Deepal integration."""

import logging
import secrets
from datetime import timedelta

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
    CONF_PRIVATE_KEY,
    CONF_CONTROL_PIN,
    CONF_DEVICE_ID,
    CONF_USER_ID,
    CONF_OS_VERSION,
    CONF_TSP_TOKEN_SOURCE,
    CONF_ENVIRONMENT,
    CONF_SEND_TIMESTAMPS,
    CONF_SCAN_INTERVAL,
    CONF_ENABLE_API_LOGGING,
    DEFAULT_COUNTRY,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_OS_VERSION,
    DEFAULT_TSP_TOKEN_SOURCE,
    DEFAULT_ENVIRONMENT,
    DEFAULT_SEND_TIMESTAMPS,
)
from .coordinator import DeepalDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


def _build_client(entry: ConfigEntry) -> DeepalClient | DeepalIntlClient:
    """Build the API client for the entry's platform."""
    if entry.data.get(CONF_PLATFORM, PLATFORM_SDA) == PLATFORM_INTL:
        client = DeepalIntlClient(
            country=entry.data.get(CONF_COUNTRY) or DEFAULT_COUNTRY,
            os_version=entry.options.get(CONF_OS_VERSION, DEFAULT_OS_VERSION),
            tsp_token_source=entry.options.get(
                CONF_TSP_TOKEN_SOURCE, DEFAULT_TSP_TOKEN_SOURCE
            ),
            environment=entry.options.get(CONF_ENVIRONMENT, DEFAULT_ENVIRONMENT),
            send_timestamps=bool(
                entry.options.get(CONF_SEND_TIMESTAMPS, DEFAULT_SEND_TIMESTAMPS)
            ),
            enable_api_logging=bool(
                entry.options.get(CONF_ENABLE_API_LOGGING, False)
            ),
        )
        client.access_token = entry.data[CONF_ACCESS_TOKEN]
        client.refresh_token = entry.data.get(CONF_REFRESH_TOKEN) or None
        client.cac_token = entry.data.get(CONF_CAC_TOKEN) or None
        client.user_id = entry.data.get(CONF_USER_ID) or None
        client.private_key_pem = entry.data.get(CONF_PRIVATE_KEY) or None
        client.control_pin = (
            entry.options.get(CONF_CONTROL_PIN)
            or entry.data.get(CONF_CONTROL_PIN)
            or None
        )
        client.device_id = entry.data.get(CONF_DEVICE_ID) or client.device_id
        return client

    return DeepalClient(access_token=entry.data[CONF_ACCESS_TOKEN])


def _platforms(entry: ConfigEntry) -> list[Platform]:
    """Return the entity platforms for an entry."""
    platforms = [Platform.SENSOR, Platform.BINARY_SENSOR]
    if (
        entry.data.get(CONF_PLATFORM, PLATFORM_SDA) == PLATFORM_INTL
        and entry.data.get(CONF_PRIVATE_KEY)
    ):
        platforms.extend(
            [
                Platform.CLIMATE,
                Platform.LOCK,
                Platform.COVER,
                Platform.BUTTON,
                Platform.NUMBER,
                Platform.SWITCH,
                Platform.TIME,
            ]
        )
    return platforms


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Changan Deepal from a config entry."""
    if (
        entry.data.get(CONF_PLATFORM, PLATFORM_SDA) == PLATFORM_INTL
        and not entry.data.get(CONF_DEVICE_ID)
    ):
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_DEVICE_ID: secrets.token_hex(16)},
        )

    client = _build_client(entry)
    coordinator = DeepalDataUpdateCoordinator(
        hass,
        entry,
        client,
        update_interval=timedelta(
            seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        ),
    )

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, _platforms(entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, _platforms(entry))

    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        client = data["client"]
        await client.close()

    return unload_ok
