"""Example: SMS verification code login against the international Deepal API."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deepal import DeepalIntlClient

DIAL_CODES = {
    "ES": "34",
    "PT": "351",
    "GB": "44",
    "IE": "353",
    "FR": "33",
    "DE": "49",
    "IT": "39",
    "NL": "31",
    "BE": "32",
    "IL": "972",
}


async def main():
    country = input("Enter your sales country code (e.g. ES) [ES]: ").strip().upper() or "ES"
    default_dial = DIAL_CODES.get(country, "")
    dial_prompt = "Enter your country dial code (e.g. 34)"
    if default_dial:
        dial_prompt += f" [{default_dial}]"
    dial_code = input(f"{dial_prompt}: ").strip().lstrip("+") or default_dial
    while not dial_code.isdigit():
        dial_code = input("Dial code must be digits only (e.g. 34): ").strip().lstrip("+")

    phone = input("Enter your phone number without the country code: ").strip()
    while not phone or phone.startswith("+"):
        phone = input("Enter your national phone number (without +country code): ").strip()

    async with DeepalIntlClient(country=country) as client:
        print("Requesting SMS verification code...")
        await client.request_sms_code(phone, dial_code)

        code = input("Enter the SMS verification code received: ").strip()
        print("Logging in...")
        token = await client.login_with_sms_code(phone, code, dial_code)

        print("\nLogin successful!")
        print(f"Access Token: {token.access_token}")
        if token.refresh_token:
            print(f"Refresh Token: {token.refresh_token}")
        if token.cac_token:
            print(f"CAC Token: {token.cac_token}")
        if client.private_key_pem:
            print("\nLogin Private Key (needed for remote commands):")
            print(client.private_key_pem)


if __name__ == "__main__":
    asyncio.run(main())
