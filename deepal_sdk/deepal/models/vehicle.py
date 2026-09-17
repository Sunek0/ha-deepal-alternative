"""Vehicle telematics data models."""

from typing import Optional, Any
from pydantic import BaseModel, Field


class Vehicle(BaseModel):
    """Deepal Vehicle Summary model."""
    car_id: str = Field(..., description="Unique vehicle ID")
    vin: str = Field(..., description="Vehicle Identification Number (VIN)")
    series_name: Optional[str] = Field(default="Deepal S05", description="Vehicle series/model name")
    car_name: Optional[str] = Field(default=None, description="Custom vehicle nickname")
    license_plate: Optional[str] = Field(default=None, description="License plate number")
    thumbnail_url: Optional[str] = Field(default=None, description="Image URL of the vehicle model")


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


class DoorsCondition(BaseModel):
    """Vehicle doors and trunk status."""
    locked: bool = Field(default=True, description="Are doors locked")
    driver_door_open: bool = False
    passenger_door_open: bool = False
    rear_left_door_open: bool = False
    rear_right_door_open: bool = False
    trunk_open: bool = False
    hood_open: bool = False


class ClimateCondition(BaseModel):
    """AC and Climate status."""
    power_on: bool = False
    target_temperature_c: Optional[float] = None
    steering_wheel_heater_on: bool = False
    driver_seat_ventilation_level: int = 0
    driver_seat_heating_level: int = 0


class VehicleCondition(BaseModel):
    """Full Vehicle Status / Telemetry snapshot."""
    car_id: str
    vin: str
    total_odometer_km: Optional[float] = Field(default=None, description="Total mileage (CdcTotMilg)")
    battery: BatteryCondition = Field(default_factory=BatteryCondition)
    doors: DoorsCondition = Field(default_factory=DoorsCondition)
    climate: ClimateCondition = Field(default_factory=ClimateCondition)
    tires: TiresCondition = Field(default_factory=TiresCondition)
    last_updated_timestamp: Optional[int] = Field(default=None, description="Unix timestamp of last report")
    raw_data: Optional[dict[str, Any]] = Field(default=None, description="Raw JSON telemetry response")
