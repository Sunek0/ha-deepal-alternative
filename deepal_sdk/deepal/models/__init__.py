"""Deepal SDK Data Models."""

from deepal.models.auth import AuthToken, UserProfile
from deepal.models.vehicle import (
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
