"""Component for Changan Deepal integration."""

import asyncio
import logging
import secrets
import time as _time
from datetime import timedelta
from typing import Any

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.storage import Store

from .charging import ChargingSessionManager
from .deepal import DeepalClient, DeepalIntlClient
from .diagnostics_capture import (
    async_get_capture_manager,
    async_register_diagnostics_view,
    async_remove_capture,
    async_shutdown_capture,
)
from .frontend import async_register_frontend, async_unregister_frontend
from .panel import async_sync_panel, async_unregister_panel_if_unwanted
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
    CONF_ENABLE_LOCATION,
    CONF_WAKE,
    DEFAULT_COUNTRY,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_ENVIRONMENT,
    DEFAULT_WAKE,
    DEFAULT_ENABLE_LOCATION,
)
from .coordinator import DeepalDataUpdateCoordinator
from .runtime_data import DeepalConfigEntry, DeepalRuntimeData
from .model_assets import (
    DATA_MODEL_ENTRIES,
    VehicleModelAssetManager,
    async_register_vehicle_model_view,
)

_LOGGER = logging.getLogger(__name__)


def _charging_store(hass: HomeAssistant, entry: DeepalConfigEntry) -> Store:
    """Return the per-entry store of the charging-session tracker."""
    return Store(hass, 1, f"{DOMAIN}.charging.{entry.entry_id}")


def _build_client(
    hass: HomeAssistant,
    entry: DeepalConfigEntry,
    *,
    on_exchange: Any = None,
) -> DeepalClient | DeepalIntlClient:
    """Build the API client for the entry's platform.

    Both clients share Home Assistant's httpx session; the SDK keeps an
    injected client open and leaves closing it to Home Assistant. An entry
    whose stored data carries no access token fails with
    ``ConfigEntryAuthFailed`` so the reauthentication flow can recover it.
    """
    access_token = entry.data.get(CONF_ACCESS_TOKEN)
    if not access_token:
        raise ConfigEntryAuthFailed(
            "The Deepal entry stores no access token; reauthenticate the entry."
        )
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
            on_exchange=on_exchange,
        )
        client.access_token = access_token
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
                client.private_key_pem = None
                client.public_key = None
        client.control_pin = (
            entry.options.get(CONF_CONTROL_PIN)
            or entry.data.get(CONF_CONTROL_PIN)
            or None
        )
        client.device_id = entry.data.get(CONF_DEVICE_ID) or client.device_id
        client.location_enabled = bool(
            entry.options.get(CONF_ENABLE_LOCATION, DEFAULT_ENABLE_LOCATION)
        )
        return client

    return DeepalClient(
        access_token=access_token,
        httpx_client=get_async_client(hass),
        on_exchange=on_exchange,
    )


def _platforms(entry: DeepalConfigEntry) -> list[Platform]:
    """Return the entity platforms for an entry."""
    platforms = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.IMAGE]
    if getattr(entry, "options", {}).get(
        CONF_ENABLE_LOCATION, DEFAULT_ENABLE_LOCATION
    ):
        platforms.append(Platform.DEVICE_TRACKER)
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
DATA_PENDING_VEHICLE_REMOVALS = "pending_vehicle_removals"

#: A vehicle must be missing from consecutive account reports for this long
#: before its registry entries and device are removed. A single partial list is
#: an anomaly, not a removal event, and deleting the entities would lose their
#: history irreversibly.
VEHICLE_REMOVAL_GRACE = 1800.0


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


def _pending_vehicle_removals(hass: HomeAssistant) -> dict[str, dict[str, float]]:
    """Return the per-entry first-missing timestamps."""
    return hass.data.setdefault(DOMAIN, {}).setdefault(
        DATA_PENDING_VEHICLE_REMOVALS, {}
    )


def _has_pending_vehicle_removals(
    hass: HomeAssistant, entry: DeepalConfigEntry
) -> bool:
    """Return whether an entry has a vehicle waiting for the grace window."""
    return bool(
        hass.data.get(DOMAIN, {})
        .get(DATA_PENDING_VEHICLE_REMOVALS, {})
        .get(entry.entry_id)
    )


def _remove_stale_vehicle_registry(
    hass: HomeAssistant,
    entry: DeepalConfigEntry,
    coordinator: DeepalDataUpdateCoordinator,
    *,
    now: float | None = None,
) -> bool:
    """Drop registry entries of vehicles the account no longer reports.

    A vehicle must be missing for ``VEHICLE_REMOVAL_GRACE`` seconds before its
    entities and device are removed: a single partial account response is an
    anomaly, not a removal event, and deleting the registry would lose the
    entity history irreversibly. The first-missing timestamp is kept per entry
    and vehicle in ``hass.data`` so reloads do not restart the window. An empty
    freshly fetched list removes nothing at all. Returns whether anything was
    removed.
    """
    current = {vehicle.car_id for vehicle in coordinator.vehicles}
    if not current:
        # The config flow rejects accounts without vehicles, and a running
        # coordinator keeps the current list when the account reports none, so
        # an empty first list is an anomaly (for example a transient gateway
        # response). Removing the registry here would wipe every entity and
        # device of the entry.
        return False

    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    entity_entries = list(
        er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    )
    device_entries = list(
        dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    )

    # Devices are the authoritative source of a vehicle identity; entities are
    # matched by their unique-id prefix because the test and legacy entries may
    # not carry a device id.
    stale_device_ids: dict[str, str] = {}
    for device_entry in device_entries:
        for domain, identifier in device_entry.identifiers:
            if domain == DOMAIN and identifier not in current:
                stale_device_ids[identifier] = device_entry.id
    stale_car_ids = set(stale_device_ids)
    known_car_ids = current | stale_car_ids
    entity_car_ids: dict[str, str | None] = {}
    for entity_entry in entity_entries:
        unique_id = entity_entry.unique_id or ""
        if not unique_id.startswith("deepal_"):
            continue
        car_id = next(
            (
                candidate
                for candidate in known_car_ids
                if unique_id.startswith(f"deepal_{candidate}_")
            ),
            None,
        )
        entity_car_ids[entity_entry.entity_id] = car_id
        if car_id is not None and car_id not in current:
            stale_car_ids.add(car_id)

    pending_by_entry = _pending_vehicle_removals(hass)
    if not stale_car_ids:
        pending_by_entry.pop(entry.entry_id, None)
        return False
    now = _time.monotonic() if now is None else now
    pending = pending_by_entry.setdefault(entry.entry_id, {})
    for car_id in current:
        pending.pop(car_id, None)
    for car_id in stale_car_ids:
        pending.setdefault(car_id, now)
    removable = {
        car_id
        for car_id in stale_car_ids
        if now - pending[car_id] >= VEHICLE_REMOVAL_GRACE
    }
    for car_id in list(pending):
        if car_id not in stale_car_ids:
            pending.pop(car_id, None)

    removed = False
    for entity_entry in entity_entries:
        unique_id = entity_entry.unique_id or ""
        if not unique_id.startswith("deepal_"):
            continue
        car_id = entity_car_ids.get(entity_entry.entity_id)
        if car_id is None or car_id in removable:
            entity_registry.async_remove(entity_entry.entity_id)
            removed = True
    for car_id in removable:
        device_id = stale_device_ids.get(car_id)
        if device_id is not None:
            device_registry.async_remove_device(device_id)
            removed = True
        pending.pop(car_id, None)
    if not pending:
        pending_by_entry.pop(entry.entry_id, None)
    return removed


async def _async_remove_stale_after_grace(
    hass: HomeAssistant, entry: DeepalConfigEntry
) -> None:
    """Remove a missing vehicle after the grace window and reload the entry."""
    while True:
        runtime_data = getattr(entry, "runtime_data", None)
        if runtime_data is None:
            return
        coordinator = runtime_data.coordinator
        if not coordinator.vehicles:
            return
        pending = (
            hass.data.get(DOMAIN, {})
            .get(DATA_PENDING_VEHICLE_REMOVALS, {})
            .get(entry.entry_id, {})
        )
        if not pending:
            return
        wait = (
            min(timestamp + VEHICLE_REMOVAL_GRACE for timestamp in pending.values())
            - _time.monotonic()
        )
        if wait > 0:
            await asyncio.sleep(wait)
        if _remove_stale_vehicle_registry(hass, entry, coordinator):
            hass.config_entries.async_schedule_reload(entry.entry_id)
            return
        if not _has_pending_vehicle_removals(hass, entry):
            return


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

    capture = async_get_capture_manager(hass, entry, create=True)
    client = _build_client(hass, entry, on_exchange=capture.record)
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

    platforms = _platforms(entry)
    entry.runtime_data = DeepalRuntimeData(
        client=client,
        coordinator=coordinator,
        charging=charging,
        capture=capture,
        platforms=platforms,
    )
    async_register_diagnostics_view(hass)
    await capture.async_start()

    # Fetch initial data
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await async_shutdown_capture(hass, entry)
        raise
    capture.record(
        {
            "kind": "capture",
            "event": "vehicles",
            "vehicles": [
                {
                    "car_id": vehicle.car_id,
                    "vin": vehicle.vin,
                    "series_name": vehicle.series_name,
                    "model_name": vehicle.model_name,
                    "model_code": vehicle.model_code,
                    "series_code": vehicle.series_code,
                    "car_platform": vehicle.car_platform,
                    "protocol_type": vehicle.protocol_type,
                }
                for vehicle in coordinator.vehicles
            ],
        }
    )

    if isinstance(client, DeepalIntlClient) and async_register_vehicle_model_view(
        hass
    ):
        manager = VehicleModelAssetManager(hass, client)
        await manager.async_load(coordinator.vehicles)
        entry.runtime_data.model_assets = manager
        coordinator.model_assets = manager
        hass.data.setdefault(DOMAIN, {}).setdefault(DATA_MODEL_ENTRIES, {})[
            entry.entry_id
        ] = manager
        entry.async_create_background_task(
            hass,
            manager.async_prefetch_vehicles(coordinator.vehicles),
            f"{DOMAIN}_model_assets_{entry.entry_id}",
        )

    _remove_stale_vehicle_registry(hass, entry, coordinator)
    if _has_pending_vehicle_removals(hass, entry):
        entry.async_create_background_task(
            hass,
            _async_remove_stale_after_grace(hass, entry),
            f"{DOMAIN}_stale_registry_{entry.entry_id}",
        )
    _sync_mqtt_reauth_issue(hass, entry, coordinator)

    # The panel and its assets are an addition: registration is contained and
    # happens once per Home Assistant run, even with several entries. Whether
    # the panel shows depends on the accounts' stored preference.
    await async_register_frontend(hass)
    await async_sync_panel(hass)

    platforms = _platforms(entry)
    _LOGGER.debug(
        "Deepal setting up platforms: %s", [platform.value for platform in platforms]
    )
    await hass.config_entries.async_forward_entry_setups(entry, platforms)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DeepalConfigEntry) -> bool:
    """Unload a config entry."""
    runtime_data = getattr(entry, "runtime_data", None)
    platforms = getattr(runtime_data, "platforms", None)
    if platforms is None:
        platforms = _platforms(entry)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms)

    if unload_ok:
        await async_shutdown_capture(hass, entry)

    if unload_ok and runtime_data is not None:
        manager = getattr(runtime_data, "model_assets", None)
        if manager is not None:
            await manager.async_shutdown()
            runtime_data.coordinator.model_assets = None
        await runtime_data.client.close()

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: DeepalConfigEntry) -> None:
    """Clean up the entry's stored data and log out the international session.

    The charging sessions are always removed; the logout is best-effort: the
    logout and the client teardown are wrapped so a network or configuration
    failure is only logged and never blocks the removal.
    """
    await _charging_store(hass, entry).async_remove()
    await async_remove_capture(hass, entry)
    hass.data.get(DOMAIN, {}).get(DATA_PENDING_VEHICLE_REMOVALS, {}).pop(
        entry.entry_id, None
    )
    manager = getattr(getattr(entry, "runtime_data", None), "model_assets", None)
    if manager is None:
        manager = (
            hass.data.get(DOMAIN, {})
            .get(DATA_MODEL_ENTRIES, {})
            .pop(entry.entry_id, None)
        )
    else:
        hass.data.get(DOMAIN, {}).get(DATA_MODEL_ENTRIES, {}).pop(
            entry.entry_id, None
        )
    if manager is not None:
        await manager.async_remove_cache()
    ir.async_delete_issue(hass, DOMAIN, _mqtt_reauth_issue_id(entry))
    async_unregister_panel_if_unwanted(hass, entry)
    if not any(
        other.entry_id != entry.entry_id
        for other in hass.config_entries.async_entries(DOMAIN)
    ):
        await async_unregister_frontend(hass)
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
