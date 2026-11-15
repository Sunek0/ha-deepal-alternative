#!/usr/bin/env python3
"""Obtain Deepal international tokens with an email login.

This helper is deliberately separate from the probe: it performs the email
verification-code flow (or the experimental email/password flow), then stores
the tokens *and the login private key* in a local JSON file. The private key is
required to sign remote commands; without it the probe cannot send a plan.

Examples:
    python login_email.py send-code --email you@example.com --country ES
    python login_email.py login --email you@example.com --code 123456 --country ES
    python login_email.py password --email you@example.com --password '...' --country ES
    python login_email.py show --token-file .token.json

The token file is written with mode 0600. Never commit or share it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for candidate in (ROOT / "deepal_sdk", Path.cwd() / "deepal_sdk"):
    if candidate.is_dir() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from deepal import DeepalIntlClient  # noqa: E402


def _device_id(path: Path) -> str:
    """Return a stable device id shared by send-code and login."""
    path = path.expanduser()
    if path.is_file():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = secrets.token_hex(16)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return value


def _mask(value: str | None) -> str:
    if not value or value == "None":
        return "<missing>"
    if len(value) <= 12:
        return value[:4] + "..."
    return value[:8] + "..." + value[-4:]


def _token_dict(client: DeepalIntlClient) -> dict[str, object]:
    return {
        "access_token": client.access_token,
        "refresh_token": client.refresh_token,
        "cac_token": client.cac_token,
        "user_id": client.user_id,
        "ca_user_id": client.ca_user_id,
        "cac_user_id": client.cac_user_id,
        "expires_at": client.access_token_expires_at,
        "private_key_pem": client.private_key_pem,
        "public_key": client.public_key,
        "device_id": client.device_id,
    }


def _save_tokens(client: DeepalIntlClient, path: Path) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_token_dict(client), indent=2), encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    print(f"\nSaved tokens and login key to {path} (mode 0600).")
    print("Keep this file private; it can sign commands for your account.")


def _show_token_file(path: Path) -> int:
    path = path.expanduser()
    if not path.is_file():
        print(f"Token file not found: {path}", file=sys.stderr)
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))
    print(f"Token file: {path}")
    for key in (
        "access_token",
        "refresh_token",
        "cac_token",
        "user_id",
        "ca_user_id",
        "cac_user_id",
        "expires_at",
        "device_id",
    ):
        print(f"  {key}: {_mask(str(data.get(key))) if key.endswith('token') else data.get(key)}")
    print(f"  private_key_pem: {'present' if data.get('private_key_pem') else '<missing>'}")
    print(f"  public_key: {'present' if data.get('public_key') else '<missing>'}")
    return 0


async def _send_code(args: argparse.Namespace) -> int:
    async with DeepalIntlClient(
        country=args.country.upper(),
        environment=args.environment,
        device_id=_device_id(Path(args.device_id_file)),
    ) as client:
        await client.request_email_code(args.email)
    print("Verification code requested. Check the mailbox for the email code.")
    return 0


async def _login_code(args: argparse.Namespace) -> int:
    async with DeepalIntlClient(
        country=args.country.upper(),
        environment=args.environment,
        device_id=_device_id(Path(args.device_id_file)),
    ) as client:
        token = await client.login_with_email_code(
            args.email, args.code, sales_country=args.country.upper()
        )
        print(f"Login OK: access_token={_mask(token.access_token)} user_id={token.user_id}")
        _save_tokens(client, Path(args.token_file))
    return 0


async def _login_password(args: argparse.Namespace) -> int:
    async with DeepalIntlClient(
        country=args.country.upper(),
        environment=args.environment,
        device_id=_device_id(Path(args.device_id_file)),
    ) as client:
        token = await client.login_with_email_password(
            args.email, args.password, sales_country=args.country.upper()
        )
        print(f"Login OK: access_token={_mask(token.access_token)} user_id={token.user_id}")
        _save_tokens(client, Path(args.token_file))
    return 0


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--email", required=True, help="Account email address.")
    common.add_argument("--country", default=os.getenv("DEEPAL_COUNTRY", "ES"), help="Sales country code, e.g. ES, GB, PT.")
    common.add_argument(
        "--environment",
        default=os.getenv("DEEPAL_ENVIRONMENT", "release_eu"),
        help="SDK environment: release_eu (production EU) or preprod_eu.",
    )
    common.add_argument(
        "--token-file",
        default=os.getenv("DEEPAL_TOKEN_FILE", ".token.json"),
        help="Where to store the tokens and login key (default: .token.json).",
    )
    common.add_argument(
        "--device-id-file",
        default=os.getenv("DEEPAL_DEVICE_ID_FILE", ".device_id"),
        help="Stable device id shared by send-code and login (default: .device_id).",
    )

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("send-code", parents=[common], help="Send the email verification code.")
    p.set_defaults(func=_send_code)

    p = sub.add_parser("login", parents=[common], help="Exchange an email code for tokens.")
    p.add_argument("--code", required=True, help="Verification code received by email.")
    p.set_defaults(func=_login_code)

    p = sub.add_parser("password", parents=[common], help="Experimental email/password login.")
    p.add_argument("--password", required=True, help="Account password.")
    p.set_defaults(func=_login_password)

    p = sub.add_parser("show", help="Show a masked summary of a token file.")
    p.add_argument("--token-file", default=os.getenv("DEEPAL_TOKEN_FILE", ".token.json"))
    p.set_defaults(func=None)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "show":
        return _show_token_file(Path(args.token_file))
    return asyncio.run(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
