"""Read-only SDA MQTT broker probe for the Deepal E07.

Runs on the tester's computer: no phone, no mitmproxy, no certificate to
install. It logs in with the account, asks the SDA gateway for the broker
configuration the app uses (``get-mqtt-server-config``) and for the ``vot-auth``
auth token, connects to the broker with the identity candidates and reports:

* which CONNECT identity the broker accepts (the ``authType 2`` question);
* which topics the account is allowed to subscribe to (SUBACK reason codes);
* everything the broker sends while it listens, with tokens, identifiers, plate
  and location masked, and with any encrypted ``sers`` list decoded locally.

It NEVER publishes a control command. The only publish it can do is the
``loginout`` exchange, and only with ``--allow-login``, because opening a
session may kick the app on the phone.

What this answers and what it does not: it answers how the SDA broker session
works (identity, topics, login exchange, and whether the account can *observe*
the app's own commands). It does not replace the MQTT capture for the command
codes: if the app's ``sers`` is encrypted with a per-session key this probe
cannot see, the codes still need the ``tools/sda-mqtt-capture`` kit.

Usage:
    DEEPAL_EMAIL=you@example.com DEEPAL_PASSWORD=secret \
        python tools/sda-mqtt-probe/probe.py --country AU --environment release_ase
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import ssl
import sys
import time
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "deepal_sdk"))

from deepal import DeepalIntlClient  # noqa: E402
from deepal.endpoints import INTL_CA_APP_APIGW_GET_AUTH_TOKEN  # noqa: E402
from deepal.exceptions import DeepalError  # noqa: E402
from deepal.mqtt import (  # noqa: E402
    LOGIN_PUB_TOPIC_TEMPLATE,
    MQTT_DEFAULT_KEEPALIVE,
    aes_cbc_decrypt,
    basic_identifiers,
    build_connect_packet,
    build_publish_packet,
    build_subscribe_packet,
    login_request_payload,
    new_request_id,
    parse_connack,
    parse_publish,
    read_packet_with_keepalive,
    resolve_mqtt_topics,
    secret_from_login_payload,
)
from deepal.redact import redact_for_log  # noqa: E402

#: The app's broker bootstrap for SDA cars (issue #2 trace, 1-oct-2026).
SDA_MQTT_SERVER_CONFIG = (
    "/app-apigw/sda-app-control/api/v1/sda-app/car-ctrl/get-mqtt-server-config"
)

#: Topics a control command could ever use. The probe must never publish to one.
CONTROL_TOPIC_MARKERS = ("/commands/", "/set/", "/client/action")

#: CONNECT reason codes worth naming in the log.
CONNACK_REASONS = {
    0x00: "success",
    0x80: "unspecified error",
    0x81: "malformed packet",
    0x82: "protocol error",
    0x83: "implementation specific error",
    0x84: "unsupported protocol version",
    0x85: "client identifier not valid",
    0x86: "bad user name or password",
    0x87: "not authorized",
    0x88: "server unavailable",
    0x89: "server busy",
    0x8A: "banned",
    0x8C: "bad authentication method",
    0x90: "topic name invalid",
    0x95: "packet too large",
    0x97: "quota exceeded",
    0x99: "payload format invalid",
    0x9A: "retain not supported",
    0x9B: "QoS not supported",
    0x9E: "connection rate exceeded",
}

SUBACK_REASONS = {
    0x00: "granted QoS 0",
    0x01: "granted QoS 1",
    0x02: "granted QoS 2",
    0x80: "not authorized",
    0x83: "implementation specific error",
    0x87: "not authorized",
    0x8F: "topic filter invalid",
    0x91: "packet identifier in use",
    0x97: "quota exceeded",
    0x9E: "shared subscriptions not supported",
    0xA1: "subscription identifiers not supported",
    0xA2: "wildcard subscriptions not supported",
}

_LOG_FILE: Optional[Any] = None


def log(message: str = "") -> None:
    """Write one redacted line to the console and, when open, the log file."""
    print(message, flush=True)
    if _LOG_FILE is not None:
        _LOG_FILE.write(message + "\n")
        _LOG_FILE.flush()


def mask_identifier(value: Any) -> str:
    """Return a stable short tag so ids stay comparable without being revealed."""
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:8]


def mask_topic(topic: str) -> str:
    """Mask the ``$vdp/<did>`` device segment of an MQTT topic."""
    if not topic.startswith("$vdp/"):
        return topic
    parts = topic.split("/", 2)
    if len(parts) < 3:
        return topic
    return f"$vdp/<did:{mask_identifier(parts[1])}>/{parts[2]}"


#: Credential spellings the probe must never write to the log.
_SECRET_KEYS = {
    "secretkey",
    "seriralno",
    "serialno",
    "password",
    "username",
    "userid",
    "authcode",
    "safecode",
}

#: Identifier spellings that keep a stable tag so messages stay comparable.
_TAG_KEYS = {
    "did",
    "devicedid",
    "deviceid",
    "cid",
    "uid",
    "ruid",
    "clientid",
    "carid",
    "vehicleid",
    "vin",
}


def mask_value(key: str, value: Any) -> Any:
    """Mask the spellings the SDK redactor does not cover on its own."""
    compact = str(key).lower().replace("_", "")
    if compact in _SECRET_KEYS:
        return f"<{key}:{len(str(value))} chars>"
    if compact in _TAG_KEYS:
        return f"<{key}:{mask_identifier(value)}>"
    return None


def redact(value: Any) -> Any:
    """Redact a JSON payload for the log, masking ``secretKey`` explicitly."""
    if isinstance(value, dict):
        return {
            key: (mask_value(key, item) or redact(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return redact_for_log(value)


def decode_sers(
    parsed: dict[str, Any], secret_key: Optional[str]
) -> dict[str, Any]:
    """Return a log-ready copy of a payload with ``sers`` decoded when possible."""
    out = dict(parsed)
    sers = out.pop("sers", None)
    if not isinstance(sers, str):
        return out
    out["sers_ciphertext_chars"] = len(sers)
    if not secret_key:
        out["sers_decoded"] = "<unavailable: no secretKey yet>"
        return out
    try:
        out["sers_decoded"] = aes_cbc_decrypt(sers, secret_key, out.get("r", ""))
    except Exception as exc:  # noqa: BLE001 - a probe never aborts on a bad frame
        out["sers_decoded"] = f"<unavailable: {type(exc).__name__}>"
    return out


def parse_broker_config(raw: Any) -> dict[str, Any]:
    """Pull host, port, cluster and auth type out of the config response."""
    payload: Any = raw
    if isinstance(payload, dict):
        for key in ("data", "params"):
            value = payload.get(key)
            if isinstance(value, dict) and value:
                payload = value
                break
    if not isinstance(payload, dict):
        return {}
    infos = payload.get("mqttConnectionInfos")
    if isinstance(infos, list) and infos and isinstance(infos[0], dict):
        payload = {**payload, **infos[0]}
    return {
        "host": payload.get("host") or payload.get("mqttHost"),
        "port": payload.get("port") or payload.get("mqttPort"),
        "cluster_name": payload.get("clusterName"),
        "auth_type": payload.get("authType"),
        "identity": payload,
    }


def connect_candidates(
    config: dict[str, Any],
    auth_token: Optional[str],
    login_did: str,
    secret_key: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Build the CONNECT identity candidates the probe tries in order.

    The app's ``authType 2`` handshake is not documented, so the probe tries the
    identity the configuration reports (when it carries one) and the auth token
    in the roles the sibling CA broker uses.
    """
    identity = config.get("identity") or {}
    reported_client = identity.get("clientId") or identity.get("client_id")
    reported_user = identity.get("userName") or identity.get("username")
    reported_password = identity.get("password")

    candidates: list[dict[str, Any]] = []

    def add(label: str, client_id: Any, username: Any, password: Any) -> None:
        if not (client_id and username and password):
            return
        entry = {
            "label": label,
            "client_id": str(client_id),
            "username": str(username),
            "password": str(password),
        }
        if entry not in candidates:
            candidates.append(entry)

    add("config-reported identity", reported_client, reported_user, reported_password)
    if secret_key:
        add(
            "config identity + secretKey",
            reported_client or login_did,
            reported_user or login_did,
            secret_key,
        )
    add("authToken as password", login_did, login_did, auth_token)
    add("authToken as username and password", login_did, auth_token, auth_token)
    add("authToken as client id", auth_token, login_did, auth_token)
    return candidates


def parse_suback(first: int, body: bytes) -> tuple[Optional[int], list[int]]:
    """Parse a SUBACK into ``(packet_id, reason_codes)``."""
    if first >> 4 != 9 or len(body) < 3:
        return None, []
    return int.from_bytes(body[:2], "big"), list(body[2:])


async def fetch_broker_config(
    client: DeepalIntlClient, car_id: str
) -> dict[str, Any]:
    """Ask the SDA gateway for the broker configuration the app uses."""
    raw = await client._request(  # noqa: SLF001 - inherits the SDA token handling
        SDA_MQTT_SERVER_CONFIG,
        auth_required=True,
        base_url=client.sda_base_url,
        method="GET",
        query={"carId": car_id},
    )
    config = parse_broker_config(raw)
    log("Broker configuration (masked):")
    log("  " + json.dumps(redact(raw), ensure_ascii=False, sort_keys=True)[:800])
    return config


async def fetch_auth_token(client: DeepalIntlClient) -> Optional[str]:
    """Fetch the ``vot-auth`` auth token on the SDA host, trying GET then POST."""
    attempts = (
        ("GET", {"userId": client.user_id}, None),
        ("POST", None, {"userId": client.user_id}),
    )
    for method, query, body in attempts:
        query = {k: v for k, v in (query or {}).items() if v}
        body = {k: v for k, v in (body or {}).items() if v}
        if not query and not body:
            continue
        try:
            raw = await client._request(  # noqa: SLF001
                INTL_CA_APP_APIGW_GET_AUTH_TOKEN,
                json_data=body,
                auth_required=True,
                base_url=client.sda_base_url,
                method=method,
                query=query,
            )
        except DeepalError as exc:
            log(f"  authToken via {method} {sorted(query or body)}: {exc}")
            continue
        if isinstance(raw, dict) and raw.get("authToken"):
            log(f"  authToken via {method} {sorted(query or body)}: captured")
            return str(raw["authToken"])
        log(f"  authToken via {method}: response without authToken (masked below)")
        log("    " + json.dumps(redact(raw), ensure_ascii=False)[:300])
    return None


async def open_broker(host: str, port: int, timeout: float):
    """Open a verified TLS connection to the broker."""
    context = ssl.create_default_context()
    return await asyncio.wait_for(
        asyncio.open_connection(host, port, ssl=context, server_hostname=host),
        timeout,
    )


async def listen(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    seconds: float,
    secret_holder: dict[str, Optional[str]],
) -> list[dict[str, Any]]:
    """Log every PUBLISH the broker sends during the window."""
    seen: list[dict[str, Any]] = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            first, body = await read_packet_with_keepalive(
                reader,
                writer,
                min(5.0, max(0.1, deadline - time.monotonic())),
                keepalive=MQTT_DEFAULT_KEEPALIVE / 2,
            )
        except asyncio.TimeoutError:
            continue
        except (asyncio.IncompleteReadError, ConnectionError, OSError) as exc:
            log(f"  connection closed while listening: {type(exc).__name__}")
            break
        kind = first >> 4
        if kind != 3:
            log(f"  <- {kind} (control packet)")
            continue
        try:
            topic, payload, _ = parse_publish(first, body)
        except (ValueError, UnicodeDecodeError) as exc:
            log(f"  <- PUBLISH with a payload the probe could not parse: {exc}")
            continue
        found = secret_from_login_payload(payload)
        if found and not secret_holder.get("secret_key"):
            secret_holder["secret_key"] = found
            log(
                "  secretKey captured from a login response "
                f"({len(found)} chars); sers decoding enabled"
            )
        entry = {
            "topic": topic,
            "payload": decode_sers(payload, secret_holder.get("secret_key")),
        }
        seen.append(entry)
        log(f"  <- PUBLISH topic={mask_topic(topic)}")
        log("     " + json.dumps(redact(entry["payload"]), ensure_ascii=False)[:800])
    return seen


async def probe_broker(
    config: dict[str, Any],
    auth_token: Optional[str],
    login_did: str,
    subscriptions: list[str],
    *,
    seconds: float,
    allow_login: bool,
    timeout: float,
    secret_key: Optional[str] = None,
) -> dict[str, Any]:
    """Try the identity candidates, subscribe and listen. Never sends a command."""
    host = config.get("host")
    port = config.get("port")
    if not host or not port:
        log("No broker host/port in the configuration; nothing to probe.")
        return {"connected": False, "reason": "no broker configuration"}
    port = int(port)
    log(f"Connecting to {host}:{port} (TLS, verified)")
    log(f"  cluster={config.get('cluster_name')} authType={config.get('auth_type')}")

    candidates = connect_candidates(config, auth_token, login_did, secret_key)
    if not candidates:
        log("No CONNECT identity candidates to try; nothing to probe.")
        return {"connected": False, "reason": "no candidates"}

    report: dict[str, Any] = {"connected": False, "attempts": [], "messages": []}
    reader = writer = None
    for candidate in candidates:
        log(f"  CONNECT as {candidate['label']}")
        try:
            reader, writer = await open_broker(host, port, timeout)
        except (OSError, asyncio.TimeoutError) as exc:
            log(f"    connection failed: {type(exc).__name__}: {exc}")
            report["attempts"].append(
                {"label": candidate["label"], "error": type(exc).__name__}
            )
            continue
        writer.write(
            build_connect_packet(
                candidate["client_id"], candidate["username"], candidate["password"]
            )
        )
        await writer.drain()
        try:
            first, body = await asyncio.wait_for(
                read_packet_with_keepalive(reader, writer, timeout),
                timeout + 5,
            )
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, OSError) as exc:
            log(f"    no CONNACK: {type(exc).__name__}")
            report["attempts"].append(
                {"label": candidate["label"], "error": type(exc).__name__}
            )
            writer.close()
            continue
        session_present, reason = parse_connack(first, body)
        name = CONNACK_REASONS.get(reason, f"0x{reason:02X}" if reason else "unknown")
        log(f"    CONNACK session_present={session_present} reason={name}")
        report["attempts"].append(
            {"label": candidate["label"], "reason": reason, "reason_name": name}
        )
        if reason == 0:
            report["connected"] = True
            report["identity"] = candidate["label"]
            break
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass
        reader = writer = None

    if not report["connected"] or reader is None or writer is None:
        log("No candidate was accepted by the broker.")
        return report

    if subscriptions:
        writer.write(build_subscribe_packet(1, subscriptions))
        await writer.drain()
        try:
            first, body = await asyncio.wait_for(
                read_packet_with_keepalive(reader, writer, timeout), timeout + 5
            )
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, OSError):
            log("  no SUBACK")
        else:
            packet_id, reasons = parse_suback(first, body)
            report["subscriptions"] = [
                {
                    "topic": mask_topic(topic),
                    "reason": reason,
                    "reason_name": SUBACK_REASONS.get(reason, f"0x{reason:02X}"),
                }
                for topic, reason in zip(subscriptions, reasons)
            ]
            log(f"  SUBACK id={packet_id}")
            for entry in report["subscriptions"]:
                log(f"    {entry['topic']} -> {entry['reason_name']}")

    secret_holder: dict[str, Optional[str]] = {"secret_key": secret_key}
    if allow_login:
        topic = LOGIN_PUB_TOPIC_TEMPLATE % login_did
        if any(marker in topic for marker in CONTROL_TOPIC_MARKERS):
            log("  refusing to publish on a control topic; skipping the login")
        else:
            payload = login_request_payload(
                login_did,
                new_request_id(login_did),
                basic_identifiers(ruid=login_did),
            )
            log(f"  -> PUBLISH loginout on {mask_topic(topic)} (opens a session)")
            writer.write(build_publish_packet(topic, payload))
            await writer.drain()
    else:
        log("  (login exchange skipped: pass --allow-login to open a session)")

    log(f"Listening for {seconds:g} s; press lock/unlock in the app now if asked to")
    report["messages"] = await listen(reader, writer, seconds, secret_holder)
    report["secret_key_seen"] = bool(secret_holder.get("secret_key"))

    writer.write(b"\xe0\x00")  # DISCONNECT
    await writer.drain()
    writer.close()
    try:
        await writer.wait_closed()
    except OSError:
        pass
    return report


def probe_topics(config: dict[str, Any], login_did: str, wildcard: bool) -> list[str]:
    """Return the topics to subscribe to: the app's set plus the publish topics."""
    topics = resolve_mqtt_topics(config, login_did)
    subscriptions = list(topics.subscriptions)
    for candidate in (
        topics.login_publish,
        topics.properties_publish,
        topics.properties_set_publish,
    ):
        if candidate and candidate not in subscriptions:
            subscriptions.append(candidate)
    if wildcard:
        device_did = topics.device_did or login_did
        wildcard_topic = f"$vdp/{device_did}/#"
        if wildcard_topic not in subscriptions:
            subscriptions.append(wildcard_topic)
    return subscriptions


def build_client(args: argparse.Namespace) -> DeepalIntlClient:
    """Build the SDK client from the CLI arguments and the environment."""
    client = DeepalIntlClient(
        country=args.country,
        environment=args.environment,
        enable_api_logging=args.api_logging,
    )
    token = os.getenv("DEEPAL_ACCESS_TOKEN", "").strip()
    refresh = os.getenv("DEEPAL_REFRESH_TOKEN", "").strip()
    if token:
        client.access_token = token
        client.refresh_token = refresh or None
        log("Using the access token from DEEPAL_ACCESS_TOKEN (no login)")
    return client


async def run(args: argparse.Namespace) -> int:
    """Log in, probe the broker and write the report."""
    async with build_client(args) as client:
        if not client.access_token:
            email = os.getenv("DEEPAL_EMAIL", "").strip()
            password = os.getenv("DEEPAL_PASSWORD", "")
            code = os.getenv("DEEPAL_CODE", "").strip()
            if not email or not (password or code):
                log("Set DEEPAL_EMAIL and DEEPAL_PASSWORD (or DEEPAL_CODE), or")
                log("DEEPAL_ACCESS_TOKEN/DEEPAL_REFRESH_TOKEN, to run the probe.")
                return 2
            log(f"Logging in as {email[:2]}***@{email.split('@')[-1]} ({args.country})")
            if code:
                await client.login_with_email_code(email, code, args.country)
            else:
                await client.login_with_email_password(email, password, args.country)
            log(f"Logged in; account user id {'present' if client.user_id else 'MISSING'}")

        vehicles = await client.get_vehicles()
        if args.list_vehicles or not vehicles:
            log("Vehicles in this account:")
            for vehicle in vehicles:
                log(
                    f"  {vehicle.series_name or vehicle.model_name or '?'} "
                    f"car_id=<{mask_identifier(vehicle.car_id)}> "
                    f"protocol={vehicle.protocol_type} vin={'set' if vehicle.vin else 'unset'}"
                )
            if args.list_vehicles:
                return 0
        car_id = args.car_id or next(
            (
                vehicle.car_id
                for vehicle in vehicles
                if (vehicle.protocol_type or "").upper() == "SDA-MQTT"
            ),
            vehicles[0].car_id if vehicles else None,
        )
        if not car_id:
            log("No vehicle to probe.")
            return 2
        log(f"Probing car_id=<{mask_identifier(car_id)}>")

        config = await fetch_broker_config(client, car_id)
        auth_token = await fetch_auth_token(client)
        if auth_token is None:
            log("No vot-auth auth token; the probe will still try the config identity.")

        identity = config.get("identity") or {}
        topics = resolve_mqtt_topics(config, None)
        login_did = (
            topics.login_did
            or identity.get("did")
            or identity.get("loginDid")
            or car_id
        )
        subscriptions = probe_topics(config, login_did, args.wildcard)
        log("Subscriptions to request:")
        for topic in subscriptions:
            log(f"  {mask_topic(topic)}")

        report = await probe_broker(
            config,
            auth_token,
            login_did,
            subscriptions,
            seconds=args.seconds,
            allow_login=args.allow_login,
            timeout=args.timeout,
            secret_key=identity.get("secretKey"),
        )

        log("")
        log("Summary (safe to paste in the issue):")
        log(f"  connected: {report.get('connected')}")
        if report.get("identity"):
            log(f"  accepted identity: {report['identity']}")
        for attempt in report.get("attempts", []):
            log(
                f"  attempt: {attempt['label']} -> "
                f"{attempt.get('reason_name') or attempt.get('error')}"
            )
        log(f"  subscribed topics: {len(report.get('subscriptions', []))}")
        log(f"  messages received: {len(report.get('messages', []))}")
        log(f"  secretKey seen: {report.get('secret_key_seen')}")
        if report.get("messages"):
            decoded = sum(
                1
                for message in report["messages"]
                if isinstance(message["payload"].get("sers_decoded"), list)
            )
            log(f"  of those, sers decoded: {decoded}")
        return 0 if report.get("connected") else 1


def main() -> int:
    """Parse the arguments and run the probe."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--car-id", help="vehicle to probe (default: the SDA one)")
    parser.add_argument("--country", default="AU", help="sales country (default AU)")
    parser.add_argument(
        "--environment",
        default="release_ase",
        help="international environment id (default release_ase)",
    )
    parser.add_argument(
        "--seconds", type=float, default=90.0, help="listen window (default 90 s)"
    )
    parser.add_argument(
        "--allow-login",
        action="store_true",
        help="publish the loginout exchange (may kick the app session)",
    )
    parser.add_argument(
        "--wildcard",
        action="store_true",
        help="also subscribe to $vdp/<did>/# to observe the app's own frames",
    )
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--api-logging", action="store_true")
    parser.add_argument("--list-vehicles", action="store_true")
    parser.add_argument(
        "--log",
        default="sda-probe.log",
        help="redacted log file (default sda-probe.log)",
    )
    args = parser.parse_args()

    global _LOG_FILE  # noqa: PLW0603 - a tiny CLI, one log file
    path = Path(args.log)
    with path.open("a", encoding="utf-8") as handle:
        _LOG_FILE = handle
        log(f"--- SDA MQTT probe {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
        log("READ-ONLY: this never publishes a control command.")
        try:
            return asyncio.run(run(args))
        except DeepalError as exc:
            log(f"Deepal API error: {exc}")
            return 2
        except KeyboardInterrupt:
            log("Interrupted")
            return 130
        finally:
            log(f"--- end of probe (log: {path.resolve()}) ---")


if __name__ == "__main__":
    raise SystemExit(main())
