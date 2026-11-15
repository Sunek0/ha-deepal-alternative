#!/usr/bin/env python3
"""Probe the VOT charge-plan endpoints used by the My Changan app.

The script is read-only unless ``--apply`` is passed. It builds the same signed
request the Android app uses for the MQTT/VOT battery screen and can print the
current strategy list before creating a plan.

See README.md in this folder for the full test matrix and the meaning of every
option.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for candidate in (ROOT / "deepal_sdk", Path.cwd() / "deepal_sdk"):
    if candidate.is_dir() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from deepal import DeepalAPIError, DeepalAuthError, DeepalIntlClient  # noqa: E402


VOT_ADD_PLAN = "/intl-app-gw/intl-car-control/api/charge/add-plan"
VOT_CREATE_SERIAL = "/intl-app-gw/intl-car-control/api/control/create-serial-no"
VOT_STRATEGY_URLS = (
    "/intl-app-gw/vot-api-server/api/strategy/getStrategy",
    "/intl-app-gw/vot-vrtm-car-condition-write/api/strategy/getStrategy",
)


def _load_token_file(path: Path) -> dict[str, object]:
    path = path.expanduser()
    if not path.is_file():
        alternate = Path(__file__).resolve().parent / path.name
        if alternate.is_file():
            path = alternate
        else:
            raise SystemExit(
                f"Token file not found: {path}. Run login_email.py first or pass --token-file."
            )
    return json.loads(path.read_text(encoding="utf-8"))


def _client_from_args(args: argparse.Namespace) -> DeepalIntlClient:
    data: dict[str, object] = {}
    if args.token_file:
        data = _load_token_file(Path(args.token_file))
    client = DeepalIntlClient(
        country=args.country.upper(),
        environment=args.environment,
        signing_policy=args.signing_policy,
        private_key_pem=data.get("private_key_pem"),  # type: ignore[arg-type]
        public_key=data.get("public_key"),  # type: ignore[arg-type]
        device_id=data.get("device_id"),  # type: ignore[arg-type]
        enable_api_logging=args.debug,
    )
    token = args.token or data.get("access_token")
    if token:
        client.access_token = str(token)
    for field in ("refresh_token", "cac_token", "user_id", "ca_user_id", "cac_user_id"):
        value = data.get(field)
        if value:
            setattr(client, field, value)
    expires_at = data.get("expires_at")
    if isinstance(expires_at, (int, float)):
        client.access_token_expires_at = int(expires_at)
    return client


def _serial_payload(kind: str, car_id: str) -> dict[str, str]:
    if kind == "carId":
        return {"type": "2", "carId": car_id}
    if kind == "vehicleId":
        return {"type": "2", "vehicleId": car_id}
    if kind == "type-only":
        return {"type": "2"}
    return {"type": "2", "carId": car_id, "vehicleId": car_id}


async def list_plans(client: DeepalIntlClient, car_id: str) -> None:
    """Read the current strategy list without changing anything."""
    bodies = (
        {"strategyCode": "ReserveCharge", "vehicleId": car_id},
        {"strategyCode": "ReserveCharge", "carId": car_id},
        {"strategyCode": "ReserveCharge"},
    )
    for url in VOT_STRATEGY_URLS:
        for body in bodies:
            print(f"\nPOST {url}")
            print(f"body: {json.dumps(body, ensure_ascii=False)}")
            try:
                data = await client._request(  # noqa: SLF001 - diagnostic probe
                    url, json_data=body, auth_required=True
                )
                print(json.dumps(data, ensure_ascii=False, indent=2)[:6000])
            except DeepalAuthError as exc:
                print("AUTH", exc)
            except DeepalAPIError as exc:
                print("API", getattr(exc, "code", None), exc)
            except Exception as exc:  # noqa: BLE001 - diagnostic probe
                print("ERR", type(exc).__name__, exc)


async def build_body(
    client: DeepalIntlClient, args: argparse.Namespace, car_id: str
) -> dict[str, object]:
    """Build and sign the add-plan body without sending it."""
    serial_response = await client._request(  # noqa: SLF001 - diagnostic probe
        VOT_CREATE_SERIAL,
        json_data=_serial_payload(args.serial_body, car_id),
        auth_required=True,
    )
    if not isinstance(serial_response, str):
        raise DeepalAPIError("Unexpected VOT serial-number response.")
    serial_no = client.decrypt_serial_no(serial_response)

    body: dict[str, object] = {
        "vehicleId": car_id,
        "planType": args.plan_type,
        "timeFormat": args.time_format,
        "startTime": args.start,
        "endTime": args.end,
        args.repetition_field: args.weeks,
        "endSwitch": args.end_switch,
        "timeZone": args.time_zone,
        "seriralNo": serial_no,
    }
    if args.strategy_id:
        body["strategyId"] = args.strategy_id
    if args.command:
        body["command"] = args.command
    body["sign"] = client.sign_payload(body, omit_keys={"command", "rcToken"})
    return body


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token-file", default=os.getenv("DEEPAL_TOKEN_FILE", ".token.json"))
    parser.add_argument("--token", default=os.getenv("DEEPAL_TOKEN"))
    parser.add_argument("--country", default=os.getenv("DEEPAL_COUNTRY", "ES"))
    parser.add_argument("--environment", default=os.getenv("DEEPAL_ENVIRONMENT", "release_eu"))
    parser.add_argument("--car-id", default=os.getenv("DEEPAL_CAR_ID"))
    parser.add_argument("--start", default="0100", help="HHMM local vehicle time (default 0100).")
    parser.add_argument("--end", default="0200", help="HHMM local vehicle time (default 0200).")
    parser.add_argument("--weeks", default="1111111", help="7-character day mask (default all days).")
    parser.add_argument(
        "--repetition-field",
        choices=("repetitionCycle", "weeks"),
        default="repetitionCycle",
        help="Payload field used for the weekly mask.",
    )
    parser.add_argument("--end-switch", type=int, choices=(0, 1), default=0)
    parser.add_argument("--time-zone", default="GMT+01:00", help="Vehicle timezone in GMT+HH:MM form.")
    parser.add_argument("--plan-type", type=int, default=1)
    parser.add_argument("--time-format", type=int, default=1)
    parser.add_argument(
        "--strategy-id",
        default=None,
        help="Optional strategyId copied from --list; the VOT model accepts it.",
    )
    parser.add_argument(
        "--command",
        choices=("add_charge_plan",),
        default=None,
        help="Include the optional command field in the body.",
    )
    parser.add_argument("--signing-policy", choices=("app", "legacy"), default="app")
    parser.add_argument(
        "--serial-body",
        choices=("both", "carId", "vehicleId", "type-only"),
        default="both",
        help="Body variant for create-serial-no.",
    )
    parser.add_argument("--list", action="store_true", help="Read the current strategy list.")
    parser.add_argument("--apply", action="store_true", help="Actually POST the plan.")
    parser.add_argument("--debug", action="store_true", help="Enable SDK redacted API logging.")
    args = parser.parse_args()

    client = _client_from_args(args)
    async with client:
        if not client.access_token:
            raise SystemExit("No access token. Run login_email.py first or pass --token.")
        if not client.private_key_pem:
            raise SystemExit(
                "No login private key in the token file. Re-run login_email.py; "
                "remote commands cannot be signed without it."
            )
        vehicles = await client.get_vehicles()
        if not vehicles:
            raise SystemExit("No vehicles on this account.")
        vehicle = next((v for v in vehicles if v.car_id == args.car_id), vehicles[0])
        print(f"vehicle={vehicle.series_name!r} car_id={vehicle.car_id!r} vin={vehicle.vin!r}")

        if args.list:
            await list_plans(client, vehicle.car_id)
            return 0

        body = await build_body(client, args, vehicle.car_id)
        print("\nSigned body:")
        print(json.dumps(body, ensure_ascii=False, indent=2))
        if not args.apply:
            print("\nDry run only. Re-run with --apply to POST the plan.")
            return 0

        print(f"\nPOST {VOT_ADD_PLAN}")
        try:
            data = await client._request(  # noqa: SLF001 - diagnostic probe
                VOT_ADD_PLAN, json_data=body, auth_required=True
            )
            print(json.dumps(data, ensure_ascii=False, indent=2))
        except DeepalAuthError as exc:
            print("AUTH", exc)
            return 2
        except DeepalAPIError as exc:
            print("API", getattr(exc, "code", None), exc)
            return 1
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
