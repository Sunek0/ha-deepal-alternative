"""Example: Email verification code login against the international Deepal API."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deepal import DeepalIntlClient


async def main():
    email = input("Enter your account email: ").strip()
    country = input("Enter your sales country code (e.g. GB, ES, PT): ").strip().upper()

    async with DeepalIntlClient(country=country or "GB") as client:
        print("Requesting email verification code...")
        await client.request_email_code(email)

        code = input("Enter the verification code received by email: ").strip()
        print("Logging in...")
        token = await client.login_with_email_code(email, code)

        print("\nLogin successful!")
        print(f"Access Token: {token.access_token}")
        if token.refresh_token:
            print(f"Refresh Token: {token.refresh_token}")
        if token.cac_token:
            print(f"CAC Token: {token.cac_token}")
        if token.user_id:
            print(f"User ID: {token.user_id}")
        if client.private_key_pem:
            print("\nLogin Private Key (needed for remote commands):")
            print(client.private_key_pem)


if __name__ == "__main__":
    asyncio.run(main())
