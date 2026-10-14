"""Register the bundled vehicle panel in the Home Assistant sidebar.

The panel is available to every Home Assistant user and is also opened by the
integration's "Configure" action. Registration happens once per Home Assistant
run, on the first entry setup, and is removed when the last entry goes away.
Failures only log: the panel is an addition, never a setup requirement.
"""

from __future__ import annotations

import logging

from homeassistant.components import frontend, panel_custom
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import (
    CONF_SHOW_PANEL,
    DOMAIN,
    FRONTEND_JS_URL,
    PANEL_ELEMENT,
    PANEL_SIDEBAR_ICON,
    PANEL_SIDEBAR_TITLE,
    PANEL_URL_PATH,
    VERSION,
)

_LOGGER = logging.getLogger(__name__)

DATA_PANEL_REGISTERED = "panel_registered"


async def async_register_panel(hass: HomeAssistant) -> None:
    """Add the vehicle panel to the sidebar once per Home Assistant run."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(DATA_PANEL_REGISTERED):
        return

    try:
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=PANEL_URL_PATH,
            webcomponent_name=PANEL_ELEMENT,
            sidebar_title=PANEL_SIDEBAR_TITLE,
            sidebar_icon=PANEL_SIDEBAR_ICON,
            # The version query keeps browsers from reusing a stale bundle
            # after an integration update.
            module_url=f"{FRONTEND_JS_URL}?v={VERSION}",
            require_admin=False,
            config={},
        )
    except Exception as err:  # noqa: BLE001 - contained on purpose
        _LOGGER.warning("Deepal panel registration failed: %s", err)
        return

    domain_data[DATA_PANEL_REGISTERED] = True


@callback
def async_unregister_panel(hass: HomeAssistant) -> None:
    """Remove the vehicle panel from the sidebar."""
    domain_data = hass.data.get(DOMAIN, {})
    if not domain_data.pop(DATA_PANEL_REGISTERED, None):
        return
    try:
        frontend.async_remove_panel(hass, PANEL_URL_PATH)
    except Exception as err:  # noqa: BLE001 - removal must never block
        _LOGGER.warning("Deepal panel removal failed: %s", err)


def _wants_panel(entry: ConfigEntry) -> bool:
    """True when the account wants the sidebar panel.

    A missing preference means the entry predates the option: keep the panel.
    """
    return bool(entry.options.get(CONF_SHOW_PANEL, True))


def panel_wanted(hass: HomeAssistant, exclude: ConfigEntry | None = None) -> bool:
    """True when any configured account wants the sidebar panel."""
    return any(
        _wants_panel(entry)
        for entry in hass.config_entries.async_entries(DOMAIN)
        if exclude is None or entry.entry_id != exclude.entry_id
    )


async def async_sync_panel(hass: HomeAssistant) -> None:
    """Register or remove the panel following the accounts' preference."""
    if panel_wanted(hass):
        await async_register_panel(hass)
    else:
        async_unregister_panel(hass)


@callback
def async_unregister_panel_if_unwanted(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Remove the panel when no remaining account wants it."""
    if panel_wanted(hass, exclude=entry):
        return
    async_unregister_panel(hass)
