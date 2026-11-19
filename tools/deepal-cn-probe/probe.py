#!/usr/bin/env python3
"""Read-only probe for the Deepal app (China) car-data endpoint.

The Deepal app (深蓝汽车) does not use the SDA platform. Its telemetry call is:

    POST https://cy-m.shenlanche.com.cn/app2/api/car/data?carId=...&keys=*&token=...

This tool lets a tester validate that endpoint with their own token, on their
own machine, and report the field names without sharing the token. It only
reads; it never logs in, requests an SMS, or sends a control command.

The token travels as a query parameter because that is the app's contract, so
the tool never prints the request URL. Use ``--raw`` to print the redacted
payload for field mapping.

Usage:
    DEEPAL_CN_TOKEN=... DEEPAL_CN_CAR_ID=... \
        python tools/deepal-cn-probe/probe.py

    DEEPAL_CN_TOKEN=... DEEPAL_CN_CAR_ID=... \
        python tools/deepal-cn-probe/probe.py --raw
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "deepal_sdk"))

from deepal.redact import redact_for_log  # noqa: E402

DEFAULT_BASE_URL = "https://cy-m.shenlanche.com.cn"
CAR_DATA_PATH = "/app2/api/car/data"
DEFAULT_KEYS = "*"
DEFAULT_TIMEOUT = 30.0

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2

#: Extra identifiers the shared redaction model does not cover by name. Kept
#: local to the probe until the SDK model needs them.
_EXTRA_REDACTED_KEYS = {"tuid", "sidandmid", "tenantid"}

#: Curated, non-sensitive fields for the default summary.
CURATED_FIELDS: tuple[tuple[str, str], ...] = (
    ("SOC (%)", "soc"),
    ("Remaining range (remainedPowerMile)", "remainedPowerMile"),
    ("Remaining fuel range (remainedOilMile)", "remainedOilMile"),
    ("Total residual mileage", "totalResidualMileage"),
    ("Odometer (totalOdometer)", "totalOdometer"),
    ("Charge status", "chargeStatus"),
    ("Battery charge status", "batteryChargeStatus"),
    ("Charge SOC", "chargeSoc"),
    ("Doors open (door)", "door"),
    ("Driver door", "driverDoor"),
    ("Passenger door", "passengerDoor"),
    ("Left front door", "leftFrontDoor"),
    ("Left rear door", "leftRearDoor"),
    ("Right front door", "rightFrontDoor"),
    ("Right rear door", "rightRearDoor"),
    ("Trunk", "trunk"),
    ("Hood", "hood"),
    ("Windows", "window"),
    ("Driver door lock", "driverDoorLock"),
    ("Air status", "airStatus"),
    ("AC target temperature", "airConditioningSetTemperature"),
    ("Cabin humidity", "innerHumidity"),
    ("PM2.5", "pm25"),
    ("Speed", "speed"),
    ("Vehicle speed", "vehicleSpeed"),
    ("Shift position", "shiftPosition"),
)


def build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Read the Deepal app (China) car-data endpoint with your own token. "
            "The output is redacted; the request URL is never printed."
        )
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("DEEPAL_CN_TOKEN"),
        help="access token (default: DEEPAL_CN_TOKEN)",
    )
    parser.add_argument(
        "--car-id",
        default=os.environ.get("DEEPAL_CN_CAR_ID"),
        help="vehicle id (default: DEEPAL_CN_CAR_ID)",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"gateway host (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--keys",
        default=DEFAULT_KEYS,
        help=f"value of the keys query parameter (default: {DEFAULT_KEYS})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"request timeout in seconds (default: {DEFAULT_TIMEOUT:g})",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="print the full redacted payload after the summary",
    )
    return parser


async def fetch_car_data(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    token: str,
    car_id: str,
    keys: str = DEFAULT_KEYS,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Call the car-data endpoint and return the decoded JSON payload."""
    response = await client.post(
        f"{base_url.rstrip('/')}{CAR_DATA_PATH}",
        params={"carId": car_id, "keys": keys, "token": token},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("the gateway returned a non-object JSON payload")
    return payload


def redact_payload(payload: Any) -> Any:
    """Redact the payload with the SDK model plus the extra identifiers."""
    return _redact_extra_keys(redact_for_log(payload))


def _redact_extra_keys(value: Any) -> Any:
    """Apply the probe's extra key list recursively."""
    if isinstance(value, dict):
        return {
            key: (
                "[redacted]"
                if str(key).lower() in _EXTRA_REDACTED_KEYS
                else _redact_extra_keys(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_extra_keys(item) for item in value]
    return value


def render_summary(data: dict[str, Any]) -> str:
    """Render the curated, non-sensitive telemetry summary."""
    lines = [f"Fields returned: {len(data)}"]
    missing: list[str] = []
    for label, key in CURATED_FIELDS:
        if key in data:
            lines.append(f"  {label:<38} {data[key]}")
        else:
            missing.append(key)
    if missing:
        lines.append(f"  (not present: {', '.join(missing)})")
    return "\n".join(lines)


def _error_text(payload: dict[str, Any]) -> str:
    code = payload.get("code")
    message = payload.get("msg") or payload.get("message") or "unknown error"
    return f"gateway error {code}: {message}"


async def run(
    args: argparse.Namespace,
    *,
    client: Optional[httpx.AsyncClient] = None,
) -> int:
    """Execute the probe and return the process exit code."""
    token = (args.token or "").strip()
    car_id = (args.car_id or "").strip()
    if not token or not car_id:
        print(
            "Missing credentials: set DEEPAL_CN_TOKEN and DEEPAL_CN_CAR_ID "
            "(or pass --token and --car-id).",
            file=sys.stderr,
        )
        return EXIT_USAGE
    if not str(args.base_url).lower().startswith("https://"):
        print(
            "Refusing to send the token over a non-HTTPS base URL; use https://.",
            file=sys.stderr,
        )
        return EXIT_USAGE

    owns_client = client is None
    http_client = client or httpx.AsyncClient()
    try:
        payload = await fetch_car_data(
            http_client,
            base_url=args.base_url,
            token=token,
            car_id=car_id,
            keys=args.keys,
            timeout=args.timeout,
        )
    except httpx.HTTPStatusError as err:
        # Do not print the exception: it embeds the URL, and the token is a
        # query parameter.
        print(
            f"Request failed with HTTP {err.response.status_code}.",
            file=sys.stderr,
        )
        return EXIT_ERROR
    except httpx.RequestError as err:
        print(f"Request failed ({type(err).__name__}).", file=sys.stderr)
        return EXIT_ERROR
    except ValueError as err:
        print(f"Invalid response: {err}", file=sys.stderr)
        return EXIT_ERROR
    finally:
        if owns_client:
            await http_client.aclose()

    if str(payload.get("code")) != "0":
        print(_error_text(payload), file=sys.stderr)
        return EXIT_ERROR

    data = payload.get("data")
    if not isinstance(data, dict):
        print("The gateway returned no data object.", file=sys.stderr)
        return EXIT_ERROR

    print(render_summary(data))
    if args.raw:
        print(json.dumps(redact_payload(payload), ensure_ascii=False, indent=2))
    return EXIT_OK


def main(argv: Optional[list[str]] = None) -> int:
    """Parse the CLI and run the probe."""
    args = build_parser().parse_args(argv)
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
