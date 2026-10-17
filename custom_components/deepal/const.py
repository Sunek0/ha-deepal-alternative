"""Constants for the Deepal Alternative Home Assistant integration."""

import json
from pathlib import Path

try:  # Home Assistant 2026.4 and later expose the density unit enum.
    from homeassistant.const import UnitOfDensity

    DENSITY_MICROGRAMS_PER_CUBIC_METER = (
        UnitOfDensity.MICROGRAMS_PER_CUBIC_METER
    )
except ImportError:  # Home Assistant 2026.3 only ships the legacy constant.
    from homeassistant.const import CONCENTRATION_MICROGRAMS_PER_CUBIC_METER

    DENSITY_MICROGRAMS_PER_CUBIC_METER = CONCENTRATION_MICROGRAMS_PER_CUBIC_METER

try:  # Home Assistant 2026.7 and later expose the ratio unit enum.
    from homeassistant.const import UnitOfRatio

    PERCENTAGE_UNIT = UnitOfRatio.PERCENTAGE
except ImportError:  # Home Assistant 2026.3-2026.6 only ship the string.
    from homeassistant.const import PERCENTAGE

    PERCENTAGE_UNIT = PERCENTAGE

DOMAIN = "deepal"

PLATFORM_SDA = "sda"
PLATFORM_INTL = "intl"

CONF_PLATFORM = "platform"
CONF_PHONE = "phone"
CONF_EMAIL = "email"
CONF_LOGIN_METHOD = "login_method"
CONF_COUNTRY = "country"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_CAC_TOKEN = "cac_token"
CONF_USER_ID = "user_id"
CONF_VEHICLE_ID = "vehicle_id"
CONF_PRIVATE_KEY = "private_key"
CONF_PUBLIC_KEY = "public_key"
CONF_CONTROL_PIN = "control_pin"
CONF_DEVICE_ID = "device_id"
CONF_ENVIRONMENT = "environment"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_ENABLE_API_LOGGING = "enable_api_logging"
CONF_WAKE = "wake"
CONF_SHOW_PANEL = "show_panel"

DEFAULT_COUNTRY = "ES"
DEFAULT_NAME = "Deepal Alternative"
DEFAULT_SCAN_INTERVAL = 300  # seconds (5 minutes)
DEFAULT_ENVIRONMENT = "release_eu"
DEFAULT_WAKE = True
# New entries start without the sidebar panel (the setup flow asks for it).
# A missing preference means the entry predates the option, so the panel is
# kept for those entries.
DEFAULT_SHOW_PANEL = False

# Vehicle wake (MQTT): an explicit refresh wakes a stale car, throttled so
# repeated refreshes cannot drain the 12 V battery.
WAKE_STALE_AFTER = 120  # seconds since the last report before waking
WAKE_COOLDOWN = 300  # seconds between wakes per vehicle
WAKE_REPORT_TIMEOUT = 60  # seconds to wait for the fresh report after a wake

# Device Info
MANUFACTURER = "Changan Auto"
DEFAULT_MODEL = "Deepal S05 Max"

# Bundled frontend panel and dashboard card
PANEL_URL_PATH = "deepal-panel"
PANEL_ELEMENT = "deepal-panel"
FRONTEND_JS_FILE = "deepal-frontend.js"
PANEL_SIDEBAR_TITLE = "Deepal"
PANEL_SIDEBAR_ICON = "mdi:car-electric"
FRONTEND_URL_PATH = "/deepal/frontend"
FRONTEND_JS_URL = f"{FRONTEND_URL_PATH}/{FRONTEND_JS_FILE}"
FRONTEND_ASSETS_URL = f"{FRONTEND_URL_PATH}/assets"

INTEGRATION_DIR = Path(__file__).parent


def _read_manifest_version() -> str:
    """Return the integration version from the bundled manifest."""
    try:
        manifest = json.loads(
            (INTEGRATION_DIR / "manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return "0"
    version = manifest.get("version")
    return version if isinstance(version, str) else "0"


VERSION = _read_manifest_version()
