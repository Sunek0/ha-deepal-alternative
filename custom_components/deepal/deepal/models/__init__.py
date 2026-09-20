"""Deepal SDK Data Models."""

from .auth import AuthToken, UserProfile
from .command import CommandResult, CommandResultStatus
from .vehicle import (
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
