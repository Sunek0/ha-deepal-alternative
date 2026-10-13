"""mitmproxy addon: capture and decode MQTT-over-TLS for the Deepal SDA broker.

Run it with the launcher (see README.md) or directly:

    mitmdump --mode wireguard -s mqtt_dump.py --set mqtt_dump_dir=capture
    mitmdump --mode regular -p 8080 -s mqtt_dump.py --set mqtt_dump_dir=capture

It writes, inside the dump directory:

    mqtt-transcript.log   decoded MQTT frames, safe to share
    http-transcript.log   the allowlisted app HTTP calls, safe to share
    mqtt-raw.log          raw hex per TCP message, LOCAL ONLY and off by default

Privacy contract:

* The shareable logs never contain credentials, tokens, identifiers, the number
  plate or the vehicle location. Location and plate keys are masked outright;
  identifiers (DIDs, user and car ids) keep a stable 8 hex character tag so the
  maintainer can still correlate messages without learning the value.
* The MQTT ``secretKey`` (the login response that unlocks the encrypted ``sers``
  blobs) is kept **in memory only** and never written to any log. When it is
  present, ``sers`` is decrypted locally and the transcript carries the decoded
  service list (``service_code``, ``command_code``, ``params``) instead of the
  ciphertext. That is the whole point of the capture: the remote-control command
  codes travel inside ``sers``, so a ciphertext-only log cannot answer which
  command the app sends.
* ``mqtt-raw.log`` is opt-in (``--set mqtt_dump_raw=true``), omits CONNECT and
  login responses, and is meant to stay on the tester's machine.

The addon is self-contained: the tester only needs this file and mitmproxy
(which already depends on ``cryptography``).
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlsplit

from mitmproxy import ctx, http, tcp

TARGET_HOSTS = (
    "prod-appmq.sda.changanauto.sg",
    "ca-rtm.iov.changanauto.sg",
)

#: App HTTP calls whose bodies answer the SDA command questions. Everything else
#: (banking, mail, any other app on the phone) is ignored on purpose.
HTTP_HOST_SUFFIXES = (
    "changanauto.sg",
    "changanauto.com.de",
    "changanauto.link",
    "iov.changanauto.sg",
)
HTTP_PATH_TOKENS = (
    "/car-ctrl/get-mqtt-server-config",
    "/car-ctrl/getCarConditionByCarId",
    "/car-ctrl/rapid-func",
    "/car-ctrl/get-function-config",
    "/appGetCarConfFunc",
    "/vot-auth/api/token/getAuthTokenByUserId",
    "/security-code/get-status",
    "/security-code/check-code",
)
HTTP_BODY_LIMIT = 4000
SAFE_HEADER_KEYS = (
    "selectcountry",
    "appversion",
    "apptype",
    "language",
    "x-os-version",
    "x-tsp-timestamp",
)

TLS_HANDSHAKE = bytes((0x16, 0x03))

PACKET_TYPES = {
    1: "CONNECT",
    2: "CONNACK",
    3: "PUBLISH",
    4: "PUBACK",
    5: "PUBREC",
    6: "PUBREL",
    7: "PUBCOMP",
    8: "SUBSCRIBE",
    9: "SUBACK",
    10: "UNSUBSCRIBE",
    11: "UNSUBACK",
    12: "PINGREQ",
    13: "PINGRESP",
    14: "DISCONNECT",
    15: "AUTH",
}

_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}(?:\.[A-Za-z0-9_\-]+)?")
_LONG_TOKEN_RE = re.compile(r"[A-Za-z0-9+/=_\-]{40,}")

_FULL_MASK_KEYS = {
    "accesstoken",
    "authorization",
    "authtoken",
    "cactoken",
    "checkcode",
    "controlpin",
    "cookie",
    "email",
    "gps",
    "lat",
    "latitude",
    "latitud",
    "licenseplate",
    "lng",
    "lon",
    "longitude",
    "mobile",
    "password",
    "passwd",
    "pin",
    "plate",
    "platenumber",
    "position",
    "privatekey",
    "rctoken",
    "refreshtoken",
    "safecode",
    "secret",
    "secretkey",
    "seriralno",
    "serialno",
    "sign",
    "token",
    "vin",
    "vincode",
    "vehiclevin",
}
# NOTE: the gateway ``code``/``msg`` status fields stay readable (they are not
# secrets) while every security-code spelling (``safeCode``, ``checkCode``,
# ``pin``) is masked outright.
_TAGGED_MASK_KEYS = {
    "carid",
    "cid",
    "devicedid",
    "deviceid",
    "did",
    "ruid",
    "sc",
    "sessionid",
    "uid",
    "vehicleid",
}
_FULL_MASK = "<masked>"
_TAG_LENGTH = 8


def _stable_tag(value: Any) -> str:
    """Return a short stable tag so the same id stays comparable when masked."""
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()
    return digest[:_TAG_LENGTH]


def _norm(key: Any) -> str:
    return str(key).lower().replace("_", "").replace("-", "")


def mask_text(value: str) -> str:
    value = _JWT_RE.sub("<jwt>", value)
    return _LONG_TOKEN_RE.sub("<token>", value)


def _mask_value(key: Any, item: Any) -> Any:
    """Return the masked stand-in for one value, or ``None`` when not sensitive."""
    norm = _norm(key)
    if norm in _FULL_MASK_KEYS:
        return _FULL_MASK
    if norm in _TAGGED_MASK_KEYS and isinstance(item, (str, int)):
        return f"<{norm}:{_stable_tag(item)}>"
    return None


def mask_identifier(value: str) -> str:
    return f"<id:{_stable_tag(value)}>" if value else _FULL_MASK


def mask_topic(topic: str) -> str:
    """Mask the ``$vdp/<did>`` device segment of an MQTT topic."""
    if not topic.startswith("$vdp/"):
        return topic
    parts = topic.split("/", 2)
    if len(parts) < 3:
        return topic
    return f"$vdp/{mask_identifier(parts[1])}/{parts[2]}"


def mask_json(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            masked = _mask_value(key, item)
            if masked is not None:
                out[key] = masked
            else:
                out[key] = mask_json(item)
        return out
    if isinstance(value, list):
        return [mask_json(item) for item in value]
    if isinstance(value, str):
        return mask_text(value)
    return value


def mask_url_path(path: str) -> str:
    """Mask the sensitive query values of a request path."""
    parts = urlsplit(path)
    if not parts.query:
        return path
    query = "&".join(
        f"{key}={_mask_value(key, value) or value}"
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
    )
    return f"{parts.path}?{query}"


def safe_headers(headers: Any) -> Dict[str, str]:
    """Keep only the non-sensitive headers useful for debugging the region."""
    lookup = {str(key).lower(): str(value) for key, value in dict(headers).items()}
    return {key: lookup[key] for key in SAFE_HEADER_KEYS if key in lookup}


def absorb_secret(payload: Any) -> Optional[str]:
    """Return the MQTT ``secretKey`` carried by a login response, if present.

    Mirrors ``deepal_sdk/deepal/mqtt.py::secret_from_login_payload``.
    """
    if not isinstance(payload, dict):
        return None
    candidates: List[Any] = []
    for item in payload.get("rs") or []:
        if isinstance(item, dict):
            for key in ("params", "data"):
                value = item.get(key)
                if isinstance(value, dict):
                    candidates.append(value.get("secretKey"))
    for key in ("secretKey", "secret_key"):
        candidates.append(payload.get(key))
    data = payload.get("data")
    if isinstance(data, dict):
        candidates.append(data.get("secretKey"))
    for candidate in candidates:
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


def _b64decode(value: str) -> bytes:
    return base64.b64decode(value + "=" * ((4 - len(value) % 4) % 4))


def decrypt_sers(
    encrypted: str, secret_key: Optional[str], req_id: Any
) -> Tuple[Optional[List[Any]], str]:
    """Decrypt a ``sers`` service payload: AES-CBC + base64 + gzip + JSON list.

    Vendored from ``deepal_sdk/deepal/mqtt.py::aes_cbc_decrypt`` (AES-CBC with
    the MQTT ``secretKey`` as key and ``md5(req_id)`` as IV) so the kit stays a
    single file. The matching test keeps both implementations in step.
    """
    if not secret_key:
        return None, "no secretKey captured yet"
    if not isinstance(req_id, str) or not req_id:
        return None, "no request id in the envelope"
    try:
        from cryptography.hazmat.primitives import padding as symmetric_padding
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        decryptor = Cipher(
            algorithms.AES(secret_key.encode()),
            modes.CBC(hashlib.md5(req_id.encode()).digest()),
        ).decryptor()
        padded = decryptor.update(_b64decode(encrypted)) + decryptor.finalize()
        unpadder = symmetric_padding.PKCS7(128).unpadder()
        plaintext = unpadder.update(padded) + unpadder.finalize()
        compressed = _b64decode(plaintext.decode().strip())
        decoded = json.loads(gzip.decompress(compressed).decode())
    except Exception as exc:  # noqa: BLE001 - a capture tool never aborts the proxy
        return None, f"{type(exc).__name__}: {exc}"
    if not isinstance(decoded, list):
        return None, "decrypted payload is not a service list"
    return decoded, ""


def prepare_payload(
    parsed: Any,
    secret_key: Optional[str] = None,
    secret_sink: Optional[Callable[[str], None]] = None,
) -> Any:
    """Return a transcript-ready copy of an MQTT JSON payload.

    The ``sers`` ciphertext is replaced by the locally decrypted service list so
    the shareable log answers which command the app sent.
    """
    if not isinstance(parsed, dict):
        return mask_json(parsed)

    found = absorb_secret(parsed)
    if found and secret_sink is not None:
        secret_sink(found)

    out = dict(parsed)
    sers = out.pop("sers", None)
    if isinstance(sers, str):
        out["sers_ciphertext_chars"] = len(sers)
        decoded, error = decrypt_sers(sers, secret_key, out.get("r"))
        if decoded is not None:
            out["sers_decoded"] = decoded
        else:
            out["sers_decoded"] = f"<unavailable: {error}>"
    return mask_json(out)


def read_varint(data: bytes, pos: int) -> Tuple[Optional[int], int]:
    value = 0
    multiplier = 1
    for _ in range(4):
        if pos >= len(data):
            return None, pos
        byte = data[pos]
        pos += 1
        value += (byte & 0x7F) * multiplier
        if not byte & 0x80:
            return value, pos
        multiplier *= 128
    return None, pos


def split_packets(buffer: bytearray) -> List[bytes]:
    """Pop complete MQTT packets from the stream buffer."""
    packets: List[bytes] = []
    while len(buffer) >= 2:
        remaining, pos = read_varint(bytes(buffer), 1)
        if remaining is None:
            break
        total = pos + remaining
        if len(buffer) < total:
            break
        packets.append(bytes(buffer[:total]))
        del buffer[:total]
    return packets


def _read_string(data: bytes, pos: int) -> Tuple[Optional[str], int]:
    if pos + 2 > len(data):
        return None, pos
    length = int.from_bytes(data[pos : pos + 2], "big")
    pos += 2
    if pos + length > len(data):
        return None, pos
    return data[pos : pos + length].decode("utf-8", "replace"), pos + length


def _decode_connect(body: bytes) -> str:
    protocol, pos = _read_string(body, 0)
    if pos >= len(body):
        return "CONNECT (truncated)"
    level = body[pos]
    pos += 1
    flags = body[pos] if pos < len(body) else 0
    pos += 1
    keepalive = int.from_bytes(body[pos : pos + 2], "big") if pos + 2 <= len(body) else 0
    pos += 2
    if level == 5:
        props_len, pos = read_varint(body, pos)
        if props_len:
            pos += props_len
    client_id, pos = _read_string(body, pos)
    strings: List[str] = []
    while pos < len(body):
        value, pos = _read_string(body, pos)
        if value is None:
            break
        strings.append(value)
    username = mask_identifier(strings[0]) if strings else None
    password = strings[1] if len(strings) > 1 else None
    return "CONNECT " + json.dumps(
        {
            "protocol": protocol,
            "level": level,
            "clean_start": bool(flags & 0x02),
            "username": username,
            "password": f"<password:{len(password)} chars>" if password else None,
            "keepalive": keepalive,
            "client_id": mask_identifier(client_id or ""),
        },
        ensure_ascii=False,
    )


def _payload_json(payload: bytes) -> Optional[Any]:
    """Parse a PUBLISH payload, skipping the MQTT 5 property block when present.

    ``build_publish_packet`` (and the app) write the property length before the
    JSON body, so a plain ``json.loads`` on the raw bytes fails and the decoder
    would fall back to unredacted free text.
    """
    candidates: List[str] = []
    props_len, pos = read_varint(payload, 0)
    if props_len is not None and pos + props_len <= len(payload):
        candidates.append(payload[pos + props_len :].decode("utf-8", "replace"))
    candidates.append(payload.decode("utf-8", "replace"))
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except ValueError:
            continue
    return None


def _format_publish(
    topic: str,
    qos: int,
    retain: bool,
    packet_id: Optional[int],
    payload: bytes,
    secret_key: Optional[str] = None,
    secret_sink: Optional[Callable[[str], None]] = None,
) -> str:
    head = f"PUBLISH topic={mask_topic(topic)} qos={qos} retain={retain}"
    if packet_id is not None:
        head += f" id={packet_id}"
    if not payload:
        return head + " payload=<empty>"
    parsed = _payload_json(payload)
    if parsed is None:
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            return head + f" payload=<binary {len(payload)} bytes>"
        return head + " payload=" + mask_text(text[:400])
    rendered = json.dumps(
        prepare_payload(parsed, secret_key, secret_sink),
        ensure_ascii=False,
        sort_keys=True,
    )
    if len(rendered) > 2400:
        rendered = rendered[:2400] + "…"
    return head + " payload=" + rendered


def _decode_publish(
    flags: int,
    body: bytes,
    secret_key: Optional[str] = None,
    secret_sink: Optional[Callable[[str], None]] = None,
) -> str:
    topic, pos = _read_string(body, 0)
    if topic is None:
        return "PUBLISH (truncated)"
    qos = (flags >> 1) & 0x03
    packet_id = None
    if qos:
        if pos + 2 > len(body):
            return f"PUBLISH topic={mask_topic(topic)} (truncated)"
        packet_id = int.from_bytes(body[pos : pos + 2], "big")
        pos += 2
    return _format_publish(
        topic, qos, bool(flags & 0x01), packet_id, body[pos:], secret_key, secret_sink
    )


def decode_packet(
    packet: bytes,
    secret_key: Optional[str] = None,
    secret_sink: Optional[Callable[[str], None]] = None,
) -> str:
    if not packet:
        return "<empty>"
    ptype = packet[0] >> 4
    flags = packet[0] & 0x0F
    name = PACKET_TYPES.get(ptype, f"TYPE{ptype}")
    remaining, pos = read_varint(packet, 1)
    body = packet[pos : pos + remaining] if remaining is not None else packet[pos:]
    if ptype == 3:
        return _decode_publish(flags, body, secret_key, secret_sink)
    if ptype == 1:
        return _decode_connect(body)
    if ptype == 2 and len(body) >= 2:
        return f"CONNACK session_present={body[0] & 1} reason={body[1]}"
    if ptype in (8, 10) and len(body) >= 2:
        packet_id = int.from_bytes(body[:2], "big")
        entries = [
            mask_topic(entry)
            for entry in (
                match.decode()
                for match in re.findall(rb"[\x20-\x7e]{3,}", body[2:])
            )
        ]
        return f"{name} id={packet_id} entries={entries}"
    if ptype in (4, 5, 6, 7) and len(body) >= 2:
        return f"{name} id={int.from_bytes(body[:2], 'big')}"
    if ptype == 9 and len(body) >= 3:
        return f"SUBACK id={int.from_bytes(body[:2], 'big')} reasons={list(body[2:])}"
    if ptype == 11 and len(body) >= 2:
        return f"UNSUBACK id={int.from_bytes(body[:2], 'big')}"
    return f"{name} flags=0x{flags:x} bytes={len(packet)} body={body[:48].hex()}"


class MqttDump:
    """mitmproxy addon that decodes MQTT and the allowlisted HTTP calls."""

    def __init__(self) -> None:
        self.buffers: Dict[Tuple[str, bool], bytearray] = {}
        self.transcript = None
        self.http_transcript = None
        self.raw = None
        self.secret_key: Optional[str] = None
        self.secret_seen = False
        self.raw_enabled = False
        self.http_enabled = True

    def load(self, loader: Any) -> None:
        loader.add_option(
            "mqtt_dump_dir",
            str,
            "mqtt-capture",
            "Directory where the capture logs are written",
        )
        loader.add_option(
            "mqtt_dump_raw",
            bool,
            False,
            "Write mqtt-raw.log (local only; CONNECT and logins are still omitted)",
        )
        loader.add_option(
            "mqtt_dump_http",
            bool,
            True,
            "Write http-transcript.log with the allowlisted app HTTP calls",
        )

    def running(self) -> None:
        directory = Path(ctx.options.mqtt_dump_dir)
        directory.mkdir(parents=True, exist_ok=True)
        self.transcript = (directory / "mqtt-transcript.log").open("a", encoding="utf-8")
        self.raw_enabled = bool(getattr(ctx.options, "mqtt_dump_raw", False))
        self.http_enabled = bool(getattr(ctx.options, "mqtt_dump_http", True))
        if self.raw_enabled:
            self.raw = (directory / "mqtt-raw.log").open("a", encoding="utf-8")
        if self.http_enabled:
            self.http_transcript = (directory / "http-transcript.log").open(
                "a", encoding="utf-8"
            )
        ctx.log.info(f"Deepal capture writing to {directory.resolve()}")

    @staticmethod
    def _stamp() -> str:
        now = time.time()
        return f"{time.strftime('%H:%M:%S', time.localtime(now))}.{int(now * 1000) % 1000:03d}"

    @staticmethod
    def _write(stream: Any, line: str) -> None:
        if stream is None:
            return
        stream.write(line)
        stream.flush()

    def _remember_secret(self, secret: str) -> None:
        if self.secret_key is None:
            self.secret_key = secret
            self.secret_seen = True
            self._write(
                self.transcript,
                f"{self._stamp()} secretKey captured ({len(secret)} chars); "
                "sers payloads are decoded locally and the key is never logged\n",
            )

    def _host(self, flow: tcp.TCPFlow) -> str:
        address = flow.server_conn.address
        return address[0] if address else ""

    def tcp_message(self, flow: tcp.TCPFlow) -> None:
        if self.transcript is None:
            return
        host = self._host(flow)
        if host not in TARGET_HOSTS:
            return
        message = flow.messages[-1]
        direction = "C->S" if message.from_client else "S->C"
        stamp = self._stamp()
        if message.content[:2] == TLS_HANDSHAKE:
            self._write(
                self.transcript,
                f"{stamp} {host} {direction} TLS handshake seen but not intercepted; "
                "install/trust the mitmproxy CA and retry\n",
            )
            return
        key = (host, message.from_client)
        buffer = self.buffers.setdefault(key, bytearray())
        buffer.extend(message.content)
        for packet in split_packets(buffer):
            ptype = packet[0] >> 4
            decoded = decode_packet(packet, self.secret_key, self._remember_secret)
            self._write(self.transcript, f"{stamp} {host} {direction} {decoded}\n")
            if not self.raw_enabled:
                continue
            if ptype == 1:
                note = "<CONNECT omitted: it carries the broker credentials>"
            elif "secretKey" in decoded:
                note = "<login response omitted: it carries the secretKey>"
            else:
                note = packet.hex()
            self._write(self.raw, f"{stamp} {host} {direction} {note}\n")

    # --------------------------------------------------------------- HTTP
    @staticmethod
    def _text(message: Any) -> str:
        getter = getattr(message, "get_text", None)
        if getter is None:
            return ""
        try:
            return getter() or ""
        except TypeError:
            return getter(strict=False) or ""

    @staticmethod
    def _request_host(request: Any) -> str:
        return str(
            getattr(request, "pretty_host", None) or getattr(request, "host", "") or ""
        )

    @staticmethod
    def _render_body(text: str) -> str:
        if not text:
            return "<empty>"
        try:
            parsed = json.loads(text)
        except ValueError:
            return mask_text(text[:HTTP_BODY_LIMIT])
        rendered = json.dumps(mask_json(parsed), ensure_ascii=False, sort_keys=True)
        if len(rendered) > HTTP_BODY_LIMIT:
            rendered = rendered[:HTTP_BODY_LIMIT] + "…"
        return rendered

    def http(self, flow: http.HTTPFlow) -> None:
        if not self.http_enabled or self.http_transcript is None:
            return
        request = flow.request
        host = self._request_host(request)
        if not host.endswith(HTTP_HOST_SUFFIXES):
            return
        path = str(getattr(request, "path", "") or "")
        if not any(token in path for token in HTTP_PATH_TOKENS):
            return
        line = (
            f"{self._stamp()} {host} {request.method} {mask_url_path(path)}\n"
            f"  request={self._render_body(self._text(request))}\n"
            f"  headers={json.dumps(safe_headers(request.headers), sort_keys=True)}\n"
        )
        response = getattr(flow, "response", None)
        if response is not None:
            line += (
                f"  status={getattr(response, 'status_code', '?')} "
                f"response={self._render_body(self._text(response))}\n"
            )
        self._write(self.http_transcript, line)


addons = [MqttDump()]
