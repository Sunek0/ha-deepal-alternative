"""Minimal MQTT 5.0 transport and S05 payload helpers for the international platform.

This module implements the subset of MQTT 5.0 and the S05 parameter mapping that the
official app uses for MQTT-backed vehicles: CONNECT/SUBSCRIBE/PUBLISH/PUBACK/PINGREQ/
DISCONNECT packets over TLS and the AES-CBC (IV ``MD5(reqId)``) + base64 + gzip
encryption of service payloads. No external MQTT library is required.
"""

from __future__ import annotations

import asyncio
import base64
import gzip
import hashlib
import json
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Optional

from cryptography.hazmat.primitives import padding as symmetric_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

S05_SERVICE_CODES = (
    None,
    "car_condition",
    "BDC_Service",
    "BMS_Service",
    "OBC_Service",
    "THU_Service",
)

MQTT_PROTOCOL_LEVEL = 5
MQTT_DEFAULT_KEEPALIVE = 60

# Topic templates from the app's MqttConstantKt (1.12.0 DEX recovery).
LOGIN_PUB_TOPIC_TEMPLATE = "$vdp/%s/client/loginout"
LOGIN_SUB_TOPIC_TEMPLATE = "$vdp/%s/server/loginout"
EVENT_SUB_TOPIC_TEMPLATE = "$vdp/%s/%s/server/event"
EVENT_3D_SUB_TOPIC_TEMPLATE = "$vdp/%s/%s-3D/server/event"

# Command channels the one-shot telemetry exchange never consumes.
COMMAND_TOPIC_MARKERS = ("/commands/", "/set/", "/client/action")
COMMAND_MSG_TYPES = frozenset({"command", "commands", "cmd", "control", "set"})

# Basic identifiers of the app's ReqPayLoad ``b`` object.
BASIC_IDENTIFIER_KEYS = ("vin", "sc", "mc", "uid", "cid", "ruid")

MQTT_CONNACK_REASONS = {
    0x00: "success",
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
    0x8E: "topic name invalid",
    0x93: "receive maximum exceeded",
    0x95: "packet too large",
    0x97: "quota exceeded",
    0x99: "payload format invalid",
    0x9A: "retain not supported",
    0x9B: "qos not supported",
    0x9C: "use another server",
    0x9D: "server moved",
    0x9F: "connection rate exceeded",
}

MQTT_CLIENT_ID_KEYS = ("clientId", "client_id", "clientID", "client")
MQTT_USERNAME_KEYS = ("userName", "username", "user")


def mqtt_string(value: str) -> bytes:
    """Encode a length-prefixed MQTT UTF-8 string."""
    data = value.encode()
    return struct.pack("!H", len(data)) + data


def mqtt_remaining_length(length: int) -> bytes:
    """Encode the MQTT variable-length remaining length field."""
    out = bytearray()
    while True:
        encoded = length % 128
        length //= 128
        if length:
            encoded |= 128
        out.append(encoded)
        if not length:
            return bytes(out)


def build_connect_packet(
    client_id: str,
    username: str,
    password: str,
    keepalive: float = MQTT_DEFAULT_KEEPALIVE,
    clean_start: bool = True,
) -> bytes:
    """Build an MQTT 5.0 CONNECT packet with username/password credentials."""
    flags = 0xC0 | (0x02 if clean_start else 0x00)
    payload = mqtt_string(client_id) + mqtt_string(username) + mqtt_string(password)
    variable = (
        mqtt_string("MQTT")
        + bytes([MQTT_PROTOCOL_LEVEL, flags])
        + struct.pack("!H", max(0, min(0xFFFF, int(keepalive))))
        + b"\x00"
    )
    body = variable + payload
    return bytes([0x10]) + mqtt_remaining_length(len(body)) + body


def build_subscribe_packet(packet_id: int, topics: list[str]) -> bytes:
    """Build an MQTT 5.0 SUBSCRIBE packet with QoS 1 subscriptions."""
    payload = b"".join(mqtt_string(topic) + b"\x01" for topic in topics)
    body = struct.pack("!H", packet_id) + b"\x00" + payload
    return bytes([0x82]) + mqtt_remaining_length(len(body)) + body


def build_publish_packet(topic: str, payload: dict[str, Any]) -> bytes:
    """Build an MQTT 5.0 QoS 0 PUBLISH packet with a JSON payload."""
    body = (
        mqtt_string(topic)
        + b"\x00"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    )
    return bytes([0x30]) + mqtt_remaining_length(len(body)) + body


def build_puback_packet(packet_id: int) -> bytes:
    """Build the MQTT 5.0 PUBACK used to acknowledge a QoS 1 message."""
    return bytes([0x40, 0x04]) + struct.pack("!H", packet_id) + b"\x00\x00"


def build_pingreq_packet() -> bytes:
    """Build a PINGREQ packet."""
    return b"\xc0\x00"


def build_disconnect_packet(reason_code: int = 0x00) -> bytes:
    """Build an MQTT 5.0 DISCONNECT packet."""
    return bytes([0xE0, 0x02, reason_code & 0xFF, 0x00])


async def read_packet(reader: asyncio.StreamReader) -> tuple[int, bytes]:
    """Read one MQTT control packet and return its first byte and body."""
    first = (await reader.readexactly(1))[0]
    multiplier = 1
    remaining = 0
    while True:
        byte = (await reader.readexactly(1))[0]
        remaining += (byte & 0x7F) * multiplier
        if not byte & 0x80:
            break
        multiplier *= 128
    return first, await reader.readexactly(remaining)


async def read_packet_with_keepalive(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    timeout: float,
    keepalive: Optional[float] = None,
) -> tuple[int, bytes]:
    """Read one packet, sending PINGREQ when the keepalive elapses while waiting."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    interval = float(keepalive) if keepalive and keepalive > 0 else None
    next_ping = loop.time() + interval if interval else None
    task = asyncio.ensure_future(read_packet(reader))
    try:
        while True:
            now = loop.time()
            remaining = deadline - now
            if remaining <= 0:
                raise asyncio.TimeoutError
            wait = remaining
            if next_ping is not None:
                wait = min(wait, max(0.0, next_ping - now))
            done, _ = await asyncio.wait({task}, timeout=wait)
            if task in done:
                return task.result()
            now = loop.time()
            if next_ping is not None and now >= next_ping:
                writer.write(build_pingreq_packet())
                await writer.drain()
                next_ping = now + interval
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


def read_variable_byte_integer(data: bytes, pos: int = 0) -> tuple[int, int]:
    """Decode an MQTT variable byte integer, returning ``(value, new_pos)``."""
    multiplier = 1
    value = 0
    while pos < len(data):
        byte = data[pos]
        pos += 1
        value += (byte & 0x7F) * multiplier
        if not byte & 0x80:
            return value, pos
        multiplier *= 128
    raise ValueError("Truncated MQTT variable byte integer.")


def parse_connack(first: int, body: bytes) -> tuple[Optional[int], Optional[int]]:
    """Parse a CONNACK into ``(session_present, reason_code)``."""
    if first != 0x20 or len(body) < 2:
        return None, None
    return body[0] & 0x01, body[1]


def parse_publish(first: int, body: bytes) -> tuple[str, dict[str, Any], Optional[int]]:
    """Parse an MQTT 5.0 PUBLISH body into ``(topic, payload, packet_id)``."""
    pos = 0
    topic_len = struct.unpack("!H", body[pos : pos + 2])[0]
    pos += 2
    topic = body[pos : pos + topic_len].decode(errors="replace")
    pos += topic_len
    packet_id: Optional[int] = None
    if (first >> 1) & 0x03:
        packet_id = struct.unpack("!H", body[pos : pos + 2])[0]
        pos += 2
    properties_length, pos = read_variable_byte_integer(body, pos)
    pos += properties_length
    payload = json.loads(body[pos:].decode())
    return topic, payload, packet_id


def topic_device_id(topic: Optional[str]) -> Optional[str]:
    """Return the device id of a ``$vdp/<did>/...`` topic."""
    if not topic:
        return None
    parts = topic.split("/")
    if len(parts) > 2 and parts[0] == "$vdp":
        return parts[1]
    return None


def _first_mapping(value: Any) -> Optional[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, Mapping):
                return item
    return None


def _config_sources(config: Any) -> list[Mapping[str, Any]]:
    """Return the configuration blocks that may carry topics or identity values."""
    if not isinstance(config, Mapping):
        return []
    sources: list[Mapping[str, Any]] = [config]
    info = _first_mapping(config.get("mqttConnectionInfos"))
    if info is not None and info is not config:
        sources.append(info)
        cluster = _first_mapping(info.get("clusterInfos"))
        if cluster is not None:
            sources.append(cluster)
    return sources


def _first_string(source: Mapping[str, Any], keys: tuple[str, ...]) -> Optional[str]:
    for key in keys:
        value = source.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def config_mqtt_identity(
    config: Any,
    login_did: Optional[str],
    *,
    client_id: Optional[str] = None,
    username: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    """Resolve the MQTT client id and username, falling back to the login DID."""
    resolved_client = client_id
    resolved_user = username
    for source in _config_sources(config):
        if resolved_client is None:
            resolved_client = _first_string(source, MQTT_CLIENT_ID_KEYS)
        if resolved_user is None:
            resolved_user = _first_string(source, MQTT_USERNAME_KEYS)
    return resolved_client or login_did, resolved_user or login_did


def _normalize_msg_type(value: Any) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    return normalized or None


def _topic_entries(value: Any, msg_type: Optional[str] = None) -> list[tuple[str, Optional[str]]]:
    """Flatten a topic map/list into ``(topic, msg_type)`` pairs."""
    entries: list[tuple[str, Optional[str]]] = []
    if value is None:
        return entries
    if isinstance(value, str):
        return [(value, msg_type)]
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if key_text.startswith("$vdp"):
                if isinstance(item, str) and item:
                    entries.append((key_text, item))
                elif isinstance(item, Mapping):
                    entries.append(
                        (key_text, item.get("msgType") or item.get("msg_type"))
                    )
                else:
                    entries.append((key_text, None))
                continue
            if isinstance(item, str):
                entries.append((item, key_text))
            elif isinstance(item, Mapping):
                nested = (
                    item.get("pubTopics")
                    or item.get("subTopics")
                    or item.get("topics")
                )
                if nested is None and item.get("topic"):
                    nested = [item["topic"]]
                nested_type = item.get("msgType") or item.get("msg_type") or key_text
                entries.extend(_topic_entries(nested, nested_type))
            elif isinstance(item, (list, tuple)):
                for nested_item in item:
                    if isinstance(nested_item, str):
                        entries.append((nested_item, key_text))
                    elif isinstance(nested_item, Mapping):
                        nested_topic = (
                            nested_item.get("topic")
                            or nested_item.get("pubTopic")
                            or nested_item.get("subTopic")
                        )
                        nested_type = (
                            nested_item.get("msgType")
                            or nested_item.get("msg_type")
                            or key_text
                        )
                        if isinstance(nested_topic, str):
                            entries.append((nested_topic, nested_type))
        return entries
    if isinstance(value, (list, tuple)):
        for item in value:
            entries.extend(_topic_entries(item, msg_type))
    return entries


def _classify_topic(
    topic: str, msg_type: Optional[str], direction: Optional[str] = None
) -> Optional[str]:
    """Classify one candidate topic into the exchange role it can serve."""
    if not topic:
        return None
    lowered = topic.lower()
    if any(marker in lowered for marker in COMMAND_TOPIC_MARKERS):
        return "command"
    kind = _normalize_msg_type(msg_type)
    if kind in COMMAND_MSG_TYPES:
        return "command"
    if "loginout" in lowered:
        if "/client/" in lowered or direction == "pub":
            return "login_publish"
        return "login_subscribe"
    if kind in {"loginout", "login"}:
        return "login_publish" if direction == "pub" else "login_subscribe"
    if "properties" in lowered:
        if lowered.endswith("/res") or direction == "sub":
            return "properties_subscribe"
        return "properties_publish"
    if kind in {"properties", "property", "car_condition"}:
        return "properties_publish" if direction == "pub" else "properties_subscribe"
    if "event" in lowered or kind in {"event", "events"}:
        return "event"
    return None


@dataclass(frozen=True)
class MqttTopics:
    """Resolved publish/subscribe topics and device identities for one vehicle."""

    login_publish: Optional[str] = None
    login_subscribe: Optional[str] = None
    properties_publish: Optional[str] = None
    event_subscribe: Optional[str] = None
    subscriptions: tuple[str, ...] = ()
    login_did: Optional[str] = None
    device_did: Optional[str] = None

    @property
    def did(self) -> Optional[str]:
        return self.device_did or self.login_did


def _config_topic_entries(config: Any) -> list[tuple[str, Optional[str], Optional[str]]]:
    """Return ``(topic, msg_type, direction)`` triples from a connection config."""
    entries: list[tuple[str, Optional[str], Optional[str]]] = []
    for source in _config_sources(config):
        for topic_info in source.get("topicInfos") or []:
            if not isinstance(topic_info, Mapping):
                continue
            msg_type = topic_info.get("msgType") or topic_info.get("msg_type")
            for topic in topic_info.get("pubTopics") or []:
                if isinstance(topic, str):
                    entries.append((topic, msg_type, "pub"))
            for topic in topic_info.get("subTopics") or []:
                if isinstance(topic, str):
                    entries.append((topic, msg_type, "sub"))
        for key, direction in (
            ("pubTopicMap", "pub"),
            ("subTopicMap", "sub"),
            ("allSubTopics", "sub"),
        ):
            for topic, msg_type in _topic_entries(source.get(key)):
                entries.append((topic, msg_type, direction))
        topic_to_msgtype = source.get("topicToMsgtype") or source.get("topicToMsgType")
        if isinstance(topic_to_msgtype, Mapping):
            for topic, msg_type in topic_to_msgtype.items():
                if isinstance(topic, str) and isinstance(msg_type, str):
                    entries.append((topic, msg_type, None))
    return entries


def resolve_mqtt_topics(
    config: Any, fallback_did: Optional[str] = None
) -> MqttTopics:
    """Resolve telemetry topics from the CA connection configuration.

    Accepts the ``topicInfos`` list shape and the app's ``pubTopicMap``/
    ``subTopicMap``/``topicToMsgtype`` maps, and falls back to the app templates
    when the configuration omits a login or event topic.
    """
    entries = _config_topic_entries(config)

    selected: dict[str, str] = {}
    subscriptions: list[str] = []
    for topic, msg_type, direction in entries:
        kind = _classify_topic(topic, msg_type, direction)
        if kind is None:
            if direction == "sub":
                subscriptions.append(topic)
            continue
        if kind == "command":
            continue
        selected.setdefault(kind, topic)
        if direction == "sub" or kind in {
            "login_subscribe",
            "properties_subscribe",
            "event",
        }:
            subscriptions.append(topic)

    login_did = topic_device_id(
        selected.get("login_publish") or selected.get("login_subscribe")
    )
    device_did = topic_device_id(
        selected.get("properties_publish")
        or selected.get("properties_subscribe")
        or selected.get("login_publish")
        or selected.get("login_subscribe")
    )

    explicit_did: Optional[str] = None
    for source in _config_sources(config):
        explicit_did = _first_string(
            source, ("clientId", "client_id", "clientID", "client", "did", "userName")
        )
        if explicit_did:
            break
    did = device_did or login_did or explicit_did or fallback_did

    if not selected.get("properties_publish"):
        properties_subscribe = selected.get("properties_subscribe")
        if properties_subscribe and properties_subscribe.endswith("/res"):
            selected["properties_publish"] = properties_subscribe[:-4] + "/req"

    if did:
        selected.setdefault("login_publish", LOGIN_PUB_TOPIC_TEMPLATE % did)
        selected.setdefault("login_subscribe", LOGIN_SUB_TOPIC_TEMPLATE % did)
        selected.setdefault("event", EVENT_SUB_TOPIC_TEMPLATE % (did, did))
        login_did = login_did or did
        device_did = device_did or did

    for kind in ("login_subscribe", "event"):
        topic = selected.get(kind)
        if topic:
            subscriptions.append(topic)

    return MqttTopics(
        login_publish=selected.get("login_publish"),
        login_subscribe=selected.get("login_subscribe"),
        properties_publish=selected.get("properties_publish"),
        event_subscribe=selected.get("event"),
        subscriptions=tuple(dict.fromkeys(subscriptions)),
        login_did=login_did,
        device_did=device_did,
    )


def _b64decode(value: str) -> bytes:
    return base64.b64decode(value + "=" * ((4 - len(value) % 4) % 4))


def aes_cbc_decrypt(encrypted: str, secret_key: str, req_id: str) -> list[dict[str, Any]]:
    """Decrypt a service payload: AES-CBC + base64 + gzip + JSON list."""
    decryptor = Cipher(
        algorithms.AES(secret_key.encode()),
        modes.CBC(hashlib.md5(req_id.encode()).digest()),
    ).decryptor()
    padded = decryptor.update(_b64decode(encrypted)) + decryptor.finalize()
    unpadder = symmetric_padding.PKCS7(128).unpadder()
    plaintext = unpadder.update(padded) + unpadder.finalize()
    compressed = _b64decode(plaintext.decode().strip())
    decoded = json.loads(gzip.decompress(compressed).decode())
    return decoded if isinstance(decoded, list) else []


def aes_cbc_encrypt(services: list[dict[str, Any]], secret_key: str, req_id: str) -> str:
    """Encrypt service payloads the way the app does: base64(gzip(JSON)) in AES-CBC."""
    compressed_b64 = base64.b64encode(
        gzip.compress(
            json.dumps(services, ensure_ascii=False, separators=(",", ":")).encode()
        )
    )
    padder = symmetric_padding.PKCS7(128).padder()
    padded = padder.update(compressed_b64) + padder.finalize()
    encryptor = Cipher(
        algorithms.AES(secret_key.encode()),
        modes.CBC(hashlib.md5(req_id.encode()).digest()),
    ).encryptor()
    return base64.b64encode(encryptor.update(padded) + encryptor.finalize()).decode()


def secret_from_login_payload(payload: dict[str, Any]) -> Optional[str]:
    """Return the MQTT ``secretKey`` carried by a login response, if present."""
    for item in payload.get("rs") or []:
        if not isinstance(item, dict):
            continue
        for key in ("params", "data"):
            value = item.get(key)
            if isinstance(value, dict) and value.get("secretKey"):
                return str(value["secretKey"])
    return None


def iso_now() -> str:
    """Return the current UTC timestamp in the app's ISO format."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def new_request_id(device_id: str) -> str:
    """Build the per-request id used as the AES-CBC IV source."""
    return f"{device_id}_{datetime.now(UTC).timestamp() * 1_000_000:.0f}"


def basic_identifiers(
    *,
    ruid: Optional[str] = None,
    vin: Optional[str] = None,
    uid: Optional[str] = None,
    cid: Optional[str] = None,
    sc: Optional[str] = None,
    mc: Optional[str] = None,
) -> dict[str, Any]:
    """Build the ``b`` object of the app's ReqPayLoad, omitting unknown values."""
    candidates = {"vin": vin, "sc": sc, "mc": mc, "uid": uid, "cid": cid, "ruid": ruid}
    return {
        key: candidates[key]
        for key in BASIC_IDENTIFIER_KEYS
        if candidates[key] is not None
    }


def _filter_basic_info(basic_info: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    if not basic_info:
        return {}
    return {
        key: basic_info[key]
        for key in BASIC_IDENTIFIER_KEYS
        if basic_info.get(key) is not None
    }


def _set_optional_fields(
    payload: dict[str, Any],
    *,
    rt: Optional[str],
    ms: Optional[int],
    st: Optional[int],
    time_type: Optional[int],
) -> None:
    if rt is not None:
        payload["rt"] = rt
    if ms is not None:
        payload["ms"] = ms
    if st is not None:
        payload["st"] = st
    if time_type is not None:
        payload["timeType"] = time_type


def login_request_payload(
    login_did: str,
    req_id: str,
    basic_info: Optional[Mapping[str, Any]] = None,
    *,
    rt: Optional[str] = None,
    ms: Optional[int] = None,
    st: Optional[int] = None,
    time_type: Optional[int] = None,
) -> dict[str, Any]:
    """Build the MQTT ``loginout`` request that returns the ``secretKey``."""
    payload: dict[str, Any] = {
        "did": login_did,
        "r": req_id,
        "v": "v1.0.0",
        "mt": "loginout",
        "e": 0,
        "z": "unzip",
        "tf": 0,
        "dt": iso_now(),
        "sers": [
            {
                "service_code": "login",
                "params": {
                    "encryptEnable": 1,
                    "zipType": "gzip",
                    "ts": int(datetime.now(UTC).timestamp() * 1000),
                },
            }
        ],
        "b": _filter_basic_info(basic_info),
    }
    _set_optional_fields(payload, rt=rt, ms=ms, st=st, time_type=time_type)
    return payload


def condition_request_payload(
    device_did: str,
    login_did: str,
    secret_key: str,
    req_id: str,
    basic_info: Optional[Mapping[str, Any]] = None,
    *,
    rt: Optional[str] = "",
    ms: Optional[int] = None,
    st: Optional[int] = None,
    time_type: Optional[int] = None,
) -> dict[str, Any]:
    """Build the MQTT ``properties/get/req`` message that returns the condition."""
    services = [{"service_code": "car_condition", "params": {"fetchPropertyType": 0}}]
    identifiers = dict(basic_info or {})
    identifiers.setdefault("ruid", login_did)
    payload: dict[str, Any] = {
        "did": device_did,
        "r": req_id,
        "v": "v1.0.0",
        "mt": "properties",
        "e": 1,
        "z": "gzip",
        "tf": 0,
        "dt": iso_now(),
        "b": _filter_basic_info(identifiers),
        "sers": aes_cbc_encrypt(services, secret_key, req_id),
    }
    _set_optional_fields(payload, rt=rt, ms=ms, st=st, time_type=time_type)
    return payload


def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first(params: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = params.get(key)
        if value is not None:
            return value
    return None


def _seat_heat_level(value: Any) -> Optional[int]:
    """Convert the raw 0-6 seat heat gear to the app's 0-3 level scale."""
    parsed = _as_int(value)
    return parsed // 2 if parsed is not None else None


def _seat_vent_level(value: Any) -> Optional[int]:
    """Return the seat ventilation level (reported 1:1, unlike heat)."""
    return _as_int(value)


def _to_millis(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return int(datetime.now(UTC).timestamp() * 1000)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return int(parsed.timestamp() * 1000)
    return int(datetime.now(UTC).timestamp() * 1000)


def normalize_s05_params(params: dict[str, Any]) -> dict[str, Any]:
    """Map S05 MQTT parameter names into the shared international condition shape."""
    latest = _first(params, "lastUpdatedTime", "lastUpdatedAt", "latestDate")
    return {
        "lastUpdatedAt": _to_millis(latest),
        "vehicleStatus": {
            "soc": _as_int(_first(params, "soc", "socDsp", "remainPower")),
            "drvMileage": _as_int(
                _first(params, "remainedPowerMile", "totalResidualMileage")
            ),
            "totalMileage": _as_float(params.get("totalOdometer")),
            "totalMeterYesterday": _as_float(params.get("totalMeterYesterday")),
            "igniteCumulativeMileage": _as_float(
                params.get("igniteCumulativeMileage")
            ),
            "engineSts": _as_int(params.get("engineStatus")),
            "connectStatus": 1,
            "powerStatus": _as_int(params.get("powerStatusFeedBack")),
            "epbSts": _as_int(params.get("electronichandbrakeStatus")),
        },
        "hvac": {
            "insideTemp": _as_float(params.get("vehicleTemperature")) * 10
            if _as_float(params.get("vehicleTemperature")) is not None
            else None,
            "insideHumidity": _as_float(params.get("innerHumidity")),
            "remoteTemp": _as_float(params.get("airConditioningSetTemperature")) * 10
            if _as_float(params.get("airConditioningSetTemperature")) is not None
            else None,
            "acStatus": _as_int(params.get("airStatus")),
            "defrostStatus": _as_int(params.get("frontDefrostStatus")),
            "insideAirQualityLevel": _as_int(params.get("airPurifierStatus")),
            "fanLevel": _as_int(params.get("airConditioningHairRatings")),
        },
        "charge": {
            "chargeStatus": _as_int(params.get("ChrgSts")),
            "chargeConStatus": _as_int(
                _first(
                    params,
                    "acChargeGunConnectionState",
                    "dcDhargeGunConnectionState",
                    "dcChargeGunConnectionState",
                )
            ),
            "acChargeCurrent": _as_float(
                _first(params, "BattACChrgInCurr", "battACChrgInCurr")
            ),
            "dcChargeCurrent": _as_float(
                _first(params, "BattDCChrgInCurr", "battDCChrgInCurr")
            ),
            "chargeCurrent": _as_float(
                _first(params, "BattACChrgInCurr", "BattDCChrgInCurr")
            ),
            "remainChargeTime": _as_int(params.get("chargDeltMins")),
            "dcChargeGunConnectStatus": _as_int(
                _first(
                    params,
                    "dcDhargeGunConnectionState",
                    "dcChargeGunConnectionState",
                )
            ),
        },
        "door": {
            "doors": [
                _as_int(params.get("driverDoor")),
                _as_int(params.get("passengerDoor")),
                _as_int(params.get("leftRearDoor")),
                _as_int(params.get("rightRearDoor")),
            ],
            "trunk": _as_int(params.get("trunk")),
            "hood": _as_int(_first(params, "hood", "hoodStatus")),
            "driverLock": _as_int(params.get("driverDoorLock")),
            "passengerLock": _as_int(params.get("passengerDoorLock")),
        },
        "window": {
            "windows": [
                _as_int(params.get("diverWindow")),
                _as_int(params.get("passengerWindow")),
                _as_int(params.get("leftRearWindow")),
                _as_int(params.get("rightRearWindow")),
            ]
        },
        "lamp": {
            "highBeam": _as_int(params.get("highBeam")),
            "lowBeam": _as_int(params.get("lowBeam")),
            "positionLamp": _as_int(params.get("positionLamp")),
            "frontFoglamp": _as_int(params.get("frontFoglamp")),
            "rearFoglamp": _as_int(params.get("rearFoglamp")),
            "leftTurn": _as_int(params.get("turnLndicatorLeft")),
            "rightTurn": _as_int(params.get("turnLndicatorRight")),
        },
        "tire": {
            "leftFront": {
                "pressure": _as_float(params.get("lfTyrePressure")),
                "temperature": _as_float(params.get("leftFrontTireTemperature")),
                "alarm": _as_int(params.get("lfPressureWarning")),
            },
            "rightFront": {
                "pressure": _as_float(params.get("rfTyrePressure")),
                "temperature": _as_float(params.get("rightFrontTireTemperature")),
                "alarm": _as_int(params.get("rfPressureWarning")),
            },
            "leftBack": {
                "pressure": _as_float(params.get("lrTyrePressure")),
                "temperature": _as_float(params.get("leftRearTireTemperature")),
                "alarm": _as_int(params.get("lrPressureWarning")),
            },
            "rightBack": {
                "pressure": _as_float(params.get("rrTyrePressure")),
                "temperature": _as_float(params.get("rightRearTireTemperature")),
                "alarm": _as_int(params.get("rrPressureWarning")),
            },
        },
        "seat": {
            "leftFront": {
                "heatStatus": _seat_heat_level(params.get("driverSeatHeatStatus")),
                "ventStatus": _seat_vent_level(params.get("driverSeatAirStatus")),
            },
            "rightFront": {
                "heatStatus": _seat_heat_level(params.get("passengerSeatHeatStatus")),
                "ventStatus": _seat_vent_level(params.get("passengerSeatAirStatus")),
            },
            "leftBack": {
                "heatStatus": _seat_heat_level(params.get("leftBackSeatHeatStatus")),
                "ventStatus": _seat_vent_level(
                    params.get("leftBackSeatVentilateStatus")
                ),
            },
            "rightBack": {
                "heatStatus": _seat_heat_level(params.get("rightBackSeatHeatStatus")),
                "ventStatus": _seat_vent_level(
                    params.get("rightBackSeatVentilateStatus")
                ),
            },
        },
    }


# Every S05 parameter ``normalize_s05_params`` consumes, including the aliases
# it accepts. Diagnostics and the debug discovery log use this inventory to
# tell apart mapped fields from the ones the vehicle sends but nothing reads
# yet. Keep it in sync when the mapping grows (there is a test that compares it
# against the normalization source).
MAPPED_S05_KEYS: frozenset[str] = frozenset(
    {
        # Report time
        "lastUpdatedTime",
        "lastUpdatedAt",
        "latestDate",
        # Battery and range
        "soc",
        "socDsp",
        "remainPower",
        "remainedPowerMile",
        "totalResidualMileage",
        # Drivetrain and mileage
        "totalOdometer",
        "totalMeterYesterday",
        "igniteCumulativeMileage",
        "engineStatus",
        "powerStatusFeedBack",
        "electronichandbrakeStatus",
        # Climate
        "vehicleTemperature",
        "innerHumidity",
        "airConditioningSetTemperature",
        "airStatus",
        "frontDefrostStatus",
        "airPurifierStatus",
        "airConditioningHairRatings",
        # Charging
        "ChrgSts",
        "acChargeGunConnectionState",
        "dcDhargeGunConnectionState",
        "dcChargeGunConnectionState",
        "BattACChrgInCurr",
        "battACChrgInCurr",
        "BattDCChrgInCurr",
        "battDCChrgInCurr",
        "chargDeltMins",
        # Doors, trunk and locks
        "driverDoor",
        "passengerDoor",
        "leftRearDoor",
        "rightRearDoor",
        "trunk",
        "hood",
        "hoodStatus",
        "driverDoorLock",
        "passengerDoorLock",
        # Windows
        "diverWindow",
        "passengerWindow",
        "leftRearWindow",
        "rightRearWindow",
        # Lamps
        "highBeam",
        "lowBeam",
        "positionLamp",
        "frontFoglamp",
        "rearFoglamp",
        "turnLndicatorLeft",
        "turnLndicatorRight",
        # Tires
        "lfTyrePressure",
        "leftFrontTireTemperature",
        "lfPressureWarning",
        "rfTyrePressure",
        "rightFrontTireTemperature",
        "rfPressureWarning",
        "lrTyrePressure",
        "leftRearTireTemperature",
        "lrPressureWarning",
        "rrTyrePressure",
        "rightRearTireTemperature",
        "rrPressureWarning",
        # Seats
        "driverSeatHeatStatus",
        "driverSeatAirStatus",
        "passengerSeatHeatStatus",
        "passengerSeatAirStatus",
        "leftBackSeatHeatStatus",
        "leftBackSeatVentilateStatus",
        "rightBackSeatHeatStatus",
        "rightBackSeatVentilateStatus",
    }
)


def unmapped_s05_keys(params: dict[str, Any]) -> set[str]:
    """Return the S05 parameter keys that no model field consumes."""
    return set(params) - MAPPED_S05_KEYS
