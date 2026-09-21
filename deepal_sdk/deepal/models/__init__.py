"""Deepal SDK Data Models."""

from deepal.models.auth import AuthToken, UserProfile
from deepal.models.command import CommandResult, CommandResultStatus
from deepal.models.vehicle import (
    S05_TRIM_MAX,
    S05_TRIM_PRO,
    S05_TRIM_UNKNOWN,
    SEAT_HEAT_FUNCTION_CODES,
    SEAT_VENT_FUNCTION_CODES,
    Vehicle,
    VehicleCapabilities,
    VehicleCondition,
    SeatCapabilities,
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
    "S05_TRIM_MAX",
    "S05_TRIM_PRO",
    "S05_TRIM_UNKNOWN",
    "SEAT_HEAT_FUNCTION_CODES",
    "SEAT_VENT_FUNCTION_CODES",
    "VehicleCapabilities",
    "SeatCapabilities",
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
