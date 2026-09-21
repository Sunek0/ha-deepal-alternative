"""Changan Deepal Vehicle Python SDK."""

from deepal.client import DeepalClient
from deepal.intl import (
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
from deepal.exceptions import (
    DeepalError,
    DeepalAuthError,
    DeepalAPIError,
    DeepalConnectionError,
    DeepalRateLimitError,
    DeepalCommandAuthError,
    DeepalCommandNotReady,
)
from deepal.models import (
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
