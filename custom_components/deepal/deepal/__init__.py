"""Changan Deepal Vehicle Python SDK."""

from .client import DeepalClient
from .intl import (
    APP_SIGN_EXCLUDED_KEYS,
    FLASH_HONK_BEE,
    FLASH_HONK_FLASH,
    FLASH_HONK_FLASH_BEE,
    FLASH_HONK_OFF,
    SIGNING_POLICIES,
    SIGNING_POLICY_APP,
    SIGNING_POLICY_LEGACY,
    DeepalIntlClient,
)
from .exceptions import (
    DeepalError,
    DeepalAuthError,
    DeepalAPIError,
    DeepalConnectionError,
    DeepalRateLimitError,
    DeepalCommandAuthError,
    DeepalCommandNotReady,
)
from .models import (
    AuthToken,
    CommandResult,
    CommandResultStatus,
    Vehicle,
    VehicleCapabilities,
    VehicleCondition,
    SeatCapabilities,
    BatteryCondition,
    DoorsCondition,
    ClimateCondition,
    TiresCondition,
)

__version__ = "0.1.0"

__all__ = [
    "DeepalClient",
    "DeepalIntlClient",
    "APP_SIGN_EXCLUDED_KEYS",
    "FLASH_HONK_BEE",
    "FLASH_HONK_FLASH",
    "FLASH_HONK_FLASH_BEE",
    "FLASH_HONK_OFF",
    "SIGNING_POLICIES",
    "SIGNING_POLICY_APP",
    "SIGNING_POLICY_LEGACY",
    "DeepalError",
    "DeepalAuthError",
    "DeepalAPIError",
    "DeepalConnectionError",
    "DeepalRateLimitError",
    "DeepalCommandAuthError",
    "DeepalCommandNotReady",
    "AuthToken",
    "CommandResult",
    "CommandResultStatus",
    "Vehicle",
    "VehicleCapabilities",
    "VehicleCondition",
    "SeatCapabilities",
    "BatteryCondition",
    "DoorsCondition",
    "ClimateCondition",
    "TiresCondition",
]
