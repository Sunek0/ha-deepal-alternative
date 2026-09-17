"""Example: Fetching vehicle status using Deepal SDK."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deepal import DeepalClient


async def main():
    # Provide access token via environment variable or string
    token = os.getenv("DEEPAL_TOKEN", "YOUR_ACCESS_TOKEN_HERE")

    async with DeepalClient(access_token=token) as client:
        try:
            print("Fetching user's vehicles...")
            vehicles = await client.get_vehicles()
            if not vehicles:
                print("No vehicles found for this account.")
                return

            for car in vehicles:
                print(f"\n--- Vehicle: {car.series_name} ({car.car_id}) ---")
                print(f"VIN: {car.vin}")
                if car.license_plate:
                    print(f"Plate: {car.license_plate}")

                print("\nFetching telematics condition...")
                cond = await client.get_vehicle_condition(car.car_id)
                print(f"Total Odometer: {cond.total_odometer_km} km")
                print(f"Battery SoC: {cond.battery.soc_percentage}%")
                print(f"Remaining Range: {cond.battery.remaining_range_km} km")
                print(f"Doors Locked: {cond.doors.locked}")
                print(f"AC Active: {cond.climate.power_on}")

        except Exception as err:
            print(f"Error fetching status: {err}")


if __name__ == "__main__":
    asyncio.run(main())
