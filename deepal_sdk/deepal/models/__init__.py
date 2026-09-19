"""Deepal SDK Data Models."""

from deepal.models.auth import AuthToken, UserProfile
from deepal.models.command import CommandResult, CommandResultStatus
from deepal.models.vehicle import (
    Vehicle,
    VehicleCondition,
    BatteryCondition,
    DoorsCondition,
    WindowsCondition,
    SeatsCondition,
    SeatStatus,
    ClimateCondition,
    TiresCondition,
    TireStatus,
    LampsCondition,
)

__all__ = [
    "AuthToken",
    "UserProfile",
    "CommandResult",
    "CommandResultStatus",
    "Vehicle",
    "VehicleCondition",
    "BatteryCondition",
    "DoorsCondition",
    "WindowsCondition",
    "SeatsCondition",
    "SeatStatus",
    "ClimateCondition",
    "TiresCondition",
    "TireStatus",
    "LampsCondition",
]
