"""Constants for the Deepal Alternative Home Assistant integration."""

try:  # Home Assistant 2026.4 and later expose the density unit enum.
    from homeassistant.const import UnitOfDensity

    DENSITY_MICROGRAMS_PER_CUBIC_METER = (
        UnitOfDensity.MICROGRAMS_PER_CUBIC_METER
    )
except ImportError:  # Home Assistant 2026.3 only ships the legacy constant.
    from homeassistant.const import (
        CONCENTRATION_MICROGRAMS_PER_CUBIC_METER as DENSITY_MICROGRAMS_PER_CUBIC_METER,
    )

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
CONF_OS_VERSION = "os_version"
CONF_ENVIRONMENT = "environment"
CONF_SEND_TIMESTAMPS = "send_timestamps"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_ENABLE_API_LOGGING = "enable_api_logging"
CONF_ENABLE_MQTT_CONTROLS = "enable_mqtt_controls"

DEFAULT_COUNTRY = "ES"
DEFAULT_NAME = "Deepal Alternative"
DEFAULT_SCAN_INTERVAL = 120  # seconds (2 minutes)
DEFAULT_OS_VERSION = "9"
DEFAULT_ENVIRONMENT = "release_eu"
DEFAULT_SEND_TIMESTAMPS = False

# Device Info
MANUFACTURER = "Changan Auto"
DEFAULT_MODEL = "Deepal S05 Max"
