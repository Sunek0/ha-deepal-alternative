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
import logging
import ssl
import struct
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Optional

from cryptography.hazmat.primitives import padding as symmetric_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

logger = logging.getLogger("deepal_sdk")

S05_SERVICE_CODES = (
    None,
    "car_condition",
    "BDC_Service",
    "BMS_Service",
    "OBC_Service",
    "THU_Service",
)

# SDA/VOT condition service recovered from the 1.12.0 DEX: CarConditionCmdConstant
# (M = Get_CarCondition, P_ConditionQueryType, P_SignalList, SK = CarCondition) and
# RemoteControlConstant.MQTT_CMD_METHOD_CAR_CONDITION.
SDA_CONDITION_SERVICE = "CarCondition"
SDA_CONDITION_COMMAND = "Get_CarCondition"
SDA_SERVICE_CODES = (SDA_CONDITION_SERVICE, SDA_CONDITION_COMMAND)

# The app's condition sections (CarConditionStrategy.buildStrategy), used as the
# SignalList probe for SDA vehicles.
SDA_CONDITION_SECTIONS = (
    "vehicleStatus",
    "location",
    "door",
    "window",
    "tire",
    "seat",
    "lamp",
    "charge",
    "hvac",
    "fuel",
    "welcome",
    "departurePlan",
    "airConditionPlan",
    "warmCoolingBox",
)

MQTT_PROTOCOL_LEVEL = 5
MQTT_DEFAULT_KEEPALIVE = 60
# Seconds to wait for one SDA probe response before publishing the next variant.
MQTT_SDA_PROBE_GRACE = 3.0

# Topic templates from the app's MqttConstantKt (1.12.0 DEX recovery).
LOGIN_PUB_TOPIC_TEMPLATE = "$vdp/%s/client/loginout"
LOGIN_SUB_TOPIC_TEMPLATE = "$vdp/%s/server/loginout"
EVENT_SUB_TOPIC_TEMPLATE = "$vdp/%s/%s/server/event"
EVENT_3D_SUB_TOPIC_TEMPLATE = "$vdp/%s/%s-3D/server/event"
PROPERTIES_SET_TOPIC_TEMPLATE = "$vdp/%s/properties/set/req"

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


def build_publish_packet(
    topic: str, payload: dict[str, Any], *, qos: int = 0, packet_id: int = 1
) -> bytes:
    """Build an MQTT 5.0 PUBLISH packet with a JSON payload.

    ``qos`` 1 adds the packet identifier and lets the broker queue the message
    for an offline subscriber session (the vehicle wake relies on it while the
    car sleeps); every other caller keeps QoS 0.
    """
    body = mqtt_string(topic)
    if qos > 0:
        body += struct.pack("!H", packet_id)
    body += (
        b"\x00"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    )
    return (
        bytes([0x30 | ((qos & 0x03) << 1)])
        + mqtt_remaining_length(len(body))
        + body
    )


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


def topic_with_device(topic: Optional[str], did: Optional[str]) -> Optional[str]:
    """Return the topic with its ``$vdp/<did>`` segment replaced by ``did``."""
    current = topic_device_id(topic)
    if topic and current and did and current != did:
        return topic.replace(current, did)
    return topic


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


def _function_nodes(value: Any) -> list[Mapping[str, Any]]:
    """Collect the ``CarFuncBean``-like nodes of an arbitrary JSON structure."""
    nodes: list[Mapping[str, Any]] = []
    if isinstance(value, Mapping):
        if any(
            key in value
            for key in ("commandCode", "propertyCode", "applicationFuncCode", "deviceId")
        ):
            nodes.append(value)
        for child in value.values():
            nodes.extend(_function_nodes(child))
    elif isinstance(value, (list, tuple)):
        for child in value:
            nodes.extend(_function_nodes(child))
    return nodes


def _is_condition_node(node: Mapping[str, Any]) -> bool:
    text = " ".join(
        str(node.get(key) or "")
        for key in (
            "commandCode",
            "applicationFuncCode",
            "propertyCode",
            "commandName",
            "propertyName",
        )
    ).lower()
    return "carcondition" in text or "get_carcondition" in text


def _unique_strings(values: Iterator[Any]) -> tuple[str, ...]:
    unique: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in unique:
            unique.append(text)
    return tuple(unique)


def sda_condition_plan(config: Any) -> SdaConditionPlan:
    """Derive the SDA condition request plan from the CA function tree.

    The app reads the per-function configuration (``carConfigJson`` inside the
    connection config or the ``appGetCarConfFunc`` response) into
    ``CarFuncBean`` entries and derives the MQTT device id and the condition
    command from it. The tree shape is not fully recovered from the DEX, so the
    walk is defensive: it accepts any nested JSON and only uses the fields it
    recognises.
    """
    nodes: list[Mapping[str, Any]] = []
    for source in [config, *_config_sources(config)]:
        if not isinstance(source, Mapping):
            continue
        for key in ("carConfigJson", "carConfigFuncJson", "carConfigFunc"):
            raw = source.get(key)
            if isinstance(raw, str) and raw.strip():
                try:
                    nodes.extend(_function_nodes(json.loads(raw)))
                except ValueError:
                    continue
    if not nodes:
        nodes = _function_nodes(config)

    condition_nodes = [node for node in nodes if _is_condition_node(node)]
    selected = condition_nodes[0] if condition_nodes else None
    if selected is None:
        device_did = next(
            (str(node.get("deviceId")) for node in nodes if node.get("deviceId")),
            None,
        )
        return SdaConditionPlan(device_did=device_did)

    selected_id = str(selected.get("id") or "")
    subtree = [selected]
    if selected_id:
        frontier = {selected_id}
        while frontier:
            children = [
                node
                for node in nodes
                if str(node.get("parentId") or "") in frontier
            ]
            if not children:
                break
            subtree.extend(children)
            frontier = {str(node.get("id") or "") for node in children}

    def _candidate_codes() -> Iterator[str]:
        for node in subtree:
            code = node.get("propertyCode")
            if not code:
                application = node.get("applicationFuncCode")
                code = str(application).lstrip("#") if application else None
            if code:
                yield code

    return SdaConditionPlan(
        device_did=next(
            (str(node.get("deviceId")) for node in subtree if node.get("deviceId")),
            None,
        ),
        service_code=str(selected.get("serviceCode") or SDA_CONDITION_SERVICE),
        command_code=str(selected.get("commandCode") or SDA_CONDITION_COMMAND),
        property_codes=_unique_strings(_candidate_codes()),
        strategy_codes=_unique_strings(
            node.get("strategyCode") for node in subtree
        ),
        strategy_ids=_unique_strings(node.get("strategyId") for node in subtree),
    )


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
    if "/properties/set/" in lowered:
        if direction == "sub" or lowered.endswith("/res"):
            return "properties_subscribe"
        return "properties_set_publish"
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
    properties_set_publish: Optional[str] = None
    event_subscribe: Optional[str] = None
    subscriptions: tuple[str, ...] = ()
    login_did: Optional[str] = None
    device_did: Optional[str] = None

    @property
    def did(self) -> Optional[str]:
        return self.device_did or self.login_did


@dataclass(frozen=True)
class SdaConditionPlan:
    """SDA condition request plan derived from the CA function tree."""

    device_did: Optional[str] = None
    service_code: str = SDA_CONDITION_SERVICE
    command_code: str = SDA_CONDITION_COMMAND
    property_codes: tuple[str, ...] = ()
    strategy_codes: tuple[str, ...] = ()
    strategy_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Serialize the plan for diagnostics."""
        return {
            "device_did": self.device_did,
            "service_code": self.service_code,
            "command_code": self.command_code,
            "property_codes": list(self.property_codes),
            "strategy_codes": list(self.strategy_codes),
            "strategy_ids": list(self.strategy_ids),
        }


@dataclass(frozen=True)
class MqttExchangeResult:
    """Raw parameters of one MQTT condition exchange plus its provenance.

    ``source`` names the condition service that produced the parameters
    (``sda-mqtt``, ``sda-mqtt-signal-list``, ``legacy-mqtt`` or ``None``), and
    ``variants`` keeps the raw parameters of every request variant that was
    attempted, empty entries included, for diagnostics.
    """

    params: dict[str, Any]
    source: Optional[str] = None
    variants: dict[str, dict[str, Any]] = field(default_factory=dict)
    plan: Optional[SdaConditionPlan] = None


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

    if not selected.get("properties_set_publish"):
        properties_publish = selected.get("properties_publish")
        if properties_publish and "/properties/get/" in properties_publish:
            selected["properties_set_publish"] = properties_publish.replace(
                "/properties/get/", "/properties/set/"
            )

    if did:
        selected.setdefault("login_publish", LOGIN_PUB_TOPIC_TEMPLATE % did)
        selected.setdefault("login_subscribe", LOGIN_SUB_TOPIC_TEMPLATE % did)
        selected.setdefault("event", EVENT_SUB_TOPIC_TEMPLATE % (did, did))
        selected.setdefault("properties_set_publish", PROPERTIES_SET_TOPIC_TEMPLATE % did)
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
        properties_set_publish=selected.get("properties_set_publish"),
        event_subscribe=selected.get("event"),
        subscriptions=tuple(dict.fromkeys(subscriptions)),
        login_did=login_did,
        device_did=device_did,
    )


@dataclass(frozen=True)
class SdaBrokerConfig:
    """SDA broker bootstrap parsed from ``get-mqtt-server-config``.

    ``payload`` keeps the flattened response so the capture can confirm the
    remaining open question (which of the two DEX-confirmed config variants the
    app calls) without another round trip.
    """

    host: Optional[str] = None
    port: Optional[int] = None
    cluster_name: Optional[str] = None
    auth_type: Optional[int] = None
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        """Whether the configuration carries a connectable broker."""
        return bool(self.host and self.port)


def parse_sda_broker_config(raw: Any) -> SdaBrokerConfig:
    """Pull host, port, cluster and ``authType`` out of the config response.

    The gateway wraps the payload in ``data``/``params`` and the SDA response
    repeats the CA shape (``mqttConnectionInfos[0]``), so both levels are
    unwrapped before reading. Field names follow the live E07 response
    (issue #2, 1-oct-2026).
    """
    payload: Any = raw
    if isinstance(payload, Mapping):
        for key in ("data", "params"):
            value = payload.get(key)
            if isinstance(value, Mapping) and value:
                payload = value
                break
    if not isinstance(payload, Mapping):
        return SdaBrokerConfig()
    infos = payload.get("mqttConnectionInfos")
    if isinstance(infos, list) and infos and isinstance(infos[0], Mapping):
        payload = {**payload, **infos[0]}
    port = payload.get("port") or payload.get("mqttPort")
    try:
        port = int(port)
    except (TypeError, ValueError):
        port = None
    auth_type = payload.get("authType")
    try:
        auth_type = int(auth_type)
    except (TypeError, ValueError):
        auth_type = None
    return SdaBrokerConfig(
        host=payload.get("host") or payload.get("mqttHost"),
        port=port,
        cluster_name=payload.get("clusterName"),
        auth_type=auth_type,
        payload=dict(payload),
    )


def device_id_candidates(*sources: Any) -> tuple[str, ...]:
    """Collect unique ``deviceId`` strings from broker configs and function trees.

    The SDA CONNECT identity is the car's device DID, but the sources offer
    several candidates (CA connection config, function tree) and only the
    broker knows which one belongs to the MQTT device: the probe tried them in
    order and the SDK keeps the accepted one (issue #2, 15-oct-2026).
    """
    found: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if str(key).lower() == "deviceid" and isinstance(item, str):
                    if item and item not in found:
                        found.append(item)
                else:
                    walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    for source in sources:
        walk(source)
    return tuple(found)


def sda_session_topics(
    config: Any, device_id: str, car_id: Optional[str] = None
) -> tuple[str, ...]:
    """Return the topics an SDA broker session subscribes to.

    The broker delivers events as ``$vdp/<did>/<car_id>/server/event`` (live
    probe, 15-oct-2026), so the event filter uses the car id when it is known
    instead of the CA fallback that repeats the DID. The account's own publish
    topics are included so the session sees its own login exchange.
    """
    topics = resolve_mqtt_topics(config, device_id)
    did = topics.device_did or device_id
    subscriptions = list(topics.subscriptions)
    if car_id:
        repeated = EVENT_SUB_TOPIC_TEMPLATE % (did, did)
        event = EVENT_SUB_TOPIC_TEMPLATE % (did, car_id)
        subscriptions = [topic for topic in subscriptions if topic != repeated]
        if event not in subscriptions:
            subscriptions.append(event)
    for candidate in (
        topics.login_publish,
        topics.properties_publish,
        topics.properties_set_publish,
    ):
        if candidate and candidate not in subscriptions:
            subscriptions.append(candidate)
    return tuple(dict.fromkeys(subscriptions))


def parse_suback(first: int, body: bytes) -> tuple[Optional[int], list[int]]:
    """Parse a SUBACK into ``(packet_id, reason_codes)``."""
    if first >> 4 != 9 or len(body) < 3:
        return None, []
    return int.from_bytes(body[:2], "big"), list(body[2:])


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


def sda_condition_request_payload(
    device_did: str,
    login_did: str,
    secret_key: str,
    req_id: str,
    basic_info: Optional[Mapping[str, Any]] = None,
    *,
    condition_query_type: int = 0,
    signal_list: Optional[list[str]] = None,
    service_code: str = SDA_CONDITION_SERVICE,
    command_code: str = SDA_CONDITION_COMMAND,
    strategy_code: Optional[str] = None,
    strategy_id: Optional[str] = None,
    rt: Optional[str] = "",
    ms: Optional[int] = None,
    st: Optional[int] = None,
    time_type: Optional[int] = None,
) -> dict[str, Any]:
    """Build the MQTT ``properties/get/req`` message with the SDA condition service.

    The 1.12.0 app builds the SDA request from the VOT service DTO
    (``CarConditionCmdConstant``): ``service_code`` ``CarCondition``,
    ``command_code`` ``Get_CarCondition`` and a ``params`` object with
    ``ConditionQueryType`` plus an optional ``SignalList``. When the function
    tree provides service/command/strategy values, they replace the defaults.
    """
    params: dict[str, Any] = {"ConditionQueryType": condition_query_type}
    if signal_list:
        params["SignalList"] = list(signal_list)
    service: dict[str, Any] = {
        "service_code": service_code,
        "command_code": command_code,
        "params": params,
    }
    if strategy_code:
        service["strategy_code"] = strategy_code
    if strategy_id:
        service["strategy_id"] = strategy_id
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
        "sers": aes_cbc_encrypt([service], secret_key, req_id),
    }
    _set_optional_fields(payload, rt=rt, ms=ms, st=st, time_type=time_type)
    return payload


@dataclass(frozen=True)
class SdaSessionResult:
    """Outcome of one read-only SDA broker session.

    ``attempts`` records one entry per CONNECT identity tried; ``messages``
    keeps the events received during the window (topic, payload, ``qos`` and
    ``dup``) with QoS 1 already acknowledged; ``secret_key`` is the login
    ``secretKey`` when the broker sent it.
    """

    connected: bool = False
    device_id: Optional[str] = None
    connack_reason: Optional[int] = None
    attempts: tuple[dict[str, Any], ...] = ()
    subscriptions: tuple[dict[str, Any], ...] = ()
    messages: tuple[dict[str, Any], ...] = ()
    secret_key: Optional[str] = None


async def sda_broker_session(
    host: str,
    port: int,
    *,
    device_ids: Sequence[str],
    password: str,
    topics: Sequence[str] = (),
    seconds: float = 10.0,
    timeout: float = 20.0,
    keepalive: float = MQTT_DEFAULT_KEEPALIVE,
    ssl_context: Optional[ssl.SSLContext] = None,
    login: bool = False,
) -> SdaSessionResult:
    """Open a read-only session on the SDA broker with the app's identity.

    The app's ``authType 2`` session uses ``clientId`` = device DID,
    ``username`` = the same DID and ``password`` = the ``vot-auth`` token
    (issue #2, 15-oct-2026); the DIDs are tried in order and the accepted one is
    kept in the result. The session subscribes to the event topics and
    acknowledges QoS 1 deliveries (without the ack the broker retransmits the
    whole burst), and never publishes a command: ``login`` only opts into the
    ``client/loginout`` exchange that opens the app's session. The caller owns
    the broker configuration, the token and the device DID resolution.
    """
    candidates = tuple(dict.fromkeys(str(item) for item in device_ids if item))
    if not candidates:
        return SdaSessionResult()

    context = ssl_context or ssl.create_default_context()
    reader: Optional[asyncio.StreamReader] = None
    writer: Optional[asyncio.StreamWriter] = None
    accepted: Optional[str] = None
    reason: Optional[int] = None
    attempts: list[dict[str, Any]] = []

    for device_id in candidates:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    host, port, ssl=context, server_hostname=host
                ),
                timeout,
            )
        except (OSError, asyncio.TimeoutError) as exc:
            attempts.append({"device_id": device_id, "error": type(exc).__name__})
            continue
        try:
            writer.write(
                build_connect_packet(
                    device_id, device_id, password, keepalive=keepalive
                )
            )
            await writer.drain()
            first, body = await asyncio.wait_for(read_packet(reader), timeout)
            _session_present, reason = parse_connack(first, body)
        except (OSError, asyncio.TimeoutError, ValueError) as exc:
            attempts.append({"device_id": device_id, "error": type(exc).__name__})
            await _close_writer(writer)
            reader = writer = None
            continue
        attempts.append({"device_id": device_id, "connack_reason": reason})
        if reason == 0:
            accepted = device_id
            break
        await _close_writer(writer)
        reader = writer = None

    if accepted is None or reader is None or writer is None:
        return SdaSessionResult(
            connected=False,
            connack_reason=reason,
            attempts=tuple(attempts),
        )

    subscriptions: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = []
    secret_key: Optional[str] = None
    try:
        if topics:
            writer.write(build_subscribe_packet(1, list(topics)))
            await writer.drain()
            first, body = await asyncio.wait_for(read_packet(reader), timeout)
            _packet_id, reasons = parse_suback(first, body)
            subscriptions = [
                {"topic": topic, "reason": code}
                for topic, code in zip(topics, reasons)
            ]
        if login:
            writer.write(
                build_publish_packet(
                    LOGIN_PUB_TOPIC_TEMPLATE % accepted,
                    login_request_payload(
                        accepted,
                        new_request_id(accepted),
                        basic_info=basic_identifiers(ruid=accepted),
                    ),
                )
            )
            await writer.drain()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(0.0, seconds)
        while loop.time() < deadline:
            try:
                first, body = await read_packet_with_keepalive(
                    reader,
                    writer,
                    min(5.0, max(0.1, deadline - loop.time())),
                    keepalive=keepalive / 2,
                )
            except asyncio.TimeoutError:
                continue
            except (asyncio.IncompleteReadError, ConnectionError, OSError):
                break
            if first >> 4 != 3:
                continue
            try:
                topic, payload, packet_id = parse_publish(first, body)
            except (ValueError, UnicodeDecodeError):
                continue
            qos = (first >> 1) & 0x03
            if packet_id is not None and qos == 1:
                writer.write(build_puback_packet(packet_id))
                await writer.drain()
            found = secret_from_login_payload(payload)
            if found and not secret_key:
                secret_key = found
            messages.append(
                {
                    "topic": topic,
                    "payload": payload,
                    "qos": qos,
                    "dup": bool(first & 0x08),
                }
            )
    finally:
        await _close_writer(writer)

    return SdaSessionResult(
        connected=True,
        device_id=accepted,
        connack_reason=0,
        attempts=tuple(attempts),
        subscriptions=tuple(subscriptions),
        messages=tuple(messages),
        secret_key=secret_key,
    )


async def _close_writer(writer: asyncio.StreamWriter) -> None:
    """Send DISCONNECT and close a session writer, tolerating dead sockets."""
    try:
        writer.write(build_disconnect_packet())
        await writer.drain()
    except (ConnectionError, OSError, ssl.SSLError):
        pass
    writer.close()
    try:
        await writer.wait_closed()
    except (ConnectionError, OSError, ssl.SSLError):
        pass


# Vehicle wake service (live-verified 2026-09-30): TxWakeup / Cnr_ReWakeup on
# the properties/set/req topic makes the car publish a fresh report in ~20 s.
WAKE_SERVICE_CODE = "TxWakeup"
WAKE_COMMAND_CODE = "Cnr_ReWakeup"


def wake_request_payload(
    device_did: str,
    login_did: str,
    secret_key: str,
    req_id: str,
    basic_info: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Build the MQTT ``properties/set/req`` message that wakes the vehicle."""
    services = [
        {
            "service_code": WAKE_SERVICE_CODE,
            "command_code": WAKE_COMMAND_CODE,
            "service_req_id": req_id,
            "params": {},
        }
    ]
    identifiers = dict(basic_info or {})
    identifiers.setdefault("ruid", login_did)
    return {
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


def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


# The app reports 8191 in chargDeltMins when it has no remaining-time estimate.
CHARGE_TIME_SENTINEL = 8191

# S05 ChrgSts charging states (observed live on the reference car, 2026-10-15,
# moving the gun through every state): 0 not charging, 1 AC gun connected,
# 2 DC gun connected, 3 AC charging, 4 DC charging. Any other value means the
# state is unknown and MUST NOT be translated into one.
CHARGE_STATE_NOT_CHARGING = 0
CHARGE_STATE_AC_CONNECTED = 1
CHARGE_STATE_DC_CONNECTED = 2
CHARGE_STATE_AC_CHARGING = 3
CHARGE_STATE_DC_CHARGING = 4
CHARGE_STATES = (
    CHARGE_STATE_NOT_CHARGING,
    CHARGE_STATE_AC_CONNECTED,
    CHARGE_STATE_DC_CONNECTED,
    CHARGE_STATE_AC_CHARGING,
    CHARGE_STATE_DC_CHARGING,
)
CHARGING_STATES = frozenset({CHARGE_STATE_AC_CHARGING, CHARGE_STATE_DC_CHARGING})
#: States that mean the AC gun is plugged in (charging or only connected).
AC_GUN_STATES = frozenset({CHARGE_STATE_AC_CONNECTED, CHARGE_STATE_AC_CHARGING})
#: States that mean the DC gun is plugged in (charging or only connected).
DC_GUN_STATES = frozenset({CHARGE_STATE_DC_CONNECTED, CHARGE_STATE_DC_CHARGING})

# No S05 charging current can approach this: the reference car sent 2538 in
# BattDCChrgInCurr while parked after a DC session whose history showed real
# amperes (0 -> 60 -> 0 -> 2538), so a reading outside 0..MAX_CHARGE_CURRENT_A
# is a raw glitch and is dropped instead of published as amperes. The car's DC
# peak is about 480 A, so the bound leaves margin and still rejects 2538.
MAX_CHARGE_CURRENT_A = 600.0

# S05 charge-connection aliases: the app's AC gun name plus the DC gun names the
# mapping still accepts (the app writes "dcDhargeGun..." with the typo).
S05_CHARGE_GUN_KEYS = (
    "acChargeGunConnectionState",
    "dcDhargeGunConnectionState",
    "dcChargeGunConnectionState",
)
# S05 DC-gun aliases (the AC gun key is not one of them).
S05_DC_GUN_KEYS = (
    "dcDhargeGunConnectionState",
    "dcChargeGunConnectionState",
)


def _as_charge_time(value: Any) -> Optional[int]:
    """Return remaining charge minutes, mapping the app sentinel to unknown."""
    minutes = _as_int(value)
    if minutes == CHARGE_TIME_SENTINEL:
        return None
    return minutes


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> Optional[bool]:
    """Return a boolean for zero/non-zero values, ``None`` when absent."""
    number = _as_int(value)
    return None if number is None else number != 0


def _humidity_percent(value: Any) -> Optional[float]:
    """Return the cabin humidity as a percentage.

    The S05 reports ``innerHumidity`` either as a percentage (``61``) or as
    tenths of a percent (``453``) depending on the moment, so a value above 100
    is divided by ten. Values outside 0 to 100 after that are unknown.
    """
    humidity = _as_float(value)
    if humidity is None:
        return None
    if humidity > 100:
        humidity /= 10
    return humidity if 0 <= humidity <= 100 else None


def _first(params: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = params.get(key)
        if value is not None:
            return value
    return None


def _seat_level(value: Any) -> Optional[int]:
    """Return a seat heating or ventilation level, or None when it is unknown.

    The vehicle reports both functions 1:1 with the app's 0-3 levels, and it
    sends 6 while the seat module is asleep. The sleep sentinel and any other
    out-of-range value mean the level is unknown, not a level, so callers can
    keep the last valid value instead of exposing a made-up one.
    """
    parsed = _as_int(value)
    if parsed is None or not 0 <= parsed <= 3:
        return None
    return parsed


def charge_state(value: Any) -> Optional[int]:
    """Return the S05 charging-state code, or None when the value is not one."""
    parsed = _as_int(value)
    return parsed if parsed in CHARGE_STATES else None


def charge_is_active(value: Any) -> Optional[bool]:
    """Return whether a charging state means the car is charging (None = unknown)."""
    state = charge_state(value)
    return None if state is None else state in CHARGING_STATES


def clean_charge_current(value: Any, field: str = "chargeCurrent") -> Optional[float]:
    """Return a believable charging current in amperes, or None.

    A reading outside ``0..MAX_CHARGE_CURRENT_A`` is a raw glitch (the live car
    published 2538 while parked), so it is logged at debug level and dropped
    instead of being exposed as amperes.
    """
    current = _as_float(value)
    if current is None:
        return None
    if not 0 <= current <= MAX_CHARGE_CURRENT_A:
        logger.debug(
            "S05 %s=%r dropped: outside 0-%g A",
            field,
            value,
            MAX_CHARGE_CURRENT_A,
        )
        return None
    return current


def charge_currents(
    ac_value: Any, dc_value: Any, state_value: Any
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Return the (AC, DC, active) charging currents of one S05 report.

    The car keeps reporting the current of the charger it is not using and the
    flat mapping used to pick the AC field first, so a present AC ``0`` hid the
    real DC current. Both fields are resolved against ``ChrgSts``: the field of
    the active mode is the active current, the other one is zeroed when the car
    reported a value, and connected-without-charging (``1``, ``2``) or unplugged
    (``0``) report ``0`` instead of a stale value or the post-session sentinel.
    An unrecognized state keeps the sanitized readings, preferring a non-zero
    one.
    """
    state = charge_state(state_value)
    ac_reported = _as_float(ac_value) is not None
    dc_reported = _as_float(dc_value) is not None
    ac = clean_charge_current(ac_value, "BattACChrgInCurr")
    dc = clean_charge_current(dc_value, "BattDCChrgInCurr")

    if state == CHARGE_STATE_DC_CHARGING:
        return (0.0 if ac_reported else None), dc, dc
    if state == CHARGE_STATE_AC_CHARGING:
        return ac, (0.0 if dc_reported else None), ac
    if state is not None:
        return (
            0.0 if ac_reported else None,
            0.0 if dc_reported else None,
            0.0 if (ac_reported or dc_reported) else None,
        )

    active = ac if ac not in (None, 0) else dc
    if active is None and ac is not None:
        active = 0.0
    return ac, dc, active


def _gun_code_connected(value: Any) -> Optional[bool]:
    """Return whether a raw gun connection code means connected (None = absent).

    The S05 gun fields use ``0`` and ``1`` for "not connected" and higher values
    for a plugged gun; an absent value stays unknown, so callers can tell it
    apart from a reported "not connected".
    """
    code = _as_int(value)
    if code is None:
        return None
    return code not in (0, 1)


def charge_gun_flags(
    state_value: Any,
    *,
    ac_gun_value: Any = None,
    dc_gun_value: Any = None,
) -> tuple[Optional[bool], Optional[bool], Optional[bool]]:
    """Return the (charger plugged, AC gun, DC gun) flags of one report.

    The S05 charging state identifies the gun (`1`-`4` plugged, `2`/`4` DC,
    `1`/`3` AC), so a recognized state wins and a stale raw gun field cannot
    keep the flags on after unplugging. Snapshots without a recognized state
    fall back to the raw gun fields, which the SDA and REST vehicles use, and
    the charger is plugged when either reported gun is connected.
    """
    state = charge_state(state_value)
    if state is not None:
        return (
            state != CHARGE_STATE_NOT_CHARGING,
            state in AC_GUN_STATES,
            state in DC_GUN_STATES,
        )

    ac_gun = _gun_code_connected(ac_gun_value)
    dc_gun = _gun_code_connected(dc_gun_value)
    if ac_gun or dc_gun:
        plugged: Optional[bool] = True
    elif ac_gun is False or dc_gun is False:
        plugged = False
    else:
        plugged = None
    return plugged, ac_gun, dc_gun


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
    charge_status = _as_int(params.get("ChrgSts"))
    ac_current, dc_current, active_current = charge_currents(
        _first(params, "BattACChrgInCurr", "battACChrgInCurr"),
        _first(params, "BattDCChrgInCurr", "battDCChrgInCurr"),
        charge_status,
    )
    charge_con_status, ac_gun, dc_gun = charge_gun_flags(
        charge_status,
        ac_gun_value=params.get("acChargeGunConnectionState"),
        dc_gun_value=_first(params, *S05_DC_GUN_KEYS),
    )
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
            "insideHumidity": _humidity_percent(params.get("innerHumidity")),
            "remoteTemp": _as_float(params.get("airConditioningSetTemperature")) * 10
            if _as_float(params.get("airConditioningSetTemperature")) is not None
            else None,
            "acStatus": _as_int(params.get("airStatus")),
            "defrostStatus": _as_int(params.get("frontDefrostStatus")),
            "insideAirQualityLevel": _as_int(params.get("airPurifierStatus")),
            "fanLevel": _as_int(params.get("airConditioningHairRatings")),
        },
        "charge": {
            "chargeStatus": charge_status,
            "chargeConStatus": charge_con_status,
            "acChargeGunConnectStatus": ac_gun,
            "dcChargeGunConnectStatus": dc_gun,
            "acChargeCurrent": ac_current,
            "dcChargeCurrent": dc_current,
            "chargeCurrent": active_current,
            "remainChargeTime": _as_charge_time(params.get("chargDeltMins")),
        },
        "fuel": {
            "leftPercent": _as_int(params.get("remainingFuel")),
            "remainingRange": _as_int(params.get("remainedOilMile")),
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
        "warningLights": {
            "battery12v": _as_bool(params.get("batt12VLightStatus")),
            "tpms": _as_bool(params.get("tpmsLightStatus")),
            "abs": _as_bool(params.get("absLightStatus")),
            "brakeFluid": _as_bool(params.get("brakeFluidLightStatus")),
            "brake": _as_bool(params.get("brakeLightStatus")),
            "eps": _as_bool(params.get("epsLightStatus")),
            "powerLimit": _as_bool(params.get("powerLimitLightStatus")),
            "powerSystem": _as_bool(params.get("powerSystemLightStatus")),
            "tractionBatteryLow": _as_bool(params.get("bcuBattSocLightStatus")),
        },
        "windowOpenings": {
            "frontLeft": _as_int(params.get("leftAnteriorWindowDegree")),
            "frontRight": _as_int(params.get("rightAnteriorWindowDegree")),
            "rearLeft": _as_int(params.get("leftRearWindowDegree")),
            "rearRight": _as_int(params.get("rightRearWindowDegree")),
        },
        "keyBatteryLow": _as_bool(params.get("keyLowPower")),
        "airRecirculation": _as_bool(params.get("airRecycleStatus")),
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
                "heatStatus": _seat_level(params.get("driverSeatHeatStatus")),
                "ventStatus": _seat_level(params.get("driverSeatAirStatus")),
            },
            "rightFront": {
                "heatStatus": _seat_level(params.get("passengerSeatHeatStatus")),
                "ventStatus": _seat_level(params.get("passengerSeatAirStatus")),
            },
            "leftBack": {
                "heatStatus": _seat_level(params.get("leftBackSeatHeatStatus")),
                "ventStatus": _seat_level(
                    params.get("leftBackSeatVentilateStatus")
                ),
            },
            "rightBack": {
                "heatStatus": _seat_level(params.get("rightBackSeatHeatStatus")),
                "ventStatus": _seat_level(
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
        # Fuel (PHEV / range extender)
        "remainingFuel",
        "remainedOilMile",
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
        # Dashboard warning lights and key fob battery
        "batt12VLightStatus",
        "tpmsLightStatus",
        "absLightStatus",
        "brakeFluidLightStatus",
        "brakeLightStatus",
        "epsLightStatus",
        "powerLimitLightStatus",
        "powerSystemLightStatus",
        "bcuBattSocLightStatus",
        "keyLowPower",
        # Air recirculation
        "airRecycleStatus",
        # Window opening degrees
        "leftAnteriorWindowDegree",
        "rightAnteriorWindowDegree",
        "leftRearWindowDegree",
        "rightRearWindowDegree",
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


def _sda_value(params: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = params.get(key)
        if value is not None:
            return value
    return None


def _sda_status(value: Any, closed_value: int) -> int:
    """Map an SDA status signal to 1 (open/unlocked) or 0 (closed/locked)."""
    parsed = _as_int(value)
    if parsed is None:
        return 0
    return 0 if parsed == closed_value else 1


def _sda_lock(value: Any) -> Optional[int]:
    """Map an SDA lock signal to the REST convention (0 = locked).

    The E07 reports ``2`` while the car is locked (same convention as the
    ``2`` closed state), so only that value means locked; ``1`` is unlocked and
    missing values stay unknown.
    """
    parsed = _as_int(value)
    if parsed is None:
        return None
    return 0 if parsed == 2 else 1


def _sda_tenths(value: Any) -> Optional[float]:
    parsed = _as_float(value)
    return parsed * 10 if parsed is not None else None


def normalize_sda_params(params: Mapping[str, Any]) -> dict[str, Any]:
    """Map the flat SDA condition signals into the shared nested condition shape.

    The SDA REST condition (``getCarConditionByCarId``) returns a flat object
    with SDA-specific names (for example ``BcuSocDisp``, ``VcuResiMilg``,
    ``CdcTotMilg``, ``DrvrDoorSts``). The mapping follows the values seen in
    the official app trace for an E07: status ``2`` means closed, lock ``1``
    means locked, window positions are percentages with ``0`` closed.
    Unmapped keys stay in the raw payload for diagnostics.
    """
    soc = _as_int(_sda_value(params, "VIUSocDisp"))
    if soc is None:
        raw_soc = _as_float(_sda_value(params, "BcuSocDisp"))
        soc = round(raw_soc) if raw_soc is not None else None

    ac_connected = _as_int(_sda_value(params, "AcChrgCnctrSts"))
    dc_connected = _as_int(_sda_value(params, "DcChrgCnctrSts"))
    connected = (
        1
        if (ac_connected not in (None, 0) or dc_connected not in (None, 0))
        else 0
    )
    # The SDA AC connector status follows its own rule (0 = not connected,
    # anything else = connected), the same one ``connected`` uses above.
    ac_gun_connected = (
        None if ac_connected is None else ac_connected != 0
    )

    return {
        "vehicleStatus": {
            "soc": soc,
            "drvMileage": _as_int(_sda_value(params, "VcuResiMilg")),
            "totalMileage": _as_float(_sda_value(params, "CdcTotMilg")),
            "speed": _as_float(_sda_value(params, "EspVehSpd")),
            "engineSts": _as_int(_sda_value(params, "VcuRdySts")),
            "powerStatus": _as_int(_sda_value(params, "BcmPwrStsFb")),
            "steeringWheelHeater": _as_int(_sda_value(params, "SteeringHeat")),
        },
        "charge": {
            "chargeStatus": _as_int(_sda_value(params, "BcuChrgSts")),
            "chargeConStatus": connected,
            "acChargeGunConnectStatus": ac_gun_connected,
            "dcChargeGunConnectStatus": dc_connected,
            "chargeCurrent": clean_charge_current(
                _sda_value(params, "BcuBattI"), "BcuBattI"
            ),
            "acChargeCurrent": clean_charge_current(
                _sda_value(params, "ObcChrgInpAcIL1"), "ObcChrgInpAcIL1"
            ),
            "dcChargeCurrent": clean_charge_current(
                _sda_value(params, "ObcChrgDcI"), "ObcChrgDcI"
            ),
            "remainChargeTime": _as_charge_time(
                _sda_value(params, "BcuChrgTiDisp")
            ),
            "maxSocPercent": _as_int(_sda_value(params, "TboxSocChrgTarSet")),
        },
        "door": {
            "doors": [
                _sda_status(_sda_value(params, "DrvrDoorSts"), 2),
                _sda_status(_sda_value(params, "PassDoorSts"), 2),
                _sda_status(_sda_value(params, "LeReDoorSts"), 2),
                _sda_status(_sda_value(params, "RiReDoorSts"), 2),
            ],
            "trunk": _sda_status(_sda_value(params, "ObjStTypePLGDoorSt"), 2),
            "hood": _sda_status(_sda_value(params, "FrtGateSts"), 2),
            "driverLock": _sda_lock(_sda_value(params, "DrvrDoorLockLogicSts")),
            "passengerLock": _sda_lock(
                _sda_value(params, "PassDoorLockLogicSts")
            ),
        },
        "window": {
            "windows": [
                _as_int(_sda_value(params, "DrvrWinPos")),
                _as_int(_sda_value(params, "PassWinPos")),
                _as_int(_sda_value(params, "LeReWinPos")),
                _as_int(_sda_value(params, "RiReWinPos")),
            ],
        },
        "hvac": {
            "insideTemp": _sda_tenths(_sda_value(params, "ITMSAcIntT")),
            "remoteTemp": _sda_tenths(_sda_value(params, "ITMSDrvrAutT")),
            "acStatus": _as_int(_sda_value(params, "ITMSACOnOff")),
            "insidePm25": _as_float(_sda_value(params, "ITMSPm25InCarDens")),
            "insideAirQualityLevel": _as_int(
                _sda_value(params, "ITMSAirQlyInCarLvl")
            ),
            "defrostStatus": _as_int(_sda_value(params, "ITMSFrntDefroster")),
        },
        "seat": {
            "leftFront": {
                "heatStatus": _as_int(_sda_value(params, "DrHeatGear")),
                "ventStatus": _as_int(_sda_value(params, "DrVentGear")),
            },
            "rightFront": {
                "heatStatus": _as_int(_sda_value(params, "PsgHeatGear")),
                "ventStatus": _as_int(_sda_value(params, "PsgVentGear")),
            },
            "leftBack": {
                "heatStatus": _as_int(_sda_value(params, "RearLeHeatGear")),
                "ventStatus": _as_int(_sda_value(params, "RearLeVentGear")),
            },
            "rightBack": {
                "heatStatus": _as_int(_sda_value(params, "RearRiHeatGear")),
                "ventStatus": _as_int(_sda_value(params, "RearRiVentGear")),
            },
        },
        "lamp": {
            "highBeam": max(
                _as_int(_sda_value(params, "HCM_LeHiBeSt")) or 0,
                _as_int(_sda_value(params, "HCM_RiHiBeSt")) or 0,
            ),
            "lowBeam": max(
                _as_int(_sda_value(params, "HCM_LeLoBeSt")) or 0,
                _as_int(_sda_value(params, "HCM_RiLoBeSt")) or 0,
            ),
        },
    }
