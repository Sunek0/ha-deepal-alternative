"""Minimal MQTT transport and S05 payload helpers for the international platform.

This module implements the subset of MQTT and the S05 parameter mapping that the
official app uses for MQTT-backed vehicles: CONNECT/SUBSCRIBE/PUBLISH packets over
TLS and the AES-CBC (IV ``MD5(reqId)``) + base64 + gzip encryption of service
payloads. No external MQTT library is required.
"""

from __future__ import annotations

import asyncio
import base64
import gzip
import hashlib
import json
import struct
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


def build_connect_packet(client_id: str, username: str, password: str) -> bytes:
    """Build an MQTT CONNECT packet with username/password credentials."""
    payload = mqtt_string(client_id) + mqtt_string(username) + mqtt_string(password)
    variable = mqtt_string("MQTT") + bytes([4, 0xC2]) + struct.pack("!H", 60)
    body = variable + payload
    return bytes([0x10]) + mqtt_remaining_length(len(body)) + body


def build_subscribe_packet(packet_id: int, topics: list[str]) -> bytes:
    """Build an MQTT SUBSCRIBE packet with QoS 1 subscriptions."""
    payload = b"".join(mqtt_string(topic) + b"\x01" for topic in topics)
    body = struct.pack("!H", packet_id) + payload
    return bytes([0x82]) + mqtt_remaining_length(len(body)) + body


def build_publish_packet(topic: str, payload: dict[str, Any]) -> bytes:
    """Build a QoS 0 MQTT PUBLISH packet with a JSON payload."""
    body = mqtt_string(topic) + json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    ).encode()
    return bytes([0x30]) + mqtt_remaining_length(len(body)) + body


def build_puback_packet(packet_id: int) -> bytes:
    """Build the PUBACK used to acknowledge a QoS 1 message."""
    return bytes([0x40, 0x02]) + struct.pack("!H", packet_id)


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


def parse_publish(first: int, body: bytes) -> tuple[str, dict[str, Any], Optional[int]]:
    """Parse a PUBLISH packet body into ``(topic, payload, packet_id)``."""
    pos = 0
    topic_len = struct.unpack("!H", body[pos : pos + 2])[0]
    pos += 2
    topic = body[pos : pos + topic_len].decode(errors="replace")
    pos += topic_len
    packet_id: Optional[int] = None
    if (first >> 1) & 0x03:
        packet_id = struct.unpack("!H", body[pos : pos + 2])[0]
        pos += 2
    payload = json.loads(body[pos:].decode())
    return topic, payload, packet_id


def topic_device_id(topic: str) -> Optional[str]:
    """Return the device id of a ``$vdp/<did>/...`` topic."""
    parts = topic.split("/")
    if len(parts) > 2 and parts[0] == "$vdp":
        return parts[1]
    return None


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


def login_request_payload(login_did: str, req_id: str) -> dict[str, Any]:
    """Build the MQTT ``loginout`` request that returns the ``secretKey``."""
    return {
        "did": login_did,
        "r": req_id,
        "v": "v1.0.0",
        "mt": "loginout",
        "z": "unzip",
        "a": 0,
        "e": 0,
        "tf": 0,
        "dt": iso_now(),
        "pl": True,
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
    }


def condition_request_payload(
    device_did: str, login_did: str, secret_key: str, req_id: str
) -> dict[str, Any]:
    """Build the MQTT ``properties/get/req`` message that returns the condition."""
    services = [{"service_code": "car_condition", "params": {"fetchPropertyType": 0}}]
    return {
        "did": device_did,
        "r": req_id,
        "v": "v1.0.0",
        "mt": "properties",
        "e": 1,
        "z": "gzip",
        "tf": 0,
        "dt": iso_now(),
        "b": {"ruid": login_did},
        "sers": aes_cbc_encrypt(services, secret_key, req_id),
        "rt": "",
    }


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
    latest = _first(params, "latestDate", "lastUpdatedAt")
    return {
        "lastUpdatedAt": _to_millis(latest),
        "vehicleStatus": {
            "soc": _as_int(_first(params, "soc", "socDsp", "remainPower")),
            "drvMileage": _as_int(
                _first(params, "remainedPowerMile", "totalResidualMileage")
            ),
            "totalMileage": _as_float(params.get("totalOdometer")),
            "steeringWheelHeater": _as_int(params.get("steeringWheelHeating")),
            "steeringWheelHeaterLevel": _as_int(params.get("steeringWheelHeating")),
        },
        "hvac": {
            "remoteTemp": _as_float(params.get("airConditioningSetTemperature")) * 10
            if _as_float(params.get("airConditioningSetTemperature")) is not None
            else None,
            "acStatus": _as_int(params.get("airStatus")),
        },
        "charge": {
            "chargeStatus": _as_int(params.get("ChrgSts")),
            "chargeConStatus": _as_int(
                _first(
                    params, "acChargeGunConnectionState", "dcChargeGunConnectionState"
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
        "tire": {
            "leftFront": {
                "pressure": _as_float(params.get("lfTyrePressure")),
                "alarm": _as_int(params.get("lfPressureWarning")),
            },
            "rightFront": {
                "pressure": _as_float(params.get("rfTyrePressure")),
                "alarm": _as_int(params.get("rfPressureWarning")),
            },
            "leftBack": {
                "pressure": _as_float(params.get("lrTyrePressure")),
                "alarm": _as_int(params.get("lrPressureWarning")),
            },
            "rightBack": {
                "pressure": _as_float(params.get("rrTyrePressure")),
                "alarm": _as_int(params.get("rrPressureWarning")),
            },
        },
        "seat": {
            "rightFront": {
                "heatStatus": _as_int(params.get("driverSeatHeatStatus")),
                "ventStatus": _as_int(params.get("driverSeatAirStatus")),
            },
            "leftFront": {
                "heatStatus": _as_int(params.get("passengerSeatHeatStatus")),
                "ventStatus": _as_int(params.get("passengerSeatAirStatus")),
            },
        },
    }
