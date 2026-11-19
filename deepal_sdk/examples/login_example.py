"""Example: SDA SMS login transport (expected to fail at the captcha gate).

The SDA send-code endpoint requires a captcha authorization code produced by
the official app, which this SDK does not implement. The example is kept to
show the request shape and the error the gateway returns (business code 777).
Use a pasted access token for a working setup.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deepal import DeepalAPIError, DeepalClient


async def main():
    async with DeepalClient() as client:
        phone = input("Enter your phone number (e.g. 13800000000): ").strip()

        print("Requesting SMS verification code...")
        try:
            success = await client.request_sms_code(phone)
        except DeepalAPIError as err:
            print(f"SMS request rejected (code {err.code}): {err}")
            print("The SDA gateway requires a captcha authorization code; use an access token.")
            return
        if not success:
            print("Failed to request SMS code.")
            return

        code = input("Enter the SMS verification code received: ").strip()
        print("Logging in...")
        token_info = await client.login_with_code(phone, code)

        print("\nLogin successful!")
        print(f"Access Token: {token_info.access_token}")
        print(f"User ID: {token_info.user_id}")


if __name__ == "__main__":
    asyncio.run(main())
