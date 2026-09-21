"""Vehicle telematics data models."""

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field

S05_TRIM_MAX = "max"
S05_TRIM_PRO = "pro"
S05_TRIM_UNKNOWN = "unknown"

# Function codes used by the app for the seat comfort capabilities
# (FunctionConfigManager.SeatHeatType / SeatVentType in the 1.12.0 DEX).
SEAT_HEAT_FUNCTION_CODES = {
    "front_left": "#driverSeatHeat",
    "front_right": "#passengerSeatHeat",
    "rear_left": "#LeftRearSeatHeat",
    "rear_right": "#RightRearSeatHeat",
}
SEAT_VENT_FUNCTION_CODES = {
    "front_left": "#driverSeatVent",
    "front_right": "#passengerSeatVent",
    "rear_left": "#LeftRearSeatVent",
    "rear_right": "#RightRearSeatVent",
}


class Vehicle(BaseModel):
    """Deepal Vehicle Summary model."""
    car_id: str = Field(..., description="Unique vehicle ID")
    vin: str = Field(..., description="Vehicle Identification Number (VIN)")
    series_name: Optional[str] = Field(default="Deepal S05", description="Vehicle series/model name")
    series_code: Optional[str] = Field(default=None, description="Vehicle series code (for example CD701)")
    model_name: Optional[str] = Field(default=None, description="Vehicle model name reported by the API")
    model_code: Optional[str] = Field(default=None, description="Vehicle model code reported by the API")
    car_name: Optional[str] = Field(default=None, description="Custom vehicle nickname")
    license_plate: Optional[str] = Field(default=None, description="License plate number")
    thumbnail_url: Optional[str] = Field(default=None, description="Image URL of the vehicle model")
    protocol_type: Optional[str] = Field(
        default=None, description="Backend telemetry protocol, 'MQTT' for MQTT-backed vehicles"
    )


class SeatCapabilities(BaseModel):
    """Heating and ventilation availability of one seat position."""

    heating: bool = False
    ventilation: bool = False


class VehicleCapabilities(BaseModel):
    """Per-vehicle function configuration reported by the app backend."""

    raw_codes: list[str] = Field(default_factory=list, description="Raw function codes")
    seats: dict[str, SeatCapabilities] = Field(
        default_factory=dict, description="Seat capabilities by position"
    )
    trim_hint: Literal["max", "pro", "unknown"] = Field(
        default=S05_TRIM_UNKNOWN,
        description="S05 trim hint derived from the capabilities, never from telemetry",
    )

    @classmethod
    def from_codes(cls, codes: list[str]) -> "VehicleCapabilities":
        """Build the typed capabilities from the raw function code list."""
        known = {str(code) for code in codes}
        seats = {
            position: SeatCapabilities(
                heating=heat_code in known,
                ventilation=SEAT_VENT_FUNCTION_CODES[position] in known,
            )
            for position, heat_code in SEAT_HEAT_FUNCTION_CODES.items()
        }
        front_ventilation = (
            seats["front_left"].ventilation or seats["front_right"].ventilation
        )
        return cls(
            raw_codes=[str(code) for code in codes],
            seats=seats,
            trim_hint=S05_TRIM_MAX if front_ventilation else S05_TRIM_PRO,
        )


class TireStatus(BaseModel):
    """Tire Pressure & Temperature."""
    pressure_bar: Optional[float] = None
    temperature_c: Optional[float] = None
    alarm: bool = False


class TiresCondition(BaseModel):
    """Four tires condition."""
    front_left: Optional[TireStatus] = None
    front_right: Optional[TireStatus] = None
    rear_left: Optional[TireStatus] = None
    rear_right: Optional[TireStatus] = None


class BatteryCondition(BaseModel):
    """EV Battery telemetry."""
    soc_percentage: Optional[int] = Field(default=None, ge=0, le=100, description="Battery State of Charge (%)")
    remaining_range_km: Optional[int] = Field(default=None, description="Estimated remaining range in km")
    charging_status: Optional[str] = Field(default=None, description="Charging / Discharging / Idle")
    charger_connected: bool = Field(default=False, description="Is charging cable plugged in")
    dc_gun_connected: bool = Field(default=False, description="Is the DC charging gun connected")
    charge_current_a: Optional[float] = Field(default=None, description="Charging current in amperes")
    ac_charge_current_a: Optional[float] = Field(default=None, description="AC charging current in amperes")
    dc_charge_current_a: Optional[float] = Field(default=None, description="DC charging current in amperes")
    remaining_charge_time_min: Optional[int] = Field(default=None, description="Remaining charge time in minutes")
    charge_limit_percent: Optional[int] = Field(default=None, ge=0, le=100, description="Maximum charge percentage")
    charge_schedule_enabled: bool = Field(default=False, description="Is the charging schedule enabled")
    charge_schedule_start: Optional[str] = Field(default=None, description="Charging schedule start time")
    charge_schedule_end: Optional[str] = Field(default=None, description="Charging schedule end time")
    charge_plan_id: Optional[str] = Field(default=None, description="Charging plan identifier")
    charge_plan_type: Optional[int] = Field(default=None, description="Charging plan type")
    charge_plan_time_format: Optional[int] = Field(default=None, description="Charging plan time format")
    charge_plan_time_zone: Optional[str] = Field(default=None, description="Charging plan time zone")


class DoorsCondition(BaseModel):
    """Vehicle doors and trunk status."""
    locked: bool = Field(default=True, description="Are doors locked")
    driver_locked: Optional[bool] = Field(default=None, description="Is the driver door locked")
    passenger_locked: Optional[bool] = Field(default=None, description="Is the passenger door locked")
    driver_door_open: bool = False
    passenger_door_open: bool = False
    rear_left_door_open: bool = False
    rear_right_door_open: bool = False
    trunk_open: bool = False
    hood_open: bool = False


class WindowsCondition(BaseModel):
    """Vehicle window positions."""
    front_left_open: bool = False
    front_right_open: bool = False
    rear_left_open: bool = False
    rear_right_open: bool = False


class SeatStatus(BaseModel):
    """Heating and ventilation level of one seat."""
    heating_level: int = 0
    ventilation_level: int = 0


class SeatsCondition(BaseModel):
    """Per-position seat comfort status."""
    front_left: SeatStatus = Field(default_factory=SeatStatus)
    front_right: SeatStatus = Field(default_factory=SeatStatus)
    rear_left: SeatStatus = Field(default_factory=SeatStatus)
    rear_right: SeatStatus = Field(default_factory=SeatStatus)


class ClimateCondition(BaseModel):
    """AC and Climate status."""
    power_on: Optional[bool] = Field(
        default=None, description="AC power state; None when the vehicle did not report it"
    )
    target_temperature_c: Optional[float] = None
    inside_temperature_c: Optional[float] = None
    outside_temperature_c: Optional[float] = None
    humidity: Optional[float] = None
    inside_pm25: Optional[float] = None
    air_quality_level: Optional[int] = None
    defrost_on: bool = False
    fan_level: Optional[int] = None
    steering_wheel_heater_on: bool = False
    steering_wheel_heater_level: int = 0
    driver_seat_ventilation_level: int = 0
    driver_seat_heating_level: int = 0


class LampsCondition(BaseModel):
    """Exterior lamp status."""
    high_beam: bool = False
    low_beam: bool = False
    position_lamp: bool = False
    front_fog: bool = False
    rear_fog: bool = False
    left_turn: bool = False
    right_turn: bool = False


class VehicleCondition(BaseModel):
    """Full Vehicle Status / Telemetry snapshot."""
    car_id: str
    vin: str
    total_odometer_km: Optional[float] = Field(default=None, description="Total odometer in km")
    mileage_yesterday_km: Optional[float] = Field(
        default=None, description="Mileage driven yesterday in km (MQTT)"
    )
    trip_mileage_km: Optional[float] = Field(
        default=None, description="Mileage since the current ignition cycle in km (MQTT)"
    )
    speed_kmh: Optional[float] = Field(default=None, description="Vehicle speed in km/h")
    gear: Optional[str] = Field(default=None, description="Raw gear signal value")
    epb_status: Optional[int] = Field(default=None, description="Raw electronic parking brake status")
    power_status: Optional[int] = Field(default=None, description="Raw power status value")
    vehicle_status: Optional[int] = Field(default=None, description="Raw vehicle status value")
    engine_on: bool = Field(default=False, description="Is the engine/drivetrain running")
    connected: Optional[bool] = Field(default=None, description="Is the vehicle connected to the cloud")
    battery: BatteryCondition = Field(default_factory=BatteryCondition)
    doors: DoorsCondition = Field(default_factory=DoorsCondition)
    windows: WindowsCondition = Field(default_factory=WindowsCondition)
    seats: SeatsCondition = Field(default_factory=SeatsCondition)
    climate: ClimateCondition = Field(default_factory=ClimateCondition)
    tires: TiresCondition = Field(default_factory=TiresCondition)
    lamps: LampsCondition = Field(default_factory=LampsCondition)
    last_updated_timestamp: Optional[int] = Field(default=None, description="Unix timestamp of last report")
    raw_data: Optional[dict[str, Any]] = Field(default=None, description="Raw JSON telemetry response")
    mqtt_raw_data: Optional[dict[str, Any]] = Field(
        default=None,
        description="Original decrypted S05 MQTT parameters, kept for diagnostics",
    )
