"""Example: Requesting SMS code and logging in with Deepal SDK."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deepal import DeepalClient


async def main():
    async with DeepalClient() as client:
        phone = input("Enter your phone number (e.g. +34600000000): ").strip()

        print("Requesting SMS verification code...")
        success = await client.request_sms_code(phone)
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
