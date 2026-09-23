"""Example: read-only digital key authorization check.

Logs in with the email and password from the environment and reports, for every
vehicle of the account, whether the phone is supported for the digital key and
which functions the account is authorized to use. It never registers, downloads
or shares keys and never prints tokens, user ids or key material.

Usage:
    DEEPAL_EMAIL=you@example.com DEEPAL_PASSWORD=secret DEEPAL_COUNTRY=ES \
        python deepal_sdk/examples/digital_key_status.py
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deepal import DeepalIntlClient


async def main():
    email = os.getenv("DEEPAL_EMAIL", "").strip()
    password = os.getenv("DEEPAL_PASSWORD", "")
    country = os.getenv("DEEPAL_COUNTRY", "ES").strip().upper()

    if not email or not password:
        print("Set DEEPAL_EMAIL and DEEPAL_PASSWORD to run this example.")
        return

    async with DeepalIntlClient(country=country) as client:
        print("Logging in...")
        await client.login_with_email_password(email, password, sales_country=country)

        support = await client.get_digital_key_support()
        if support is None:
            print("Phone digital key scheme: unknown (query failed or unavailable)")
        else:
            print(
                f"Phone digital key scheme: {support.key_type} (flag={support.flag})"
            )

        vehicles = await client.get_vehicles()
        if not vehicles:
            print("No vehicles in this account.")
            return

        for vehicle in vehicles:
            print(f"\n--- {vehicle.series_name} ---")
            authorizations = await client.get_vehicle_authorizations(vehicle.car_id)
            if authorizations is None:
                print("Authorizations: unavailable (service not deployed in this region)")
                continue
            print(f"Digital key authorized: {'yes' if authorizations.digital_key else 'no'}")
            print("Authorized function codes:")
            for code in authorizations.raw_codes:
                print(f"  {code}")


if __name__ == "__main__":
    asyncio.run(main())
