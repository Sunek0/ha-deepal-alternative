"""Platform predicates for the Changan Deepal config entry.

The selected platform is stored in the entry data, not in the options, and an
entry written before the platform gate existed carries no value. Keeping the
default and the comparison in one place stops the call sites from drifting.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry

from .const import CONF_PLATFORM, PLATFORM_INTL, PLATFORM_SDA


def is_international(entry: ConfigEntry) -> bool:
    """Return True when the entry uses the international platform.

    Entries without a stored platform belong to the SDA platform, which is the
    historical default and the same fallback the setup and unload paths use.
    """
    return entry.data.get(CONF_PLATFORM, PLATFORM_SDA) == PLATFORM_INTL
