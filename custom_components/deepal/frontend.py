"""Serve the bundled vehicle panel bundle and its view assets.

The panel is a plain JavaScript custom element shipped with the integration.
Home Assistant can only load it from a URL, so the integration publishes one
static path for the built bundle and one for the view assets. Registration is
idempotent per Home Assistant run and contained: a failure only logs, so
integration setup and the entities keep working without the panel.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    FRONTEND_ASSETS_URL,
    FRONTEND_JS_FILE,
    FRONTEND_JS_URL,
    VERSION,
)

_LOGGER = logging.getLogger(__name__)

INTEGRATION_DIR = Path(__file__).parent
FRONTEND_JS_PATH = INTEGRATION_DIR / "frontend" / "panel" / FRONTEND_JS_FILE
PANEL_ASSETS_DIR = INTEGRATION_DIR / "frontend" / "assets"

DATA_FRONTEND_REGISTERED = "frontend_registered"


def _resource_collection(hass: HomeAssistant):
    """Return the Lovelace resource collection, or None when unavailable.

    The collection is missing (or has no ``async_create_item``) when the
    dashboard resources are managed in YAML mode.
    """
    try:
        from homeassistant.components.lovelace.const import (  # noqa: PLC0415
            LOVELACE_DATA,
        )
    except ImportError:
        return None
    data = hass.data.get(LOVELACE_DATA)
    resources = getattr(data, "resources", None)
    if resources is None or not hasattr(resources, "async_create_item"):
        return None
    return resources


async def _async_register_resource(hass: HomeAssistant) -> None:
    """Load the bundle as a dashboard resource so cards are defined early.

    Dashboards load their resources before rendering cards; registering the
    bundle here is what makes ``custom:deepal-card`` available from the card
    picker like any other custom card. Contained: a failure only logs.
    """
    try:
        resources = _resource_collection(hass)
        if resources is None:
            _LOGGER.debug(
                "Deepal: Lovelace resources are in YAML mode; the card relies "
                "on the auto-loaded bundle only"
            )
            return
        await resources.async_get_info()
        resource_url = f"{FRONTEND_JS_URL}?v={VERSION}"
        for item in resources.async_items():
            if str(item.get("url", "")).split("?")[0] != FRONTEND_JS_URL:
                continue
            if str(item.get("url", "")) == resource_url:
                return
            # The version query is the cache buster. Keep the resource entry
            # but move it to the current bundle URL after an update; otherwise
            # the browser can keep serving the previous module from cache.
            if hasattr(resources, "async_update_item"):
                await resources.async_update_item(item["id"], {"url": resource_url})
            else:
                await resources.async_delete_item(item["id"])
                await resources.async_create_item(
                    {"res_type": "module", "url": resource_url}
                )
            return
        await resources.async_create_item(
            {"res_type": "module", "url": resource_url}
        )
    except Exception as err:  # noqa: BLE001 - the card must never break setup
        _LOGGER.warning("Deepal frontend resource registration failed: %s", err)


async def async_unregister_frontend(hass: HomeAssistant) -> None:
    """Remove the dashboard resource registered for the card."""
    try:
        resources = _resource_collection(hass)
        if resources is None:
            return
        await resources.async_get_info()
        for item in resources.async_items():
            if str(item.get("url", "")).split("?")[0] == FRONTEND_JS_URL:
                await resources.async_delete_item(item["id"])
    except Exception as err:  # noqa: BLE001 - removal must never block
        _LOGGER.debug("Deepal frontend resource removal failed: %s", err)


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Publish the frontend bundle and its assets as static paths.

    The bundle carries the sidebar panel and the dashboard card; it is also
    auto-loaded through ``frontend.add_extra_js_url`` so dashboards can use
    the card without a Lovelace resource. Safe to call on every entry setup:
    the paths are registered once per Home Assistant run, and a failure is
    logged but never allowed to break the integration.
    """
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(DATA_FRONTEND_REGISTERED):
        return

    try:
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(FRONTEND_JS_URL, str(FRONTEND_JS_PATH), False),
                StaticPathConfig(FRONTEND_ASSETS_URL, str(PANEL_ASSETS_DIR), False),
            ]
        )
    except RuntimeError as err:
        # A reload or a re-add can find the path already served.
        _LOGGER.debug("Deepal frontend path already registered: %s", err)
    except Exception as err:  # noqa: BLE001 - the frontend must never break setup
        _LOGGER.warning("Deepal frontend registration failed: %s", err)
        return

    try:
        add_extra_js_url(hass, f"{FRONTEND_JS_URL}?v={VERSION}")
    except Exception as err:  # noqa: BLE001 - contained on purpose
        _LOGGER.warning("Deepal frontend auto-load failed: %s", err)

    await _async_register_resource(hass)

    domain_data[DATA_FRONTEND_REGISTERED] = True
