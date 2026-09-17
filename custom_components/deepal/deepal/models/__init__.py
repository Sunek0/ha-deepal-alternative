"""Deepal SDK Data Models."""

from .auth import AuthToken, UserProfile
from .vehicle import (
    Vehicle,
    VehicleCondition,
    BatteryCondition,
    DoorsCondition,
    ClimateCondition,
    TiresCondition,
    TireStatus,
)

__all__ = [
    "AuthToken",
    "UserProfile",
    "Vehicle",
    "VehicleCondition",
    "BatteryCondition",
    "DoorsCondition",
    "ClimateCondition",
    "TiresCondition",
    "TireStatus",
]
