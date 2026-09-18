"""Changan Deepal Vehicle Python SDK."""

from .client import DeepalClient
from .intl import DeepalIntlClient
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
    Vehicle,
    VehicleCondition,
    BatteryCondition,
    DoorsCondition,
    ClimateCondition,
    TiresCondition,
)

__version__ = "0.1.0"

__all__ = [
    "DeepalClient",
    "DeepalIntlClient",
    "DeepalError",
    "DeepalAuthError",
    "DeepalAPIError",
    "DeepalConnectionError",
    "DeepalRateLimitError",
    "DeepalCommandAuthError",
    "DeepalCommandNotReady",
    "AuthToken",
    "Vehicle",
    "VehicleCondition",
    "BatteryCondition",
    "DoorsCondition",
    "ClimateCondition",
    "TiresCondition",
]
