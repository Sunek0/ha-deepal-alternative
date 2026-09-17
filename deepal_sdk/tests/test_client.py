"""Unit tests for Deepal Client and models."""

import pytest
from deepal import DeepalClient
from deepal.models import VehicleCondition, Vehicle


@pytest.mark.asyncio
async def test_client_initialization():
    client = DeepalClient(access_token="test_token_123")
    assert client.access_token == "test_token_123"
    assert "Authorization" in client._get_headers()
    assert client._get_headers()["Authorization"] == "Bearer test_token_123"
    await client.close()


def test_vehicle_model():
    v = Vehicle(car_id="12345", vin="LS5AXXXXX123456", series_name="Deepal S05 Max")
    assert v.car_id == "12345"
    assert v.vin == "LS5AXXXXX123456"
    assert v.series_name == "Deepal S05 Max"


def test_vehicle_condition_parsing():
    raw = {
        "vin": "LS5AXXXXX123456",
        "CdcTotMilg": 12450.5,
        "BatterySoc": 82,
        "RemainingRange": 410,
        "DoorsLocked": True,
        "AcPowerOn": False,
    }

    cond = VehicleCondition(
        car_id="12345",
        vin=raw["vin"],
        total_odometer_km=raw["CdcTotMilg"],
        battery={"soc_percentage": raw["BatterySoc"], "remaining_range_km": raw["RemainingRange"]},
        doors={"locked": raw["DoorsLocked"]},
        climate={"power_on": raw["AcPowerOn"]},
    )

    assert cond.car_id == "12345"
    assert cond.total_odometer_km == 12450.5
    assert cond.battery.soc_percentage == 82
    assert cond.battery.remaining_range_km == 410
    assert cond.doors.locked is True
    assert cond.climate.power_on is False
