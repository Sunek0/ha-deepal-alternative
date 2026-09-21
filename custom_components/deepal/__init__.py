"""Component for Changan Deepal integration."""

import logging
import secrets
from datetime import timedelta

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .deepal import DeepalClient, DeepalIntlClient
from .const import (
    PLATFORM_SDA,
    PLATFORM_INTL,
    CONF_PLATFORM,
    CONF_COUNTRY,
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_CAC_TOKEN,
    CONF_PRIVATE_KEY,
    CONF_PUBLIC_KEY,
    CONF_CONTROL_PIN,
    CONF_DEVICE_ID,
    CONF_USER_ID,
    CONF_OS_VERSION,
    CONF_ENVIRONMENT,
    CONF_SEND_TIMESTAMPS,
    CONF_SCAN_INTERVAL,
    CONF_ENABLE_API_LOGGING,
    DEFAULT_COUNTRY,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_OS_VERSION,
    DEFAULT_ENVIRONMENT,
    DEFAULT_SEND_TIMESTAMPS,
)
from .coordinator import DeepalDataUpdateCoordinator
from .runtime_data import DeepalConfigEntry, DeepalRuntimeData

_LOGGER = logging.getLogger(__name__)


def _build_client(entry: DeepalConfigEntry) -> DeepalClient | DeepalIntlClient:
    """Build the API client for the entry's platform."""
    if entry.data.get(CONF_PLATFORM, PLATFORM_SDA) == PLATFORM_INTL:
        client = DeepalIntlClient(
            country=entry.data.get(CONF_COUNTRY) or DEFAULT_COUNTRY,
            os_version=entry.options.get(CONF_OS_VERSION, DEFAULT_OS_VERSION),
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
        private_key = entry.data.get(CONF_PRIVATE_KEY) or None
        if private_key:
            try:
                client.set_login_keypair(
                    private_key, entry.data.get(CONF_PUBLIC_KEY) or None
                )
            except (ValueError, TypeError) as err:
                _LOGGER.warning(
                    "Deepal entry %s stores an unusable login private key (%s); "
                    "command signing stays disabled until the next login",
                    entry.entry_id,
                    err,
                )
                client.private_key_pem = private_key
        client.control_pin = (
            entry.options.get(CONF_CONTROL_PIN)
            or entry.data.get(CONF_CONTROL_PIN)
            or None
        )
        client.device_id = entry.data.get(CONF_DEVICE_ID) or client.device_id
        return client

    return DeepalClient(access_token=entry.data[CONF_ACCESS_TOKEN])


def _platforms(entry: DeepalConfigEntry) -> list[Platform]:
    """Return the entity platforms for an entry."""
    platforms = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.IMAGE]
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


async def async_setup_entry(hass: HomeAssistant, entry: DeepalConfigEntry) -> bool:
    """Set up Changan Deepal from a config entry."""
    if entry.data.get(CONF_PLATFORM, PLATFORM_SDA) == PLATFORM_INTL:
        data_updates = dict(entry.data)
        if not data_updates.get(CONF_DEVICE_ID):
            data_updates[CONF_DEVICE_ID] = secrets.token_hex(16)
        if not data_updates.get(CONF_PUBLIC_KEY):
            private_key = data_updates.get(CONF_PRIVATE_KEY)
            if private_key:
                try:
                    data_updates[CONF_PUBLIC_KEY] = (
                        DeepalIntlClient.public_key_body_from_private(private_key)
                    )
                except (ValueError, TypeError) as err:
                    _LOGGER.warning(
                        "Could not derive the login public key stored in Deepal "
                        "entry %s: %s",
                        entry.entry_id,
                        err,
                    )
        if data_updates != entry.data:
            hass.config_entries.async_update_entry(entry, data=data_updates)

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

    entry.runtime_data = DeepalRuntimeData(client=client, coordinator=coordinator)

    platforms = _platforms(entry)
    _LOGGER.debug(
        "Deepal setting up platforms: %s", [platform.value for platform in platforms]
    )
    await hass.config_entries.async_forward_entry_setups(entry, platforms)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: DeepalConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, _platforms(entry))

    if unload_ok:
        await entry.runtime_data.client.close()

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: DeepalConfigEntry) -> None:
    """Log out the international session before removing the entry.

    Best-effort: the logout and the client teardown are wrapped so a network
    or configuration failure is only logged and never blocks the removal.
    """
    if entry.data.get(CONF_PLATFORM, PLATFORM_SDA) != PLATFORM_INTL:
        return
    if not entry.data.get(CONF_ACCESS_TOKEN):
        return

    client = None
    try:
        client = _build_client(entry)
        await client.logout()
    except Exception as err:
        _LOGGER.warning("Deepal logout on entry removal failed: %s", err)
    finally:
        if client is not None:
            try:
                await client.close()
            except Exception as err:
                _LOGGER.warning("Deepal client close on entry removal failed: %s", err)
