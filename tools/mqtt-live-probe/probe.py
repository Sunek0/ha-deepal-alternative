#!/usr/bin/env python3
"""Read-only live MQTT probe for an international Deepal vehicle.

The probe reuses the integration's CA/MQTT bootstrap, opens one long-lived
connection, subscribes to the configured telemetry topics, logs in and then
only reads. It never publishes a condition request, a wake or a command; the
only writes are the MQTT login, the logout and the protocol acknowledgements
(PUBACK/PINGREQ).

Use it to verify, with the phone app and the car, which changes arrive as
unsolicited ``properties/report`` / ``events/up`` messages and whether the app
stays connected while the probe is listening.

The access token is used as stored by Home Assistant; the script does not
refresh the account session, so it cannot rotate the refresh token and log the
integration out. If the token has expired, run the integration refresh first
and start the probe again.

Examples:

    python tools/mqtt-live-probe/probe.py --seconds 300
    python tools/mqtt-live-probe/probe.py --seconds 600 --dump-params
    python tools/mqtt-live-probe/probe.py --entry-file /path/to/token.json

See README.md in this folder for the safety notes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for candidate in (ROOT / "deepal_sdk", Path.cwd() / "deepal_sdk"):
    if candidate.is_dir() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from deepal import DeepalError, DeepalIntlClient  # noqa: E402
from deepal.mqtt import (  # noqa: E402
    build_puback_packet,
    config_mqtt_identity,
    parse_publish,
    read_packet_with_keepalive,
)
from deepal.redact import redact_for_log, redact_topic  # noqa: E402


DEFAULT_ENTRY = Path("/mnt/ha-config/.storage/core.config_entries")

#: Parameters worth showing by default. The probe prints only the keys the
#: vehicle actually reports, so a missing field is visibly missing.
_INTERESTING_PARAMS = (
    "latestDate",
    "lastUpdatedTime",
    "lastUpdatedAt",
    "soc",
    "socDsp",
    "remainPower",
    "ChrgSts",
    "chargeConStatus",
    "acChargeGunConnectionState",
    "dcChargeGunConnectionState",
    "BattACChrgInCurr",
    "BattDCChrgInCurr",
    "chargDeltMins",
    "driverDoor",
    "passengerDoor",
    "leftRearDoor",
    "rightRearDoor",
    "trunk",
    "driverDoorLock",
    "passengerDoorLock",
    "diverWindow",
    "passengerWindow",
    "leftRearWindow",
    "rightRearWindow",
    "airStatus",
    "airConditioningSetTemperature",
    "steeringWheelHeating",
    "frontDefrostStatus",
    "powerStatusFeedBack",
    "totalOdometer",
    "remainedPowerMile",
)


def _iso_now() -> str:
    """Return a compact UTC timestamp for each printed line."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def _load_entry(path: Path, entry_id: str | None) -> dict[str, Any]:
    """Load a Deepal entry from an HA storage file or a token file."""
    try:
        raw = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except PermissionError as exc:
        raise SystemExit(
            f"Cannot read {path}: {exc}. Run the script with sudo, or copy the "
            "entry to a private file and pass --entry-file."
        ) from exc
    except FileNotFoundError as exc:
        raise SystemExit(f"Entry file not found: {path}") from exc

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
        return dict(entry.get("data") or {})

    data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    if not isinstance(data, dict) or not data.get("access_token"):
        raise SystemExit(
            f"{path} does not look like an HA config entry or a token file."
        )
    if "private_key_pem" in data and "private_key" not in data:
        data = dict(data)
        data["private_key"] = data.get("private_key_pem")
    return dict(data)


def _build_client(data: dict[str, Any], *, debug: bool) -> DeepalIntlClient:
    """Build the international client from the stored entry data."""
    client = DeepalIntlClient(
        country=str(data.get("country") or "ES").upper(),
        environment=str(data.get("environment") or "release_eu"),
        enable_api_logging=debug,
    )
    client.access_token = data.get("access_token")
    client.refresh_token = data.get("refresh_token")
    client.cac_token = data.get("cac_token")
    client.user_id = data.get("user_id")
    client.device_id = data.get("device_id") or client.device_id
    private_key = data.get("private_key")
    if private_key:
        try:
            client.set_login_keypair(private_key, data.get("public_key"))
        except (ValueError, TypeError):
            # The probe only needs the MQTT path; an unusable signing key does
            # not affect it.
            pass
    return client


def _select_vehicle(vehicles: list[Any], selector: str | None) -> Any:
    """Return the requested MQTT vehicle, or the first one."""
    mqtt_vehicles = [
        vehicle
        for vehicle in vehicles
        if DeepalIntlClient.is_mqtt_vehicle(vehicle)
        and not DeepalIntlClient.is_sda_mqtt_vehicle(vehicle)
    ]
    if not mqtt_vehicles:
        raise SystemExit(
            "The account has no protocolType MQTT vehicle (SDA-MQTT is excluded)."
        )
    if selector is None:
        return mqtt_vehicles[0]
    wanted = selector.casefold()
    for vehicle in mqtt_vehicles:
        if wanted in {
            str(vehicle.car_id).casefold(),
            str(vehicle.vin or "").casefold(),
        }:
            return vehicle
    raise SystemExit(
        "The requested vehicle does not match a protocolType MQTT vehicle."
    )


def _topic_kind(topic: str) -> str:
    """Return a short, non-identifying suffix for a topic."""
    safe = redact_topic(topic)
    if "$vdp/[redacted]" in safe:
        return safe.split("$vdp/[redacted]", 1)[1]
    return safe


def _summarize_params(params: dict[str, Any]) -> dict[str, Any]:
    """Return the interesting, redacted subset of one decoded report."""
    selected = {
        key: params[key] for key in _INTERESTING_PARAMS if key in params
    }
    return redact_for_log(selected, max_string_length=120)


def _payload_summary(payload: dict[str, Any], params: dict[str, Any]) -> str:
    """Return a compact one-line description of a received message."""
    parts = [
        f"mt={payload.get('mt')!r}",
        f"r={str(payload.get('r'))[-6:]!r}",
        f"params={len(params)}",
    ]
    if payload.get("sers"):
        parts.append("sers=encrypted")
    if payload.get("rs"):
        parts.append("rs=encrypted")
    if params:
        parts.append(
            "data="
            + json.dumps(
                _summarize_params(params),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    return " ".join(parts)


async def _run(
    client: DeepalIntlClient,
    vehicle: Any,
    *,
    seconds: float,
    dump_params: bool,
    jsonl_path: Path | None,
) -> int:
    """Open one read-only live session and print the messages it receives."""
    config = await client.get_mqtt_config(vehicle.car_id)
    token = await client.get_mqtt_token()
    reader, writer, resolved, basic_info, secret_key, _plan, settings = (
        await client._open_s05_mqtt(config, token, vehicle_id=vehicle.car_id)
    )
    logout = client._logout_context(resolved, basic_info, secret_key, settings)

    # Identity diagnostics without printing the identifiers themselves.
    client_id, username = config_mqtt_identity(
        config,
        resolved.login_did,
        client_id=client.mqtt_client_id,
        username=client.mqtt_username,
    )
    print(
        f"{_iso_now()} connected: "
        f"client_id_is_login_did={client_id == resolved.login_did} "
        f"username_is_login_did={username == resolved.login_did} "
        f"qos={settings.effective_qos} keepalive={settings.effective_keepalive}s "
        f"subscriptions={len(resolved.subscriptions)}",
        flush=True,
    )
    print(
        "Read-only probe: login/subscribe/read only; no condition request, "
        "wake or command will be published.",
        flush=True,
    )

    topics = {_topic_kind(topic) for topic in resolved.subscriptions}
    print(
        f"Subscribed: {', '.join(sorted(topic for topic in topics if topic))}",
        flush=True,
    )

    counts: dict[str, int] = {}
    reports = 0
    events = 0
    pings = 0
    errors = 0
    last_report_at: float | None = None
    plan_seen = False
    started = time.monotonic()
    deadline = started + max(0.0, seconds)
    jsonl = (
        jsonl_path.expanduser().open("w", encoding="utf-8") if jsonl_path else None
    )

    try:
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                first, body = await read_packet_with_keepalive(
                    reader,
                    writer,
                    min(remaining, max(5.0, settings.effective_keepalive)),
                    settings.effective_keepalive,
                )
            except asyncio.TimeoutError:
                print(
                    f"{_iso_now()} idle: no message for "
                    f"{min(seconds, settings.effective_keepalive):.0f}s",
                    flush=True,
                )
                continue
            except (asyncio.IncompleteReadError, ConnectionError, OSError) as exc:
                errors += 1
                print(f"{_iso_now()} connection closed: {type(exc).__name__}: {exc}")
                break

            packet_type = first >> 4
            if packet_type == 13:  # PINGRESP
                pings += 1
                print(f"{_iso_now()} pingresp", flush=True)
                continue
            if packet_type != 3:  # not a PUBLISH
                print(
                    f"{_iso_now()} packet_type={packet_type}",
                    flush=True,
                )
                continue

            try:
                topic, payload, packet_id = parse_publish(first, body)
            except ValueError as exc:
                errors += 1
                print(f"{_iso_now()} malformed publish: {exc}", flush=True)
                continue

            if packet_id is not None:
                writer.write(build_puback_packet(packet_id))
                await writer.drain()

            params = client._s05_params_from_payload(payload, secret_key)
            kind = _topic_kind(topic)
            counts[kind] = counts.get(kind, 0) + 1
            if params:
                reports += 1
                last_report_at = time.monotonic()
                if "chargePlanList" in params:
                    plan_seen = True
            if "/events/" in topic or "/msg/" in topic or "/strategy/" in topic:
                events += 1

            line = (
                f"{_iso_now()} {kind:32} "
                f"{_payload_summary(payload, params)}"
            )
            print(line, flush=True)
            if dump_params and params:
                print(
                    "  params="
                    + json.dumps(
                        redact_for_log(params, max_string_length=200),
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    flush=True,
                )
            if jsonl is not None:
                jsonl.write(
                    json.dumps(
                        {
                            "ts": _iso_now(),
                            "topic": kind,
                            "mt": payload.get("mt"),
                            "request_id_tail": str(payload.get("r"))[-6:],
                            "params": redact_for_log(
                                params, max_string_length=200
                            ),
                            "param_count": len(params),
                            "has_sers": bool(payload.get("sers")),
                            "has_rs": bool(payload.get("rs")),
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
                jsonl.flush()
    finally:
        if jsonl is not None:
            jsonl.close()
        close = await client._close_s05_mqtt(
            writer,
            vehicle_id=vehicle.car_id,
            logout=logout,
            timeout=settings.connect_timeout,
        )
        duration = time.monotonic() - started
        print(
            f"{_iso_now()} closed: duration={duration:.1f}s "
            f"messages={sum(counts.values())} reports={reports} "
            f"events={events} pings={pings} errors={errors} "
            f"logout_sent={close.logout_sent} logout_error={close.logout_error!r}",
            flush=True,
        )
        if last_report_at is not None:
            print(
                f"Last decoded report was {time.monotonic() - last_report_at:.1f}s "
                "before the end.",
                flush=True,
            )
        print(
            f"Topics seen: {json.dumps(counts, ensure_ascii=False, sort_keys=True)}",
            flush=True,
        )
        print(f"chargePlanList seen over MQTT: {plan_seen}", flush=True)

    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry-file", default=str(DEFAULT_ENTRY))
    parser.add_argument("--entry-id", default=None)
    parser.add_argument(
        "--vehicle",
        default=None,
        help="car_id or VIN; defaults to the first protocolType MQTT vehicle.",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=300.0,
        help="How long to listen (default 300).",
    )
    parser.add_argument(
        "--dump-params",
        action="store_true",
        help="Print every decoded report's redacted parameters.",
    )
    parser.add_argument(
        "--jsonl",
        default=None,
        help="Write one redacted JSON object per message to this file.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable the SDK's redacted API logging.",
    )
    args = parser.parse_args()

    data = _load_entry(Path(args.entry_file), args.entry_id)
    client = _build_client(data, debug=args.debug)
    try:
        if not client.user_id:
            raise SystemExit(
                "The entry has no user_id; MQTT requires a completed login. "
                "Re-authenticate the integration first."
            )
        vehicles = await client.get_vehicles()
        vehicle = _select_vehicle(vehicles, args.vehicle)
        print(
            f"{_iso_now()} probing vehicle "
            f"({vehicle.series_name or 'unknown model'}) for {args.seconds:.0f}s",
            flush=True,
        )
        return await _run(
            client,
            vehicle,
            seconds=args.seconds,
            dump_params=args.dump_params,
            jsonl_path=Path(args.jsonl) if args.jsonl else None,
        )
    except KeyboardInterrupt:
        print(f"{_iso_now()} interrupted", flush=True)
        return 130
    except DeepalError as exc:
        print(f"{_iso_now()} error: {type(exc).__name__}: {exc}", flush=True)
        return 1
    finally:
        await client.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
