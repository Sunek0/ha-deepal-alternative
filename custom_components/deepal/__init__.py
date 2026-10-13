"""Component for Changan Deepal integration."""

import logging
import secrets
from datetime import timedelta

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.storage import Store

from .charging import ChargingSessionManager
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
    CONF_PUBLIC_KEY,
    CONF_CONTROL_PIN,
    CONF_DEVICE_ID,
    CONF_USER_ID,
    CONF_ENVIRONMENT,
    CONF_SCAN_INTERVAL,
    CONF_ENABLE_API_LOGGING,
    CONF_WAKE,
    DEFAULT_COUNTRY,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_ENVIRONMENT,
    DEFAULT_WAKE,
)
from .coordinator import DeepalDataUpdateCoordinator
from .runtime_data import DeepalConfigEntry, DeepalRuntimeData

_LOGGER = logging.getLogger(__name__)


def _charging_store(hass: HomeAssistant, entry: DeepalConfigEntry) -> Store:
    """Return the per-entry store of the charging-session tracker."""
    return Store(hass, 1, f"{DOMAIN}.charging.{entry.entry_id}")


def _build_client(
    hass: HomeAssistant, entry: DeepalConfigEntry
) -> DeepalClient | DeepalIntlClient:
    """Build the API client for the entry's platform.

    Both clients share Home Assistant's httpx session; the SDK keeps an
    injected client open and leaves closing it to Home Assistant.
    """
    if entry.data.get(CONF_PLATFORM, PLATFORM_SDA) == PLATFORM_INTL:
        client = DeepalIntlClient(
            country=entry.data.get(CONF_COUNTRY) or DEFAULT_COUNTRY,
            environment=(
                entry.options.get(CONF_ENVIRONMENT)
                or entry.data.get(CONF_ENVIRONMENT)
                or DEFAULT_ENVIRONMENT
            ),
            enable_api_logging=bool(
                entry.options.get(CONF_ENABLE_API_LOGGING, False)
            ),
            httpx_client=get_async_client(hass),
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

    return DeepalClient(
        access_token=entry.data[CONF_ACCESS_TOKEN],
        httpx_client=get_async_client(hass),
    )


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


ISSUE_MQTT_USER_ID_MISSING = "mqtt_user_id_missing"


def _mqtt_reauth_issue_id(entry: DeepalConfigEntry) -> str:
    """Return the repair issue id for the entry's MQTT user id problem."""
    return f"{ISSUE_MQTT_USER_ID_MISSING}_{entry.entry_id}"


def _sync_mqtt_reauth_issue(
    hass: HomeAssistant,
    entry: DeepalConfigEntry,
    coordinator: DeepalDataUpdateCoordinator,
) -> None:
    """Create or clear the repair asking for a re-authentication.

    MQTT-backed vehicles need the account user id returned by the login;
    entries configured with pasted tokens do not have it and silently fall
    back to the stale REST condition, so the user is asked to re-authenticate.
    """
    client = coordinator.client
    issue_id = _mqtt_reauth_issue_id(entry)
    needs_reauth = (
        isinstance(client, DeepalIntlClient)
        and not client.user_id
        and any(client.is_mqtt_vehicle(vehicle) for vehicle in coordinator.vehicles)
    )
    if not needs_reauth:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return

    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        data={"entry_id": entry.entry_id},
        is_fixable=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_MQTT_USER_ID_MISSING,
        translation_placeholders={"name": entry.title},
    )


def _remove_stale_vehicle_registry(
    hass: HomeAssistant,
    entry: DeepalConfigEntry,
    coordinator: DeepalDataUpdateCoordinator,
) -> None:
    """Drop registry entries of vehicles the account no longer reports.

    Runs on every setup and is idempotent: only entries whose vehicle is not
    part of the freshly fetched vehicle list are removed.
    """
    current = {vehicle.car_id for vehicle in coordinator.vehicles}
    prefixes = {f"deepal_{car_id}_" for car_id in current}

    entity_registry = er.async_get(hass)
    for entity_entry in er.async_entries_for_config_entry(
        entity_registry, entry.entry_id
    ):
        unique_id = entity_entry.unique_id or ""
        if not unique_id.startswith("deepal_"):
            continue
        if any(unique_id.startswith(prefix) for prefix in prefixes):
            continue
        entity_registry.async_remove(entity_entry.entity_id)

    device_registry = dr.async_get(hass)
    for device_entry in dr.async_entries_for_config_entry(
        device_registry, entry.entry_id
    ):
        deepal_ids = {
            identifier[1]
            for identifier in device_entry.identifiers
            if identifier[0] == DOMAIN
        }
        if deepal_ids and deepal_ids.isdisjoint(current):
            device_registry.async_remove_device(device_entry.id)


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

    client = _build_client(hass, entry)
    coordinator = DeepalDataUpdateCoordinator(
        hass,
        entry,
        client,
        update_interval=timedelta(
            seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        ),
        wake_enabled=bool(entry.options.get(CONF_WAKE, DEFAULT_WAKE)),
    )

    charging = ChargingSessionManager(_charging_store(hass, entry))
    await charging.async_load()
    coordinator.charging = charging

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = DeepalRuntimeData(
        client=client, coordinator=coordinator, charging=charging
    )
    _remove_stale_vehicle_registry(hass, entry, coordinator)
    _sync_mqtt_reauth_issue(hass, entry, coordinator)

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
    """Clean up the entry's stored data and log out the international session.

    The charging sessions are always removed; the logout is best-effort: the
    logout and the client teardown are wrapped so a network or configuration
    failure is only logged and never blocks the removal.
    """
    await _charging_store(hass, entry).async_remove()
    ir.async_delete_issue(hass, DOMAIN, _mqtt_reauth_issue_id(entry))
    if entry.data.get(CONF_PLATFORM, PLATFORM_SDA) != PLATFORM_INTL:
        return
    if not entry.data.get(CONF_ACCESS_TOKEN):
        return

    client = None
    try:
        client = _build_client(hass, entry)
        await client.logout()
    except Exception as err:
        _LOGGER.warning("Deepal logout on entry removal failed: %s", err)
    finally:
        if client is not None:
            try:
                await client.close()
            except Exception as err:
                _LOGGER.warning("Deepal client close on entry removal failed: %s", err)


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    entry: DeepalConfigEntry,
    device_entry: dr.DeviceEntry,
) -> bool:
    """Allow removing a vehicle device the account no longer reports.

    Devices for vehicles still present in the account are kept: the platforms
    recreate them on every setup, so removing them would fight the reload.
    """
    runtime_data = getattr(entry, "runtime_data", None)
    if runtime_data is None:
        return True
    reported = {vehicle.car_id for vehicle in runtime_data.coordinator.vehicles}
    for identifier in device_entry.identifiers:
        if identifier[0] != DOMAIN:
            continue
        if identifier[1] in reported:
            return False
    return True
