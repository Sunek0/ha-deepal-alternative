"""Example: download the official layered vehicle-model assets.

The My Changan app keeps the extracted layers under
``Android/data/<package>/files/model/carmodel/unzip/<carId>/``. This example
shows the same descriptor and archive through the SDK and extracts the ZIP to a
directory you choose, rejecting entries that would escape it.
"""

import asyncio
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deepal import DeepalIntlClient


def _safe_extract(archive: Path, destination: Path) -> None:
    """Extract a ZIP without allowing path traversal."""
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            target = (destination / member.filename).resolve()
            if target != destination and destination not in target.parents:
                raise ValueError(f"refusing to extract outside {destination}: {member.filename}")
        bundle.extractall(destination)


async def main() -> None:
    email = input("Enter your account email: ").strip()
    country = input("Enter your sales country code (e.g. GB, ES, PT): ").strip().upper()

    async with DeepalIntlClient(country=country or "GB") as client:
        print("Requesting email verification code...")
        await client.request_email_code(email)
        code = input("Enter the verification code received by email: ").strip()
        await client.login_with_email_code(email, code)

        vehicles = await client.get_vehicles()
        if not vehicles:
            print("No vehicles found for this account.")
            return

        for index, vehicle in enumerate(vehicles, start=1):
            print(
                f"{index}. {vehicle.series_name} ({vehicle.car_id}) "
                f"platform={vehicle.car_platform}"
            )
        selected = int(input("Select a vehicle number: ").strip()) - 1
        vehicle = vehicles[selected]

        asset = await client.get_vehicle_model(vehicle.car_id, vehicle.car_platform)
        print(f"\nModel URL: {asset.model_url}")
        print(f"MD5: {asset.md5}")

        content = await client.download_vehicle_model_archive(
            vehicle.car_id, vehicle.car_platform
        )
        archive = Path(f"vehicle_model_{vehicle.car_id}.zip").resolve()
        archive.write_bytes(content)
        print(f"Saved {len(content)} bytes to {archive}")

        if input("Extract the archive now? [y/N] ").strip().lower() == "y":
            destination = Path(
                input("Destination directory: ").strip() or f"vehicle_model_{vehicle.car_id}"
            ).expanduser()
            _safe_extract(archive, destination)
            print(f"Extracted to {destination.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
