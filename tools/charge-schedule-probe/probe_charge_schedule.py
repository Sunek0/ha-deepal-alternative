#!/usr/bin/env python3
"""Probe the Deepal international charge schedule from the HA config entry.

The script reads the Deepal config entry stored by Home Assistant, builds the
same signed ``/charge/modify-plan`` command the integration uses and, only
with ``--apply``, sends it to the car.

It is dry-run by default. The access token is NOT refreshed by default, so the
script cannot rotate the refresh token and log the Home Assistant integration
out; if the token is about to expire the script stops and asks you to wait for
the integration to refresh it.

See README.md in this folder for the safety notes and the full examples.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
for candidate in (ROOT / "deepal_sdk", Path.cwd() / "deepal_sdk"):
    if candidate.is_dir() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from deepal import DeepalError, DeepalIntlClient  # noqa: E402


DEFAULT_ENTRY = Path("/mnt/ha-config/.storage/core.config_entries")
HA_TIME_ZONE = "Europe/Madrid"


def _ha_gmt_offset(zone: str) -> str:
    """Return the current ``GMT+HH:MM`` offset of a zone."""
    offset = datetime.now(ZoneInfo(zone)).utcoffset()
    if offset is None:
        return "GMT+00:00"
    minutes = int(offset.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    hours, rest = divmod(abs(minutes), 60)
    return f"GMT{sign}{hours:02d}:{rest:02d}"


def _hhmm(value: str) -> str:
    """Normalize ``HHMM`` or ``HH:MM`` to the wire ``HHMM`` form."""
    text = value.strip().replace(":", "")
    if len(text) != 4 or not text.isdigit():
        raise argparse.ArgumentTypeError(
            f"expected HHMM or HH:MM between 0000 and 2359, got {value!r}"
        )
    hours, minutes = int(text[:2]), int(text[2:])
    if not 0 <= hours <= 23 or not 0 <= minutes <= 59:
        raise argparse.ArgumentTypeError(f"invalid clock time {value!r}")
    return text


def _load_entry(path: Path, entry_id: str | None) -> tuple[dict[str, Any], str]:
    """Load the Deepal entry from an HA storage file or a token file."""
    try:
        raw = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except PermissionError as exc:
        raise SystemExit(
            f"Cannot read {path}: {exc}. Run the script with sudo, or copy the "
            "entry to a private file and pass --entry-file."
        ) from exc
    except FileNotFoundError as exc:
        raise SystemExit(f"Entry file not found: {path}") from exc

    # Full HA .storage/core.config_entries
    entries = (
        raw.get("data", {}).get("entries")
        if isinstance(raw.get("data"), dict)
        else None
    )
    if isinstance(entries, list):
        candidates = [item for item in entries if item.get("domain") == "deepal"]
        if entry_id:
            candidates = [
                item for item in candidates if item.get("entry_id") == entry_id
            ]
        if not candidates:
            raise SystemExit("No Deepal config entry found in the storage file.")
        entry = candidates[0]
        return dict(entry.get("data") or {}), str(entry.get("title") or "Deepal")

    # A single HA entry dict or a token file.
    data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    if not isinstance(data, dict) or not data.get("access_token"):
        raise SystemExit(
            f"{path} does not look like an HA config entry or a token file."
        )
    if "private_key_pem" in data and "private_key" not in data:
        data = dict(data)
        data["private_key"] = data.get("private_key_pem")
    return dict(data), str(raw.get("title") or "Deepal")


def _build_client(data: dict[str, Any], *, debug: bool) -> DeepalIntlClient:
    client = DeepalIntlClient(
        country=str(data.get("country") or "ES").upper(),
        environment=str(data.get("environment") or "release_eu"),
        enable_api_logging=debug,
    )
    client.access_token = data.get("access_token")
    client.refresh_token = data.get("refresh_token")
    client.cac_token = data.get("cac_token")
    client.user_id = data.get("user_id")
    client.control_pin = data.get("control_pin")
    client.device_id = data.get("device_id") or client.device_id
    private_key = data.get("private_key")
    if private_key:
        client.set_login_keypair(private_key, data.get("public_key"))
    return client


def _plan_summary(condition: Any) -> dict[str, Any]:
    battery = condition.battery
    raw_plan = ((condition.raw_data or {}).get("charge") or {}).get("chargePlanList")
    first = raw_plan[0] if isinstance(raw_plan, list) and raw_plan else {}
    first = first if isinstance(first, dict) else {}
    return {
        "last_updated": condition.last_updated_timestamp,
        "soc": battery.soc_percentage,
        "charging_status": battery.charging_status,
        "charger_connected": battery.charger_connected,
        "plan_id": battery.charge_plan_id,
        "plan_type": battery.charge_plan_type,
        "start": battery.charge_schedule_start,
        "end": battery.charge_schedule_end,
        "switches_enabled": battery.charge_schedule_enabled,
        "plan_valid": first.get("isValid"),
        "start_switch": first.get("startSwitch"),
        "end_switch": first.get("endSwitch"),
        "time_format": battery.charge_plan_time_format,
        "time_zone": battery.charge_plan_time_zone,
    }


async def _poll(
    client: DeepalIntlClient,
    vehicle: Any,
    command_id: str,
    seconds: int,
) -> None:
    deadline = time.monotonic() + seconds
    last_status: str | None = None
    last_plan: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        await asyncio.sleep(5)
        try:
            result = await client.control_result_status(vehicle.car_id, command_id)
            status = f"{result.status.value} code={result.code}"
            if result.error_message:
                status += f" error={result.error_message!r}"
            if status != last_status:
                print(f"command: {status}")
                last_status = status
        except Exception as exc:  # noqa: BLE001 - diagnostic probe
            print(f"command poll failed: {type(exc).__name__}: {exc}")

        try:
            condition = await client.get_vehicle_condition(
                vehicle.car_id,
                vin=vehicle.vin,
                model_code=vehicle.model_code,
            )
            plan = _plan_summary(condition)
            if plan != last_plan:
                print(f"condition: {json.dumps(plan, ensure_ascii=False)}")
                last_plan = plan
        except Exception as exc:  # noqa: BLE001 - diagnostic probe
            print(f"condition poll failed: {type(exc).__name__}: {exc}")

        try:
            mqtt = await client.s05_mqtt_condition(vehicle.car_id, vin=vehicle.vin)
            battery = mqtt.battery
            print(
                "mqtt: "
                f"status={battery.charging_status!r} "
                f"current={battery.charge_current_a!r} "
                f"last={mqtt.last_updated_timestamp!r}"
            )
        except Exception as exc:  # noqa: BLE001 - diagnostic probe
            print(f"mqtt poll failed: {type(exc).__name__}: {exc}")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry-file", default=str(DEFAULT_ENTRY))
    parser.add_argument("--entry-id", default=None)
    parser.add_argument("--start", type=_hhmm, default="0000", help="Start HHMM (default 0000).")
    parser.add_argument("--end", type=_hhmm, default="0100", help="End HHMM (default 0100).")
    parser.add_argument(
        "--disabled",
        action="store_true",
        help="Disable the plan instead of enabling it (default: enabled).",
    )
    parser.add_argument("--plan-id", default=None, help="Plan id; defaults to the car's plan.")
    parser.add_argument("--plan-type", type=int, default=1)
    parser.add_argument("--time-format", type=int, default=1)
    parser.add_argument(
        "--time-zone",
        default=None,
        help=f"Vehicle timezone in GMT+HH:MM form (default: current {HA_TIME_ZONE} offset).",
    )
    parser.add_argument(
        "--wake",
        action="store_true",
        help="Wake the vehicle before sending the command (recommended when it is asleep).",
    )
    parser.add_argument(
        "--add-plan",
        action="store_true",
        help="Create a new plan with /charge/add-plan instead of modifying the existing one.",
    )
    parser.add_argument(
        "--delete-plan",
        action="store_true",
        help="Delete the plan selected by --plan-id (or the car's current plan).",
    )
    parser.add_argument(
        "--validity",
        action="store_true",
        help="Enable or disable the existing plan with /charge/validity instead of "
        "modifying its times with /charge/modify-plan.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Send the command. Without it the script only prints the plan and the payload.",
    )
    parser.add_argument(
        "--watch",
        type=int,
        default=30,
        help="Seconds to poll the command/condition after --apply (default 30).",
    )
    parser.add_argument(
        "--allow-refresh",
        action="store_true",
        help="Allow the script to refresh the token. This can rotate the refresh token and "
        "force the Home Assistant integration to reauthenticate; use only if you accept that.",
    )
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    data, title = _load_entry(Path(args.entry_file), args.entry_id)
    if not data.get("access_token"):
        raise SystemExit("The entry has no access token.")
    if not data.get("private_key"):
        raise SystemExit("The entry has no login private key; commands cannot be signed.")
    if not data.get("device_id"):
        raise SystemExit("The entry has no device id; commands cannot be signed.")

    client = _build_client(data, debug=args.debug)
    if client.access_token_expires_soon(margin_seconds=300):
        if not args.allow_refresh:
            raise SystemExit(
                "The access token expires within 5 minutes (or has expired). Wait for the "
                "Home Assistant integration to refresh it, or pass --allow-refresh if you "
                "accept that it may force the integration to reauthenticate."
            )
        await client.refresh_tokens(force=True)

    time_zone = args.time_zone or _ha_gmt_offset(HA_TIME_ZONE)
    enabled = not args.disabled

    async with client:
        vehicles = await client.get_vehicles()
        if not vehicles:
            raise SystemExit("No vehicles on this account.")
        preferred = data.get("vehicle_id")
        vehicle = next((item for item in vehicles if item.car_id == preferred), vehicles[0])
        print(
            f"entry={title!r} vehicle={vehicle.series_name!r} "
            f"car_id={vehicle.car_id!r} vin={vehicle.vin!r} "
            f"model={vehicle.model_code!r}"
        )

        condition = await client.get_vehicle_condition(
            vehicle.car_id,
            vin=vehicle.vin,
            model_code=vehicle.model_code,
        )
        print(f"current condition: {json.dumps(_plan_summary(condition), ensure_ascii=False)}")
        raw_plan = ((condition.raw_data or {}).get("charge") or {}).get("chargePlanList")
        print(f"current plan list: {json.dumps(raw_plan, ensure_ascii=False)}")

        try:
            mqtt = await client.s05_mqtt_condition(vehicle.car_id, vin=vehicle.vin)
            battery = mqtt.battery
            print(
                "mqtt condition: "
                f"status={battery.charging_status!r} "
                f"current={battery.charge_current_a!r} "
                f"gun_ac={battery.ac_gun_connected!r} "
                f"last={mqtt.last_updated_timestamp!r}"
            )
        except DeepalError as exc:
            print(f"mqtt condition failed: {type(exc).__name__}: {exc}")

        plan_id = (
            args.plan_id
            or condition.battery.charge_plan_id
            or "1"
        )
        if sum((args.validity, args.add_plan, args.delete_plan)) > 1:
            parser.error("--validity, --add-plan and --delete-plan are mutually exclusive")
        if args.validity:
            payload = {
                "command": "COMMAND_VALID_CHARGE_PLAN",
                "enabled": enabled,
                "planId": str(plan_id),
            }
        elif args.delete_plan:
            payload = {
                "command": "delete_charge_plan",
                "planId": str(plan_id),
            }
        elif args.add_plan:
            payload = {
                "command": "add_charge_plan",
                "endSwitch": 1 if enabled else 0,
                "endTime": args.end,
                "planType": args.plan_type,
                "startTime": args.start,
                "timeFormat": args.time_format,
                "timeZone": time_zone,
            }
        else:
            payload = {
                "command": "modify-plan",
                "endSwitch": 1 if enabled else 0,
                "endTime": args.end,
                "planId": str(plan_id),
                "planType": args.plan_type,
                "startTime": args.start,
                "timeFormat": args.time_format,
                "timeZone": time_zone,
            }
        print(f"payload to sign: {json.dumps(payload, ensure_ascii=False)}")

        if not args.apply:
            print("\nDry run only. Re-run with --apply to send the command.")
            return 0

        if args.wake:
            print("\nWaking the vehicle...")
            try:
                await client.wake_vehicle(vehicle.car_id)
            except DeepalError as exc:
                print(f"wake failed: {type(exc).__name__}: {exc}")
                return 2
            print("wake acknowledged; waiting 10 s for the car to report")
            await asyncio.sleep(10)

        if args.validity:
            mode = "validity"
        elif args.delete_plan:
            mode = "delete-plan"
        elif args.add_plan:
            mode = "add-plan"
        else:
            mode = "modify-plan"
        print(f"\nSending {mode}...")
        try:
            if args.validity:
                command_id = await client.control_charge_plan_validity(
                    vehicle.car_id,
                    plan_id,
                    enabled,
                )
            elif args.delete_plan:
                command_id = await client.control_charge_plan_delete(
                    vehicle.car_id,
                    plan_id,
                )
            elif args.add_plan:
                command_id = await client.control_charge_plan_add(
                    vehicle.car_id,
                    args.start,
                    args.end,
                    1 if enabled else 0,
                    args.plan_type,
                    args.time_format,
                    time_zone,
                )
            else:
                command_id = await client.control_charge_schedule(
                    vehicle.car_id,
                    plan_id,
                    args.start,
                    args.end,
                    enabled,
                    args.plan_type,
                    args.time_format,
                    time_zone,
                )
        except DeepalError as exc:
            print(f"command failed: {type(exc).__name__}: {exc}")
            return 2
        print(f"command_id={command_id!r}")

        await _poll(client, vehicle, command_id, args.watch)
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
