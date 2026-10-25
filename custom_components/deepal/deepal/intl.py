"""Client for the Changan Deepal international gateway (email login)."""

import asyncio
import base64
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
import hashlib
from ipaddress import ip_address
import json
import logging
import secrets
import socket
import ssl
import time
from typing import Any, Optional
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from .endpoints import (
    DEFAULT_INTL_ENVIRONMENT,
    INTL_CA_GET_AUTH_TOKEN,
    INTL_CA_GET_CAR_AUTH_LIST,
    INTL_CA_GET_CAR_CONF_FUNC,
    INTL_CA_GET_CONN_CONF,
    INTL_CA_GET_DIGITAL_KEY_SUPPORT,
    INTL_CHARGE_ADD_PLAN,
    INTL_CHARGE_DELETE_PLAN,
    INTL_CHARGE_MODIFY_PLAN,
    INTL_CHARGE_PERCENTAGE,
    INTL_CHARGE_VALIDITY,
    INTL_CHECK_CONTROL_CODE,
    INTL_CONDITION_INQUIRY,
    INTL_CONTROL_AIR_CONDITIONER,
    INTL_CONTROL_DEFROST,
    INTL_CONTROL_DOORS,
    INTL_CONTROL_FLASHING_HONKING,
    INTL_CONTROL_FOTA_PLAN,
    INTL_CONTROL_RESULT,
    INTL_CONTROL_SEATS_HEAT,
    INTL_CONTROL_SEATS_WIND,
    INTL_CONTROL_STEERING_WHEEL_HEAT,
    INTL_CONTROL_TRUNK,
    INTL_CONTROL_WINDOWS,
    INTL_DEPARTURE_ADD_PLAN,
    INTL_DEPARTURE_DELETE,
    INTL_DEPARTURE_ENABLED,
    INTL_DEPARTURE_MODIFY_PLAN,
    INTL_DEPARTURE_VALIDITY,
    INTL_GET_FUNCTION_CONFIG,
    INTL_GET_MY_CARS,
    INTL_GET_VEHICLE_MODEL,
    INTL_GET_SERIAL_NO,
    INTL_GET_SECURITY_CODE_STATUS,
    INTL_GET_VEHICLE_CONDITION,
    INTL_LOGIN_BY_EMAIL_CODE,
    INTL_LOGIN_BY_EMAIL_PASSWORD,
    INTL_LOGIN_BY_MOBILE_CODE,
    INTL_LOGIN_BY_MOBILE_PASSWORD,
    INTL_LOGOUT,
    INTL_REFRESH_TOKEN,
    INTL_SDA_GET_AUTH_TOKEN,
    INTL_SDA_GET_CAR_CONDITION,
    INTL_SDA_GET_FUNCTION_CONFIG,
    INTL_SDA_GET_MQTT_SERVER_CONFIG,
    INTL_SDA_VOT_FUNCTION_CONFIG,
    INTL_SEND_EMAIL_CODE,
    INTL_SEND_SMS_CODE,
    REQUEST_ENCRYPTION_PUBLIC_KEY,
    get_intl_environment,
)
from .exceptions import (
    DeepalAPIError,
    DeepalAuthError,
    DeepalCommandAuthError,
    DeepalSessionInvalidated,
    DeepalCommandNotReady,
    DeepalConnectionError,
    DeepalError,
    DeepalRateLimitError,
    parse_retry_after,
)
from .redact import is_sensitive_key, redact_for_log, safe_headers
from .location import find_location
from .models import (
    AuthToken,
    BatteryCondition,
    ClimateCondition,
    CommandResult,
    DigitalKeySupport,
    DoorsCondition,
    FuelCondition,
    LampsCondition,
    SeatsCondition,
    SeatStatus,
    TiresCondition,
    TireStatus,
    Vehicle,
    VehicleAuthorizations,
    VehicleCapabilities,
    VehicleCondition,
    VehicleModelAsset,
    WarningLightsCondition,
    WindowOpeningsCondition,
    WindowsCondition,
)
from .mqtt import (
    CHARGE_TIME_SENTINEL,
    MQTT_CONNACK_REASONS,
    MQTT_DEFAULT_KEEPALIVE,
    MQTT_SDA_PROBE_GRACE,
    MqttTopics,
    S05_SERVICE_CODES,
    SDA_CONDITION_COMMAND,
    SDA_CONDITION_SECTIONS,
    SDA_CONDITION_SERVICE,
    SDA_SERVICE_CODES,
    WAKE_PACKET_ID,
    MqttExchangeResult,
    SdaBrokerConfig,
    SdaConditionPlan,
    SdaSessionResult,
    aes_cbc_decrypt,
    basic_identifiers,
    build_connect_packet,
    build_disconnect_packet,
    build_puback_packet,
    build_publish_packet,
    build_subscribe_packet,
    clean_charge_current,
    clean_charge_current_magnitude,
    condition_request_payload,
    condition_request_services,
    config_mqtt_identity,
    device_id_candidates,
    login_request_payload,
    new_request_id,
    normalize_s05_params,
    normalize_sda_params,
    parse_connack,
    parse_publish,
    parse_sda_broker_config,
    parse_suback,
    read_packet,
    read_packet_with_keepalive,
    resolve_mqtt_topics,
    sda_broker_session,
    sda_condition_plan,
    sda_condition_request_payload,
    sda_condition_request_services,
    sda_session_topics,
    secret_from_login_payload,
    topic_with_device,
    unmapped_s05_keys,
    wake_request_payload,
    wake_request_services,
)

logger = logging.getLogger("deepal_sdk")

# Charge keys the debug discovery log prints on every S05 report so a session
# can be diagnosed from a log without downloading the diagnostics.
S05_CHARGE_DEBUG_KEYS = (
    "ChrgSts",
    "BattACChrgInCurr",
    "battACChrgInCurr",
    "BattDCChrgInCurr",
    "battDCChrgInCurr",
    "chargDeltMins",
    "acChargeGunConnectionState",
    "dcChargeGunConnectionState",
    "dcDhargeGunConnectionState",
)

INTL_APP_ID = "ca"
INTL_APP_TYPE = "Android"
INTL_APP_VERSION = "V1.12.0"
INTL_DEVICE_TYPE = "samsung"
INTL_OS_VERSION = "9"
INTL_USER_AGENT = "okhttp/4.12.0"
DEFAULT_COUNTRY = "GB"
DEFAULT_LANGUAGE = "en_US"

# Flash/honk action codes (CarContrlConfig.java:12,84-86).
FLASH_HONK_OFF = 0
FLASH_HONK_FLASH = 1
FLASH_HONK_BEE = 2
FLASH_HONK_FLASH_BEE = 3

# Signing canonical source policy; see docs/intl-api.md section 7.1.
SIGNING_POLICY_APP = "app"
SIGNING_POLICY_LEGACY = "legacy"
SIGNING_POLICIES = (SIGNING_POLICY_APP, SIGNING_POLICY_LEGACY)
APP_SIGN_EXCLUDED_KEYS = {"sign", "class", "command"}

# Gateway kick-out codes the app treats as session failures
# (CaErrorCode.java:10-27). Compared as strings so numeric codes match too.
_AUTH_ERROR_CODES = {
    "APP_1_1_02_003",
    "APP_1_1_02_004",
    "APP_1_1_02_005",
    "APP_1_1_02_006",
    "CAC_1_1_01_045",
    "46000",
}

# App session refresh windows: a static LastGetRefreshTokenTime guarded by a lock
# (RefreshTokenInterceptor.java:14-21) with tokenExpireTime = 1800000 for the
# international session (RefreshTokenInterceptorKt.java:9-10) and 55 minutes for
# car control (RefreshTokenIntercetorKt.java:10). The car-control window guards a
# module the SDK does not model yet; it is recorded for the planned
# remote-command change.
INTL_REFRESH_THROTTLE_SECONDS = 1800.0

#: MQTT auth tokens are account level; one is reused within this window so a
#: refresh cycle with several vehicles asks the CA gateway once instead of once
#: per MQTT session.
INTL_MQTT_TOKEN_TTL_SECONDS = 60.0

#: The CA connection configuration is per vehicle and practically static; it is
#: reused within this window so the wake report wait (and its retries) fetches
#: it once and the normal polls amortize the bootstrap across cycles. A
#: rejection drops the cache, so a stale configuration cannot survive the
#: reuse window.
INTL_MQTT_CONFIG_TTL_SECONDS = 660.0
CAR_CONTROL_REFRESH_THROTTLE_SECONDS = 3300.0

#: The layered model archives are larger than JSON responses, so the explicit
#: download keeps its own bound instead of inheriting the short API timeout.
VEHICLE_MODEL_DOWNLOAD_TIMEOUT = 60.0

#: Gateway result codes the app accepts as a completed vehicle wake when the
#: response's ``success`` flag is missing or false. The upstream dec_deepal
#: 2.5.1 accepts the same set (MIT): the gateway has been observed answering an
#: accepted wake with ``code`` ``000000`` and a falsy ``success``.
WAKE_OK_CODES = frozenset({"000000", "0", "00000"})

#: MQTT timeouts are independent of the HTTP timeout: socket operations keep
#: the connect budget and the exchange/wake deadlines their own value, so
#: raising the HTTP bound never extends a telemetry or wake exchange.
MQTT_SOCKET_TIMEOUT = 15.0
MQTT_EXCHANGE_TIMEOUT = 20.0


def _auth_failure_class(code: Any, message: Any = None) -> Optional[type]:
    """Return the authentication error class for a rejection, or ``None``.

    Kick-out codes keep raising ``DeepalAuthError``. A rejection whose code
    matches none of the patterns is classified by its message only when it
    identifies an invalid, invalidated or expired session token (the live
    ``invalided token`` wording) and not the command ``rcToken``, which the
    command flow handles on its own; those message-classified failures raise
    ``DeepalSessionInvalidated`` so the CA-bootstrap fallbacks can recover.
    """
    if code is not None:
        code_str = str(code)
        if (
            "AUTH" in code_str.upper()
            or code_str.startswith("401")
            or code_str in _AUTH_ERROR_CODES
        ):
            return DeepalAuthError
    if message is None:
        return None
    lowered = str(message).lower()
    if "rctoken" in lowered:
        return None
    if "token" in lowered and any(
        marker in lowered for marker in ("invalid", "invalidated", "expired", "caduc")
    ):
        return DeepalSessionInvalidated
    return None


def _normalize_country_code(country_code: str) -> str:
    code = (country_code or "").strip().lstrip("+")
    if not code.isdigit():
        raise ValueError(
            "country_code must be a dial code with digits only, e.g. '34' for Spain."
        )
    return code


def _normalize_phone(phone: str) -> str:
    normalized = (phone or "").strip()
    if not normalized:
        raise ValueError("phone is required.")
    if normalized.startswith("+"):
        raise ValueError(
            "phone must be the national number without the country prefix; "
            "pass the dial code in country_code."
        )
    return normalized


def _path_value(data: Any, path: tuple[Any, ...]) -> Any:
    value: Any = data
    for key in path:
        if isinstance(key, int):
            if not isinstance(value, list) or len(value) <= key:
                return None
            value = value[key]
            continue
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _first_auth_token(data: Any) -> Optional[str]:
    """Return ``authToken`` of the app's response shape, flat or nested.

    The SDA ``vot-auth`` call answers with the token at the root (live E07
    trace, issue #2); the gateway wrappers used by other routes nest it under
    ``data`` or ``params``, so all three shapes are accepted.
    """
    if not isinstance(data, dict):
        return None
    for candidate in (data, data.get("data"), data.get("params")):
        if isinstance(candidate, dict) and candidate.get("authToken"):
            return str(candidate["authToken"])
    return None


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _humidity_percent(value: Any) -> Optional[float]:
    """Return the cabin humidity as a percentage.

    The API reports ``insideHumidity`` as a fixed-point integer from 0 to 1000
    with one implied decimal: ``453`` means 45.3 %. Values outside that range,
    or non-numeric values, are unknown.
    """
    humidity = _as_float(value)
    if humidity is None or not 0 <= humidity <= 1000:
        return None
    return round(humidity / 10, 1)


def _as_bool(value: Any) -> Optional[bool]:
    """Return a boolean for zero/non-zero values, ``None`` when absent."""
    number = _as_int(value)
    return None if number is None else number != 0


def _fuel_range_km(fuel: dict[str, Any]) -> Optional[int]:
    """Return the fuel remaining range, preferring the EU WLTC standard.

    ``remainingRange`` is the unit-agnostic key the MQTT normalization emits for
    ``remainedOilMile``; the REST payload carries the standard suffixes instead.
    """
    for key in (
        "remainingRange",
        "fuelWltcRemainingMileage",
        "fuelNedcRemainingMileage",
        "fuelCltcRemainingMileage",
        "fuelSumRemainingMileage",
    ):
        value = _as_int(fuel.get(key))
        if value is not None:
            return value
    return None


def _is_charge_connection(value: Any) -> bool:
    """Return whether a charge connection state means a connected gun.

    The live S05 reports ``0`` with no gun, ``1`` with the DC gun connected and
    ``3`` with the AC gun connected (2026-10-25 captures); any other reported
    value is also a connected state and an absent value is not connected. The
    old ``0``/``1`` not-connected rule marked a DC session as unplugged.
    """
    return _as_int(value) not in (None, 0)


def _gun_connected(value: Any) -> bool:
    """Return whether a gun value means connected, accepting codes or booleans.

    The normalizers resolve the S05 flags from the charging state and send
    booleans; the raw connection fields use ``0`` for not connected and any
    other reported value for connected.
    """
    if isinstance(value, bool):
        return value
    return _is_charge_connection(value)


def _gun_connected_optional(value: Any) -> Optional[bool]:
    """Return ``None`` when the vehicle did not report a gun value."""
    if value is None:
        return None
    return _gun_connected(value)


def _to_millis(value: Any) -> Optional[int]:
    """Normalize an ISO-8601 string or epoch seconds/milliseconds to epoch ms."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        parsed = int(value)
        return parsed if abs(parsed) >= 100_000_000_000 else parsed * 1000
    if isinstance(value, str) and value:
        text = value.strip()
        try:
            parsed = int(float(text))
        except ValueError:
            pass
        else:
            return parsed if abs(parsed) >= 100_000_000_000 else parsed * 1000
        try:
            parsed_dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed_dt.tzinfo is None:
            parsed_dt = parsed_dt.replace(tzinfo=UTC)
        return int(parsed_dt.timestamp() * 1000)
    return None


def _is_internal_address(value: str) -> bool:
    """Return whether an IP literal is not globally routable."""
    try:
        return not ip_address(value).is_global
    except ValueError:
        return False


def _is_local_hostname(host: str) -> bool:
    """Return whether a hostname names the local machine or network."""
    normalized = host.lower().rstrip(".")
    return (
        not normalized
        or normalized == "localhost"
        or normalized.endswith(".localhost")
        or normalized.endswith(".local")
    )


async def _async_host_is_public(host: str, resolver: Any = None) -> bool:
    """Return whether a URL host may be fetched by the SDK."""
    if not host or _is_internal_address(host) or _is_local_hostname(host):
        return False
    try:
        if resolver is None:
            infos = await asyncio.get_running_loop().getaddrinfo(
                host, 443, type=socket.SOCK_STREAM
            )
        else:
            infos = await resolver(host)
    except OSError:
        return False
    addresses = {info[4][0] for info in infos}
    return bool(addresses) and all(
        not _is_internal_address(address) for address in addresses
    )


class DeepalIntlClient:
    """Asynchronous client for the Deepal international email login flow."""

    def __init__(
        self,
        country: str = DEFAULT_COUNTRY,
        language: str = DEFAULT_LANGUAGE,
        app_version: str = INTL_APP_VERSION,
        app_type: str = INTL_APP_TYPE,
        device_type: str = INTL_DEVICE_TYPE,
        os_version: str = INTL_OS_VERSION,
        tsp_token_source: str = "access",
        environment: str = DEFAULT_INTL_ENVIRONMENT,
        mqtt_config_fallback: bool = True,
        mqtt_client_id: Optional[str] = None,
        mqtt_username: Optional[str] = None,
        mqtt_keepalive: float = MQTT_DEFAULT_KEEPALIVE,
        mqtt_clean_start: bool = True,
        mqtt_tls_insecure: bool = False,
        mqtt_sda_probe_grace: float = MQTT_SDA_PROBE_GRACE,
        mqtt_exchange_timeout: Optional[float] = None,
        mqtt_wake_timeout: Optional[float] = None,
        mqtt_token_ttl: float = INTL_MQTT_TOKEN_TTL_SECONDS,
        mqtt_config_ttl: float = INTL_MQTT_CONFIG_TTL_SECONDS,
        device_id: Optional[str] = None,
        private_key_pem: Optional[str] = None,
        public_key: Optional[str] = None,
        base_url: Optional[str] = None,
        ca_base_url: Optional[str] = None,
        sda_base_url: Optional[str] = None,
        timeout: float = 30.0,
        enable_api_logging: bool = False,
        signing_policy: str = SIGNING_POLICY_APP,
        httpx_client: Optional[httpx.AsyncClient] = None,
        on_exchange: Optional[Callable[[dict[str, Any]], None]] = None,
    ):
        if signing_policy not in SIGNING_POLICIES:
            supported = ", ".join(SIGNING_POLICIES)
            raise ValueError(
                f"Unknown signing policy {signing_policy!r}; supported: {supported}."
            )
        environment_config = get_intl_environment(environment)
        self.country = country
        self.language = language
        self.app_version = app_version
        self.app_type = app_type
        self.device_type = device_type
        self.os_version = os_version
        self.tsp_token_source = tsp_token_source
        self.environment = environment_config.id
        self.app_id = environment_config.app_id
        self._intl_path_prefix = environment_config.intl_path_prefix
        self.mqtt_config_fallback = mqtt_config_fallback
        self.mqtt_client_id = mqtt_client_id
        self.mqtt_username = mqtt_username
        self.mqtt_keepalive = mqtt_keepalive
        self.mqtt_clean_start = mqtt_clean_start
        self.mqtt_tls_insecure = mqtt_tls_insecure
        self.mqtt_sda_probe_grace = mqtt_sda_probe_grace
        self.mqtt_exchange_timeout = mqtt_exchange_timeout
        self.mqtt_wake_timeout = mqtt_wake_timeout
        self.mqtt_token_ttl = mqtt_token_ttl
        self.mqtt_config_ttl = mqtt_config_ttl
        self._mqtt_token: Optional[str] = None
        self._mqtt_token_expires_at = 0.0
        self._mqtt_configs: dict[str, tuple[dict[str, Any], float]] = {}
        self.last_mqtt_exchange: Optional[MqttExchangeResult] = None
        self.device_id = device_id or secrets.token_hex(16)
        self.base_url = (base_url or environment_config.intl_base_url).rstrip("/")
        self.ca_base_url = (ca_base_url or environment_config.ca_base_url).rstrip("/")
        self.sda_base_url = (
            sda_base_url or environment_config.sda_base_url
        ).rstrip("/")
        self.timeout = timeout
        self.enable_api_logging = enable_api_logging
        self.on_exchange = on_exchange
        self.signing_policy = signing_policy
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.cac_token: Optional[str] = None
        self.access_token_expires_at: Optional[int] = None
        self.user_id: Optional[str] = None
        self.ca_user_id: Optional[str] = None
        self.cac_user_id: Optional[str] = None
        self.control_pin: Optional[str] = None
        self.location_enabled = False
        self.rc_token: Optional[str] = None
        self.public_key: Optional[str] = public_key
        self.private_key_pem: Optional[str] = private_key_pem
        self._external_client = httpx_client is not None
        self._client: Optional[httpx.AsyncClient] = httpx_client
        self._client_lock = asyncio.Lock()
        self._refresh_lock = asyncio.Lock()
        self._mqtt_lock = asyncio.Lock()
        self._last_refresh_attempt_at: Optional[float] = None
        self._refresh_attempt_sequence = 0
        self._refresh_attempt_error: Optional[BaseException] = None
        self._last_refresh_kept_token = False

    async def _http_client(self) -> httpx.AsyncClient:
        """Return the managed HTTP client, creating it outside the event loop."""
        if self._client is None:
            async with self._client_lock:
                if self._client is None:
                    self._client = await asyncio.to_thread(
                        httpx.AsyncClient, timeout=self.timeout
                    )
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client if managed internally."""
        if self._external_client or self._client is None:
            return
        if not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self) -> "DeepalIntlClient":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    def _emit_exchange(self, event: dict[str, Any]) -> None:
        """Deliver one structured exchange event to the optional callback."""
        callback = getattr(self, "on_exchange", None)
        if callback is None:
            return
        try:
            callback(event)
        except Exception:  # noqa: BLE001 - diagnostics must never break a call
            logger.exception("Deepal exchange callback failed")

    def _emit_mqtt(self, event: str, **data: Any) -> None:
        """Deliver one MQTT event with the common envelope."""
        self._emit_exchange(
            {
                "ts": datetime.now(UTC).isoformat(),
                "kind": "mqtt",
                "event": event,
                **data,
            }
        )

    @staticmethod
    def _strip_pem_armor(pem: str) -> str:
        """Return a PEM body without its armor marker lines.

        Only lines that start with the ``-----`` marker are removed. Filtering
        by substring would drop random base64 body lines that contain
        ``BEGIN``/``END`` and register a broken login key.
        """
        return "\n".join(
            line for line in pem.splitlines() if not line.startswith("-----")
        ) + "\n"

    @staticmethod
    def _public_body(public_key: rsa.RSAPublicKey) -> str:
        """Render an RSA public key as the app ``pubKey`` body."""
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
        return DeepalIntlClient._strip_pem_armor(public_pem)

    @staticmethod
    def generate_login_keypair() -> tuple[str, str]:
        """Generate the RSA keypair used for the login pubKey field."""
        key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
        private_pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
        return private_pem, DeepalIntlClient._public_body(key.public_key())

    @staticmethod
    def public_key_body_from_private(private_key_pem: str) -> str:
        """Derive the app ``pubKey`` body from a stored login private PEM."""
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode(), password=None
        )
        return DeepalIntlClient._public_body(private_key.public_key())

    def set_login_keypair(
        self, private_key_pem: str, public_key: Optional[str] = None
    ) -> str:
        """Restore the persisted login keypair on this client.

        Stores the private PEM and resolves the app ``pubKey`` body: the
        provided public key when given, otherwise the public key derived from
        the private PEM. The private key is parsed even when the caller brings
        a public key, so an unusable stored key fails here instead of every
        command. The client is only updated once the parse succeeds. Returns
        the resolved public key body.
        """
        if not private_key_pem:
            raise ValueError("private_key_pem is required.")
        derived_public_key = self.public_key_body_from_private(private_key_pem)
        self.private_key_pem = private_key_pem
        self.public_key = public_key or derived_public_key
        return self.public_key

    @staticmethod
    def encrypt_request_value(value: str) -> str:
        """Encrypt a sensitive value with the app RSA public key (PKCS#1 v1.5)."""
        public_key = serialization.load_der_public_key(
            base64.b64decode(REQUEST_ENCRYPTION_PUBLIC_KEY)
        )
        ciphertext = public_key.encrypt(value.encode(), padding.PKCS1v15())
        return base64.b64encode(ciphertext).decode()

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "appid": self.app_id,
            "language": self.language,
            "appversion": self.app_version,
            "apptype": self.app_type,
            "devicetype": self.device_type,
            "deviceid": self.device_id,
            "selectcountry": self.country,
            "x-os-version": self.os_version,
            "accept-language": self.language,
            "content-type": "application/json; charset=UTF-8",
            "user-agent": INTL_USER_AGENT,
        }
        if self.access_token:
            headers["authorization"] = self._authorization_value()
            tsp_value = {
                "access": self.access_token,
                "cac": self.cac_token,
                "cac_user_id": self.cac_user_id,
                "ca_user_id": self.ca_user_id,
            }.get(self.tsp_token_source, self.access_token)
            if tsp_value:
                headers["X-Tsp-User-Token"] = tsp_value
                headers["X-VCS-User-Token"] = tsp_value
        return headers

    def _authorization_value(self) -> str:
        if self.cac_token and "|" not in self.access_token:
            return f"{self.access_token}|{self.cac_token}"
        return self.access_token

    async def _request(
        self,
        path: str,
        json_data: Optional[dict[str, Any]] = None,
        auth_required: bool = False,
        base_url: Optional[str] = None,
        *,
        method: str = "POST",
        query: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Perform an HTTP request against the international gateway."""
        if auth_required and not self.access_token:
            raise DeepalAuthError("Access token is required for this operation.")

        if self._intl_path_prefix != "/intl-app-gw" and path.startswith(
            "/intl-app-gw"
        ):
            path = self._intl_path_prefix + path[len("/intl-app-gw") :]
        url = f"{base_url or self.base_url}{path}" if path.startswith("/") else path
        body = json.dumps(json_data or {}, separators=(",", ":"), ensure_ascii=False)
        headers = self._get_headers()
        if base_url and base_url.rstrip("/") == self.sda_base_url:
            # The SDA gateway expects the login token without the "Bearer "
            # prefix (verified against the official app; the intl hosts keep
            # the prefixed value in Authorization) and answers with a body that
            # only decodes when compression is disabled.
            sda_token = (self.access_token or "").removeprefix("Bearer ").strip()
            if sda_token:
                headers["X-Tsp-User-Token"] = sda_token
            headers["Accept-Encoding"] = "identity"
        if self.enable_api_logging:
            logger.warning(
                "Deepal API request path=%s headers=%s payload=%s",
                path,
                safe_headers(headers),
                redact_for_log(json_data or {}),
            )

        started = time.monotonic()
        try:
            http_client = await self._http_client()
            if method.upper() == "GET":
                response = await http_client.request(
                    method="GET",
                    url=url,
                    params=query,
                    headers=headers,
                    timeout=self.timeout,
                )
            else:
                response = await http_client.request(
                    method=method.upper(),
                    url=url,
                    content=body,
                    headers=headers,
                    timeout=self.timeout,
                )
        except httpx.RequestError as exc:
            self._emit_exchange(
                {
                    "ts": datetime.now(UTC).isoformat(),
                    "kind": "rest",
                    "event": "error",
                    "client": "intl",
                    "method": method.upper(),
                    "path": path,
                    "url": url,
                    "query": query,
                    "request": json_data,
                    "headers": headers,
                    "error": str(exc),
                    "duration_ms": round((time.monotonic() - started) * 1000, 1),
                }
            )
            logger.error("Network error requesting %s: %s", url, exc)
            raise DeepalConnectionError(f"Failed to connect to Deepal API: {exc}") from exc

        if response.status_code == 429:
            self._emit_exchange(
                {
                    "ts": datetime.now(UTC).isoformat(),
                    "kind": "rest",
                    "event": "response",
                    "client": "intl",
                    "method": method.upper(),
                    "path": path,
                    "url": url,
                    "query": query,
                    "request": json_data,
                    "headers": headers,
                    "status": response.status_code,
                    "response": response.text[:2000],
                    "duration_ms": round((time.monotonic() - started) * 1000, 1),
                }
            )
            raise DeepalRateLimitError(
                "Deepal rate limit: HTTP 429.",
                status_code=429,
                retry_after=parse_retry_after(response.headers.get("Retry-After")),
            )

        if response.status_code in (401, 403):
            self._emit_exchange(
                {
                    "ts": datetime.now(UTC).isoformat(),
                    "kind": "rest",
                    "event": "response",
                    "client": "intl",
                    "method": method.upper(),
                    "path": path,
                    "url": url,
                    "query": query,
                    "request": json_data,
                    "headers": headers,
                    "status": response.status_code,
                    "response": response.text[:2000],
                    "duration_ms": round((time.monotonic() - started) * 1000, 1),
                }
            )
            raise DeepalAuthError(
                f"Authentication failed with HTTP {response.status_code}."
            )

        try:
            payload: Any = response.json()
            response_body: Any = payload
            invalid_json = False
        except ValueError:
            payload = None
            response_body = response.text[:2000]
            invalid_json = True

        self._emit_exchange(
            {
                "ts": datetime.now(UTC).isoformat(),
                "kind": "rest",
                "event": "response",
                "client": "intl",
                "method": method.upper(),
                "path": path,
                "url": url,
                "query": query,
                "request": json_data,
                "headers": headers,
                "status": response.status_code,
                "response": response_body,
                "error": "invalid_json" if invalid_json else None,
                "duration_ms": round((time.monotonic() - started) * 1000, 1),
            }
        )

        if invalid_json:
            raise DeepalAPIError(
                f"Invalid JSON response: {response.text[:200]}",
                status_code=response.status_code,
            )

        if not isinstance(payload, dict):
            raise DeepalAPIError(
                f"Unexpected Deepal response: {type(payload).__name__}",
                status_code=response.status_code,
            )

        if self.enable_api_logging:
            logger.warning(
                "Deepal API response path=%s status=%s body=%s",
                path,
                response.status_code,
                redact_for_log(payload),
            )

        if payload.get("success") is False:
            code = payload.get("code")
            msg = payload.get("msg") or payload.get("message") or f"HTTP {response.status_code}"
            if str(code) == "CAC_1_1_01_033":
                raise DeepalRateLimitError(
                    f"Deepal rate limit: {code} {msg}",
                    status_code=response.status_code,
                    code=code,
                )
            if str(code) == "HW_1_1_01_047":
                raise DeepalRateLimitError(
                    f"Too many control-code attempts ({code}); wait for the lockout "
                    "to expire or reset the PIN in the My Changan app.",
                    status_code=response.status_code,
                    code=code,
                )
            if str(code) in ("HW_1_1_01_073", "HW_1_1_01_074"):
                state = (
                    "the control code expired"
                    if str(code) == "HW_1_1_01_073"
                    else "no control code is set"
                )
                raise DeepalCommandAuthError(
                    f"Remote control unavailable: {state}; set or reset the PIN in "
                    "the My Changan app."
                )
            if str(code) == "COMMON_1_1_01_001" and path.endswith("/serial-no/get"):
                raise DeepalCommandAuthError(
                    "Remote command signing was rejected; log in again to register "
                    "a new command-signing key."
                )
            auth_error = _auth_failure_class(code, msg)
            if auth_error is not None:
                raise auth_error(f"Authentication failed: {code} {msg}")
            detail = f"{code} {msg}" if code is not None else msg
            raise DeepalAPIError(
                f"API Error: {detail}",
                status_code=response.status_code,
                code=code,
            )

        if not response.is_success:
            code = payload.get("code")
            raise DeepalAPIError(
                f"API Error: HTTP {response.status_code} ({code})",
                status_code=response.status_code,
                code=code,
            )

        return payload.get("data")

    def _ensure_pub_key(self, pub_key: Optional[str] = None) -> str:
        """Resolve the login ``pubKey`` without replacing stored key material.

        Order: the caller-provided key for this login, the client's public key,
        the public key derived from a stored private key, and only then a new
        keypair. A stored private key is never replaced while only the public
        half is missing.
        """
        if pub_key:
            return pub_key
        if self.public_key:
            return self.public_key
        if self.private_key_pem:
            self.public_key = self.public_key_body_from_private(self.private_key_pem)
            return self.public_key
        self.private_key_pem, self.public_key = self.generate_login_keypair()
        return self.public_key

    def _store_tokens(self, data: Any) -> AuthToken:
        if not isinstance(data, dict) or not data.get("token"):
            raise DeepalAuthError("Login response did not contain an access token.")

        self.access_token = str(data["token"])
        self.refresh_token = data.get("refreshToken")
        self.cac_token = data.get("cacToken")
        self.access_token_expires_at = self._jwt_expiry(self.access_token)
        self.user_id = data.get("userId")
        self.ca_user_id = data.get("caUserId")
        self.cac_user_id = data.get("cacUserId")
        self._log_session_fields()

        return AuthToken(
            access_token=self.access_token,
            refresh_token=self.refresh_token,
            cac_token=self.cac_token,
            ca_user_id=self.ca_user_id,
            cac_user_id=self.cac_user_id,
            user_id=self.user_id,
        )

    def _log_session_fields(self) -> None:
        """Log which session fields are present, never their values."""
        logger.debug(
            "Deepal session fields present: token=%s refreshToken=%s cacToken=%s "
            "userId=%s caUserId=%s cacUserId=%s",
            bool(self.access_token),
            bool(self.refresh_token),
            bool(self.cac_token),
            bool(self.user_id),
            bool(self.ca_user_id),
            bool(self.cac_user_id),
        )

    def _current_auth_token(self) -> AuthToken:
        """Return the current session as an ``AuthToken``.

        Omitted fields keep the previous value; ``user_id`` is included so a
        refresh response without ``userId`` does not drop the stored one.
        """
        return AuthToken(
            access_token=self.access_token or "",
            refresh_token=self.refresh_token,
            cac_token=self.cac_token,
            ca_user_id=self.ca_user_id,
            cac_user_id=self.cac_user_id,
            user_id=self.user_id,
        )

    def _refresh_is_throttled(self) -> bool:
        """Return whether the last automatic attempt is inside the app window."""
        if self._last_refresh_attempt_at is None:
            return False
        elapsed = time.monotonic() - self._last_refresh_attempt_at
        return elapsed < INTL_REFRESH_THROTTLE_SECONDS

    async def request_email_code(self, email: str) -> None:
        """Request an email login verification code."""
        await self._request(
            INTL_SEND_EMAIL_CODE,
            json_data={
                "type": "0",
                "email": self.encrypt_request_value(email),
            },
        )

    async def login_with_email_code(
        self,
        email: str,
        code: str,
        sales_country: Optional[str] = None,
        pub_key: Optional[str] = None,
    ) -> AuthToken:
        """Login with an email verification code and return the account tokens."""
        data = await self._request(
            INTL_LOGIN_BY_EMAIL_CODE,
            json_data={
                "authCode": code,
                "salesCountry": sales_country or self.country,
                "email": self.encrypt_request_value(email),
                "pubKey": self._ensure_pub_key(pub_key),
            },
        )
        return self._store_tokens(data)

    async def login_with_email_password(
        self,
        email: str,
        password: str,
        sales_country: Optional[str] = None,
        pub_key: Optional[str] = None,
    ) -> AuthToken:
        """Login with an email and password (experiment E12, unverified body).

        The route is recovered from ``LoginApi.emailLoginByPwd``, but the app
        method body is VMP-extracted, so the request field names are modeled on
        the sibling verification-code flow. The email and password are
        RSA-encrypted with the app public key.
        """
        data = await self._request(
            INTL_LOGIN_BY_EMAIL_PASSWORD,
            json_data={
                "salesCountry": sales_country or self.country,
                "email": self.encrypt_request_value(email),
                "password": self.encrypt_request_value(password),
                "pubKey": self._ensure_pub_key(pub_key),
            },
        )
        return self._store_tokens(data)

    async def request_sms_code(self, phone: str, country_code: str) -> None:
        """Request an SMS login verification code."""
        await self._request(
            INTL_SEND_SMS_CODE,
            json_data={
                "countryCode": _normalize_country_code(country_code),
                "mobile": self.encrypt_request_value(_normalize_phone(phone)),
            },
        )

    async def login_with_sms_code(
        self,
        phone: str,
        code: str,
        country_code: str,
        sales_country: Optional[str] = None,
        pub_key: Optional[str] = None,
    ) -> AuthToken:
        """Login with an SMS verification code and return the account tokens."""
        dial_code = _normalize_country_code(country_code)
        mobile = _normalize_phone(phone)
        data = await self._request(
            INTL_LOGIN_BY_MOBILE_CODE,
            json_data={
                "authCode": code,
                "countryCode": dial_code,
                "mobile": self.encrypt_request_value(mobile),
                "salesCountry": sales_country or self.country,
                "pubKey": self._ensure_pub_key(pub_key),
            },
        )
        return self._store_tokens(data)

    async def login_with_password(
        self,
        phone: str,
        password: str,
        country_code: str,
        sales_country: Optional[str] = None,
        pub_key: Optional[str] = None,
    ) -> AuthToken:
        """Login with a mobile number and password (experiment E13, unverified).

        The route is recovered from ``LoginApi.loginByPwd``, but the app method
        body is VMP-extracted, so the request field names are modeled on the
        sibling verification-code flow. Phone validation is shared with the SMS
        flow; the mobile and password are RSA-encrypted with the app public key.
        """
        dial_code = _normalize_country_code(country_code)
        mobile = _normalize_phone(phone)
        data = await self._request(
            INTL_LOGIN_BY_MOBILE_PASSWORD,
            json_data={
                "countryCode": dial_code,
                "mobile": self.encrypt_request_value(mobile),
                "password": self.encrypt_request_value(password),
                "salesCountry": sales_country or self.country,
                "pubKey": self._ensure_pub_key(pub_key),
            },
        )
        return self._store_tokens(data)

    async def logout(self) -> None:
        """Terminate the session (experiment E14, unverified response).

        Posts to ``INTL_LOGOUT`` with the session headers and clears the local
        access, refresh, CAC and control tokens afterwards, even when the
        remote call fails. Does nothing without an access token.
        """
        if not self.access_token:
            return
        try:
            await self._request(INTL_LOGOUT, json_data={}, auth_required=True)
        except DeepalError as exc:
            logger.warning(
                "Deepal logout failed (%s); clearing the local session anyway", exc
            )
        finally:
            self.access_token = None
            self.refresh_token = None
            self.cac_token = None
            self.rc_token = None
            self.access_token_expires_at = None
            self._invalidate_mqtt_token()
            self._invalidate_mqtt_config()

    @staticmethod
    def _jwt_expiry(token: Optional[str]) -> Optional[int]:
        """Return the ``exp`` claim of a JWT access token, if present."""
        if not token or token.count(".") < 2:
            return None
        try:
            payload_b64 = token.split(".")[1]
            payload_b64 += "=" * (-len(payload_b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            exp = payload.get("exp")
            return int(exp) if exp is not None else None
        except (ValueError, TypeError):
            return None

    def access_token_expires_soon(self, margin_seconds: int = 300) -> bool:
        """Return whether the access token expires within the margin."""
        if self.access_token_expires_at is None and self.access_token:
            self.access_token_expires_at = self._jwt_expiry(self.access_token)
        if self.access_token_expires_at is None:
            return False
        return time.time() >= self.access_token_expires_at - margin_seconds

    async def refresh_tokens(self, force: bool = False) -> AuthToken:
        """Refresh the international session tokens.

        Periodic attempts are throttled with the app's monotonic 30-minute
        window and serialized with a per-client lock, so concurrent callers
        cause at most one request in flight and share its outcome. A refresh
        justified by the access token JWT ``exp``, or an explicit ``force`` for
        an authentication rejection, bypasses the throttle.
        """
        if not self.refresh_token:
            raise DeepalAuthError("No refresh token is available.")

        seen_attempt = self._refresh_attempt_sequence
        async with self._refresh_lock:
            if self._refresh_attempt_sequence != seen_attempt:
                if self._refresh_attempt_error is not None:
                    raise self._refresh_attempt_error
                return self._current_auth_token()
            return await self._refresh_tokens_locked(force=force)

    async def _refresh_tokens_locked(self, force: bool = False) -> AuthToken:
        """Run one refresh attempt while holding the per-client lock."""
        if (
            not force
            and self._refresh_is_throttled()
            and (
                not self.access_token_expires_soon()
                or self._last_refresh_kept_token
            )
        ):
            logger.info(
                "Deepal refresh throttled by the app window (%.0f s); keeping the "
                "current session",
                INTL_REFRESH_THROTTLE_SECONDS,
            )
            return self._current_auth_token()

        # The attempt is recorded before the request, so failures occupy the
        # window for reactive attempts too, like the app interceptor does.
        self._last_refresh_attempt_at = time.monotonic()
        self._refresh_attempt_error = None
        previous_access_token = self.access_token
        try:
            data = await self._request(
                INTL_REFRESH_TOKEN,
                json_data={"refreshToken": self.refresh_token},
            )

            if not isinstance(data, dict) or not data.get("token"):
                raise DeepalAuthError(
                    "Refresh response did not contain an access token."
                )

            self.access_token = str(data["token"])
            self.refresh_token = data.get("refreshToken") or self.refresh_token
            self.cac_token = data.get("cacToken") or self.cac_token
            self.access_token_expires_at = self._jwt_expiry(self.access_token)
            self.user_id = data.get("userId") or self.user_id
            self.ca_user_id = data.get("caUserId") or self.ca_user_id
            self.cac_user_id = data.get("cacUserId") or self.cac_user_id
            self._log_session_fields()
            self._invalidate_mqtt_token()

            rotated = self.access_token != previous_access_token
            self._last_refresh_kept_token = not rotated
            if data.get("cacToken"):
                logger.info("Deepal token refresh returned a new CAC token")
            elif rotated:
                logger.warning(
                    "Deepal token refresh did not return a new CAC token; the CA/MQTT "
                    "bootstrap keeps the previous one"
                )
            else:
                logger.debug(
                    "Deepal token refresh kept the current access token; keeping "
                    "the session"
                )

            token = self._current_auth_token()
        except Exception as exc:
            self._refresh_attempt_sequence += 1
            self._refresh_attempt_error = exc
            raise
        else:
            self._refresh_attempt_sequence += 1
            return token

    async def get_vehicles(self) -> list[Vehicle]:
        """Fetch the account vehicles from the international gateway."""
        data = await self._request(INTL_GET_MY_CARS, auth_required=True)
        items = data if isinstance(data, list) else (data or {}).get("list", [])

        vehicles = []
        for item in items:
            vehicles.append(
                Vehicle(
                    car_id=str(item.get("carId") or item.get("car_id") or ""),
                    vin=item.get("vin") or "",
                    series_name=item.get("seriesName") or item.get("series_name") or "Deepal",
                    series_code=item.get("seriesCode") or item.get("series_code"),
                    model_name=item.get("modelName") or item.get("model_name"),
                    model_code=item.get("modelCode") or item.get("model_code"),
                    car_name=item.get("nickName") or item.get("carName"),
                    license_plate=item.get("licensePlate") or item.get("plateNumber"),
                    thumbnail_url=(
                        item.get("imgUrl")
                        or item.get("vehicleImageUrl")
                        or item.get("imageUrl")
                        or item.get("carImageUrl")
                        or item.get("modelImageUrl")
                    ),
                    car_platform=(
                        item.get("carPlatform")
                        if item.get("carPlatform") is not None
                        else item.get("car_platform")
                    ),
                    protocol_type=item.get("protocolType") or item.get("protocol_type"),
                )
            )
        return vehicles

    async def get_vehicle_model(
        self, vehicle_id: str, car_platform: Optional[int] = None
    ) -> VehicleModelAsset:
        """Fetch the official layered model descriptor of a vehicle.

        The official app asks ``intl-app-user/api/car/get-vehicle-model`` for a
        ZIP URL and MD5. The app sends the vehicle identifier and the platform
        value it got from the vehicle list. The body was confirmed against a
        live S05 BEV session on 2026-10-21: ``carId`` plus ``carPlatform`` 2 is
        accepted and returns the layered ZIP. When the caller does not know the
        platform, only the vehicle identifier is sent instead of inventing a
        value.
        """
        body: dict[str, Any] = {"carId": vehicle_id}
        if car_platform is not None:
            body["carPlatform"] = car_platform

        data = await self._request(
            INTL_GET_VEHICLE_MODEL, json_data=body, auth_required=True
        )
        if not isinstance(data, dict):
            raise DeepalAPIError(
                "Vehicle model response did not contain a descriptor object."
            )

        model_url = data.get("modelUrl") or data.get("model_url")
        if not isinstance(model_url, str) or not model_url.strip():
            raise DeepalAPIError(
                "Vehicle model response did not contain a modelUrl."
            )

        md5 = data.get("md5") or data.get("MD5")
        return VehicleModelAsset(
            model_url=model_url.strip(),
            md5=str(md5).strip() if md5 else None,
        )

    async def download_vehicle_model_archive(
        self, vehicle_id: str, car_platform: Optional[int] = None
    ) -> bytes:
        """Download the official layered model ZIP and verify its checksum.

        The descriptor URL is treated as untrusted: only HTTPS is accepted,
        redirects are not followed and the bytes must match the advertised MD5
        before they are returned. The archive is returned raw; extracting it is
        the caller's responsibility.
        """
        asset = await self.get_vehicle_model(vehicle_id, car_platform)
        parsed_url = urlsplit(asset.model_url)
        if parsed_url.scheme != "https" or not parsed_url.hostname:
            raise DeepalAPIError(
                "Vehicle model URL is not HTTPS; refusing to download it."
            )
        if not await _async_host_is_public(parsed_url.hostname):
            raise DeepalAPIError(
                "Vehicle model URL points to a local or internal host; "
                "refusing to download it."
            )

        started = time.monotonic()
        try:
            http_client = await self._http_client()
            response = await http_client.get(
                asset.model_url,
                timeout=VEHICLE_MODEL_DOWNLOAD_TIMEOUT,
                follow_redirects=False,
                headers={"accept": "application/zip, application/octet-stream, */*"},
            )
        except httpx.RequestError as exc:
            self._emit_exchange(
                {
                    "ts": datetime.now(UTC).isoformat(),
                    "kind": "rest",
                    "event": "error",
                    "client": "intl",
                    "method": "GET",
                    "path": asset.model_url,
                    "url": asset.model_url,
                    "vehicle_id": vehicle_id,
                    "error": str(exc),
                    "duration_ms": round((time.monotonic() - started) * 1000, 1),
                }
            )
            logger.error(
                "Network error downloading vehicle model for %s: %s",
                vehicle_id,
                exc,
            )
            raise DeepalConnectionError(
                f"Failed to download the vehicle model archive: {exc}"
            ) from exc

        if response.is_redirect:
            self._emit_exchange(
                {
                    "ts": datetime.now(UTC).isoformat(),
                    "kind": "rest",
                    "event": "response",
                    "client": "intl",
                    "method": "GET",
                    "path": asset.model_url,
                    "url": asset.model_url,
                    "vehicle_id": vehicle_id,
                    "status": response.status_code,
                    "bytes": len(response.content),
                    "error": "redirect",
                    "duration_ms": round((time.monotonic() - started) * 1000, 1),
                }
            )
            raise DeepalAPIError(
                "Vehicle model download returned a redirect; refusing to follow it."
            )
        if not response.is_success:
            self._emit_exchange(
                {
                    "ts": datetime.now(UTC).isoformat(),
                    "kind": "rest",
                    "event": "response",
                    "client": "intl",
                    "method": "GET",
                    "path": asset.model_url,
                    "url": asset.model_url,
                    "vehicle_id": vehicle_id,
                    "status": response.status_code,
                    "bytes": len(response.content),
                    "duration_ms": round((time.monotonic() - started) * 1000, 1),
                }
            )
            raise DeepalAPIError(
                f"Vehicle model download failed with HTTP {response.status_code}.",
                status_code=response.status_code,
            )

        content = response.content
        if asset.md5:
            actual = hashlib.md5(content).hexdigest()
            if actual.lower() != asset.md5.lower():
                self._emit_exchange(
                    {
                        "ts": datetime.now(UTC).isoformat(),
                        "kind": "rest",
                        "event": "response",
                        "client": "intl",
                        "method": "GET",
                        "path": asset.model_url,
                        "url": asset.model_url,
                        "vehicle_id": vehicle_id,
                        "status": response.status_code,
                        "bytes": len(content),
                        "error": "checksum_mismatch",
                        "duration_ms": round(
                            (time.monotonic() - started) * 1000, 1
                        ),
                    }
                )
                raise DeepalAPIError(
                    "Vehicle model archive checksum mismatch: "
                    f"expected {asset.md5}, got {actual}."
                )

        self._emit_exchange(
            {
                "ts": datetime.now(UTC).isoformat(),
                "kind": "rest",
                "event": "response",
                "client": "intl",
                "method": "GET",
                "path": asset.model_url,
                "url": asset.model_url,
                "vehicle_id": vehicle_id,
                "status": response.status_code,
                "bytes": len(content),
                "duration_ms": round((time.monotonic() - started) * 1000, 1),
            }
        )
        return content

    async def get_vehicle_capabilities(
        self, vehicle_id: str, vin: Optional[str] = None
    ) -> Optional[VehicleCapabilities]:
        """Fetch the per-vehicle function configuration, or None when unavailable.

        The app uses this server-side list to decide which controls a vehicle
        supports (seat ventilation, roof, ...). The request body key was not
        recovered from the DEX (the builder is VMP-extracted), so the known
        candidates are tried in order. Any failure is non-fatal: callers fall
        back to their generic behavior.
        """
        candidates: list[dict[str, Any]] = [
            # The Spanish backend answers this body; "carId" is rejected, so
            # it is only a fallback (verified by upstream dec_deepal 2.0.0b3).
            {"vehicleId": vehicle_id},
            {"carId": vehicle_id},
        ]
        if vin:
            candidates.append({"vin": vin})

        for body in candidates:
            try:
                data = await self._request(
                    INTL_GET_FUNCTION_CONFIG, json_data=body, auth_required=True
                )
            except DeepalRateLimitError as exc:
                logger.warning(
                    "Vehicle capabilities request was rate limited; skipping: %s", exc
                )
                return None
            except DeepalAuthError as exc:
                logger.debug("Vehicle capabilities authentication failed: %s", exc)
                return None
            except DeepalAPIError as exc:
                logger.debug(
                    "Vehicle capabilities body %s was rejected: %s",
                    next(iter(body)),
                    exc,
                )
                continue
            except DeepalError as exc:
                logger.debug("Vehicle capabilities unavailable: %s", exc)
                return None

            codes = data.get("confList") if isinstance(data, dict) else None
            if not isinstance(codes, list):
                logger.debug(
                    "Vehicle capabilities response carried no confList: %r", data
                )
                return None
            logger.debug(
                "Vehicle capabilities accepted body key=%s", next(iter(body))
            )
            return VehicleCapabilities.from_codes([str(code) for code in codes])

        logger.debug(
            "Vehicle capabilities were rejected for every known body candidate"
        )
        return None

    async def get_digital_key_support(
        self, vehicle_id: Optional[str] = None
    ) -> Optional[DigitalKeySupport]:
        """Check whether the phone is supported for the digital key.

        Read-only: queries the SDA gateway ``query-supported-featured`` endpoint
        with the account user id and the phone identity. The European gateway
        answers with a ``flag`` that selects the key scheme: 0 the Changan (CA)
        BLE key, 1 the ICCE (Huawei wallet) key, 2 the Honor key. Never raises
        for an unavailable feature; a missing user id or any request failure
        logs and returns ``None``.
        """
        if not self.user_id:
            logger.debug("Digital key support requires the account user id.")
            return None

        payload: dict[str, Any] = {
            "userId": self.user_id,
            "deviceInfo": {
                "terminal": self.device_type,
                "romVersion": self.os_version,
                "clientVersion": self.app_version,
            },
        }
        if vehicle_id:
            payload["carId"] = vehicle_id

        try:
            data = await self._request(
                INTL_CA_GET_DIGITAL_KEY_SUPPORT,
                json_data=payload,
                auth_required=True,
                base_url=self.sda_base_url,
            )
        except DeepalRateLimitError as exc:
            logger.warning(
                "Digital key support request was rate limited; skipping: %s", exc
            )
            return None
        except DeepalAuthError as exc:
            logger.debug("Digital key support authentication failed: %s", exc)
            return None
        except DeepalError as exc:
            logger.debug("Digital key support unavailable: %s", exc)
            return None

        flag = data.get("flag") if isinstance(data, dict) else None
        if not isinstance(flag, int) or isinstance(flag, bool):
            logger.debug("Digital key support response carried no flag: %r", data)
            return None
        logger.debug("Digital key support flag=%s", flag)
        return DigitalKeySupport.from_flag(flag, raw=data)

    async def get_vehicle_authorizations(
        self, car_id: str
    ) -> Optional[VehicleAuthorizations]:
        """Fetch the per-vehicle function authorization list, or None.

        Read-only: the list tells which functions the signed-in account may use
        on the vehicle (``DigitalKey`` among them). The endpoint is not deployed
        in every region — the European SDA gateway answers 404 — in which case
        the SDK returns no authorization. The request body key was not recovered
        from the DEX (the builder is VMP-extracted), so the known candidates are
        tried in order. Any failure is non-fatal: callers fall back to their
        generic behavior.
        """
        candidates: list[dict[str, Any]] = [
            {"carId": car_id},
            {"vehicleId": car_id},
            {"userId": self.user_id, "carId": car_id},
            {"carId": car_id, "userId": self.user_id},
        ]

        empty_result: Optional[VehicleAuthorizations] = None
        for body in candidates:
            try:
                data = await self._request(
                    INTL_CA_GET_CAR_AUTH_LIST,
                    json_data=body,
                    auth_required=True,
                    base_url=self.sda_base_url,
                )
            except DeepalRateLimitError as exc:
                logger.warning(
                    "Vehicle authorization request was rate limited; skipping: %s",
                    exc,
                )
                return None
            except DeepalAuthError as exc:
                logger.debug("Vehicle authorization authentication failed: %s", exc)
                return None
            except DeepalAPIError as exc:
                logger.debug(
                    "Vehicle authorization body %s was rejected: %s",
                    next(iter(body)),
                    exc,
                )
                continue
            except DeepalError as exc:
                logger.debug("Vehicle authorizations unavailable: %s", exc)
                return None

            result = VehicleAuthorizations.from_payload(data)
            if result.raw_codes:
                logger.debug(
                    "Vehicle authorization accepted body key=%s", next(iter(body))
                )
                return result
            empty_result = result

        if empty_result is not None:
            logger.debug("Vehicle authorization response carried no function codes")
        return empty_result

    async def get_vehicle_condition(
        self, vehicle_id: str, vin: Optional[str] = None
    ) -> VehicleCondition:
        """Fetch the telemetry condition of an international vehicle."""
        criteria = {
            "seat": "1",
            "door": "1",
            "hvac": "1",
            "charge": "1",
            "lamp": "1",
            "window": "1",
            "tire": "1",
            "vehicleStatus": "1",
            "fuel": "1",
        }
        if self.location_enabled:
            criteria["location"] = "1"
        raw = await self._request(
            INTL_GET_VEHICLE_CONDITION,
            json_data={
                "vechileCriteria": criteria,
                "vehicleId": vehicle_id,
            },
            auth_required=True,
        )
        if not isinstance(raw, dict):
            raw = {}

        return self.parse_condition(raw, vehicle_id, vin=vin)

    def parse_condition(
        self, raw: dict[str, Any], vehicle_id: str, vin: Optional[str] = None
    ) -> VehicleCondition:
        """Map a raw condition payload into the shared vehicle model."""
        status = raw.get("vehicleStatus") or {}
        door = raw.get("door") or {}
        hvac = raw.get("hvac") or {}
        charge = raw.get("charge") or {}
        fuel = raw.get("fuel") or {}
        tire = raw.get("tire") or {}
        seat = raw.get("seat") or {}
        window = raw.get("window") or {}
        lamp = raw.get("lamp") or {}
        warnings = raw.get("warningLights") or {}
        window_openings = raw.get("windowOpenings") or {}
        charge_plan = _path_value(charge, ("chargePlanList", 0)) or {}

        def _tenths(value: Any) -> Optional[float]:
            parsed = _as_float(value)
            return parsed / 10 if parsed is not None else None

        def _level(value: Any) -> Optional[int]:
            """Return a seat level within 0-3, or None when it is unknown.

            Missing values and out-of-range values (the MQTT sleep sentinel 6
            included) mean the real level is unknown, not a level; callers keep
            the last valid value instead of exposing a made-up one.
            """
            level = _as_int(value)
            if level is None or not 0 <= level <= 3:
                return None
            return level

        charge_status = charge.get("chargeStatus")
        if charge_status not in (None, 0):
            charger_connected = True
        else:
            charger_connected = _gun_connected(charge.get("chargeConStatus"))

        doors = door.get("doors") or []

        def door_open(index: int) -> bool:
            value = _path_value(doors, (index,))
            return value not in (None, 0)

        driver_lock = door.get("driverLock")
        passenger_lock = door.get("passengerLock")
        if driver_lock is not None:
            locked = driver_lock == 0
        elif passenger_lock is not None:
            locked = passenger_lock == 0
        else:
            locked = True

        target_temp = _as_float(hvac.get("remoteTemp"))

        remaining_charge_time = _as_int(charge.get("remainChargeTime"))
        if remaining_charge_time == CHARGE_TIME_SENTINEL:
            remaining_charge_time = None

        battery = BatteryCondition(
            soc_percentage=_as_int(status.get("soc")),
            remaining_range_km=_as_int(status.get("drvMileage")),
            charging_status=str(charge_status) if charge_status is not None else None,
            charger_connected=charger_connected,
            dc_gun_connected=_gun_connected(charge.get("dcChargeGunConnectStatus")),
            ac_gun_connected=_gun_connected_optional(
                charge.get("acChargeGunConnectStatus")
            ),
            charge_current_a=clean_charge_current_magnitude(
                charge.get("chargeCurrent"), "charge.chargeCurrent"
            ),
            ac_charge_current_a=clean_charge_current_magnitude(
                charge.get("acChargeCurrent"), "charge.acChargeCurrent"
            ),
            dc_charge_current_a=clean_charge_current_magnitude(
                charge.get("dcChargeCurrent"), "charge.dcChargeCurrent"
            ),
            remaining_charge_time_min=remaining_charge_time,
            charge_limit_percent=_as_int(charge.get("maxSocPercent")),
            charge_schedule_enabled=(
                charge_plan.get("startSwitch") == 1
                and charge_plan.get("endSwitch") == 1
            ),
            charge_schedule_start=(
                str(charge_plan["startTime"])
                if charge_plan.get("startTime") is not None
                else None
            ),
            charge_schedule_end=(
                str(charge_plan["endTime"])
                if charge_plan.get("endTime") is not None
                else None
            ),
            charge_plan_id=(
                str(charge_plan["planId"])
                if charge_plan.get("planId") is not None
                else None
            ),
            charge_plan_type=_as_int(charge_plan.get("planType")),
            charge_plan_time_format=_as_int(charge_plan.get("timeFormat")),
            charge_plan_time_zone=(
                str(charge_plan["timeZone"])
                if charge_plan.get("timeZone") is not None
                else None
            ),
        )

        fuel_condition = FuelCondition(
            level_percent=_as_int(fuel.get("leftPercent")),
            volume_l=_as_float(fuel.get("leftVolume")),
            tank_capacity_l=_as_float(fuel.get("tankVolume")),
            remaining_range_km=_fuel_range_km(fuel),
            temperature_c=_as_float(fuel.get("temperature")),
        )

        doors_condition = DoorsCondition(
            locked=locked,
            driver_locked=driver_lock == 0 if driver_lock is not None else None,
            passenger_locked=(
                passenger_lock == 0 if passenger_lock is not None else None
            ),
            driver_door_open=door_open(0),
            passenger_door_open=door_open(1),
            rear_left_door_open=door_open(2),
            rear_right_door_open=door_open(3),
            trunk_open=door.get("trunk") not in (None, 0),
            hood_open=door.get("hood") not in (None, 0),
        )

        window_list = window.get("windows") or []

        def window_open(index: int) -> bool:
            value = _path_value(window_list, (index,))
            return value not in (None, 0)

        windows_condition = WindowsCondition(
            front_left_open=window_open(0),
            front_right_open=window_open(1),
            rear_left_open=window_open(2),
            rear_right_open=window_open(3),
        )

        def seat_status(position: str) -> SeatStatus:
            data = seat.get(position) or {}
            heating = data.get("heatStatus")
            if heating is None:
                heating = data.get("level")
            return SeatStatus(
                heating_level=_level(heating),
                ventilation_level=_level(data.get("ventStatus")),
            )

        seats_condition = SeatsCondition(
            front_left=seat_status("leftFront"),
            front_right=seat_status("rightFront"),
            rear_left=seat_status("leftBack"),
            rear_right=seat_status("rightBack"),
        )

        def tire_status(position: str) -> TireStatus:
            data = tire.get(position) or {}
            pressure = _as_float(data.get("pressure"))
            status_value = data.get("status")
            return TireStatus(
                pressure_bar=round(pressure / 100, 2) if pressure is not None else None,
                temperature_c=_as_float(data.get("temperature")),
                alarm=bool(data.get("alarm"))
                or status_value not in (None, 0, "0"),
            )

        tires_condition = TiresCondition(
            front_left=tire_status("leftFront"),
            front_right=tire_status("rightFront"),
            rear_left=tire_status("leftBack"),
            rear_right=tire_status("rightBack"),
        )

        steering_heater = _as_int(status.get("steeringWheelHeater"))
        defrost = _as_int(hvac.get("defrostStatus"))
        ac_status = hvac.get("acStatus")

        climate = ClimateCondition(
            power_on=(
                ac_status not in (None, 0) if ac_status is not None else None
            ),
            target_temperature_c=target_temp / 10 if target_temp is not None else None,
            inside_temperature_c=_tenths(hvac.get("insideTemp")),
            outside_temperature_c=_tenths(hvac.get("outsideTemp")),
            humidity=_humidity_percent(hvac.get("insideHumidity")),
            inside_pm25=_as_float(hvac.get("insidePm25")),
            air_quality_level=_as_int(hvac.get("insideAirQualityLevel")),
            defrost_on=None if defrost is None else defrost != 0,
            fan_level=_as_int(hvac.get("fanLevel")),
            steering_wheel_heater_on=(
                None if steering_heater is None else steering_heater != 0
            ),
            steering_wheel_heater_level=_as_int(status.get("steeringWheelHeaterLevel")),
        )

        lamps = LampsCondition(
            high_beam=lamp.get("highBeam") not in (None, 0),
            low_beam=lamp.get("lowBeam") not in (None, 0),
            position_lamp=lamp.get("positionLamp") not in (None, 0),
            front_fog=lamp.get("frontFoglamp") not in (None, 0),
            rear_fog=lamp.get("rearFoglamp") not in (None, 0),
            left_turn=lamp.get("leftTurn") not in (None, 0),
            right_turn=lamp.get("rightTurn") not in (None, 0),
        )

        last_updated = _to_millis(
            raw.get("lastUpdatedAt")
            if raw.get("lastUpdatedAt") is not None
            else status.get("lastUpdatedAt")
        )

        power_status = _as_int(status.get("powerStatus"))
        engine_status = _as_int(status.get("engineSts"))
        # An electric vehicle reports engineSts 0 while driving, so the
        # ignition state comes from the power status when it is reported
        # (0 = off, anything else = on) and falls back to engineSts otherwise.
        engine_on = (
            power_status not in (None, 0)
            if power_status is not None
            else engine_status not in (None, 0)
        )

        location = find_location(raw)

        warnings_condition = WarningLightsCondition(
            battery_12v=_as_bool(warnings.get("battery12v")),
            tpms=_as_bool(warnings.get("tpms")),
            abs=_as_bool(warnings.get("abs")),
            airbag=_as_bool(warnings.get("airbag")),
            brake_fluid=_as_bool(warnings.get("brakeFluid")),
            brake=_as_bool(warnings.get("brake")),
            eps=_as_bool(warnings.get("eps")),
            power_limit=_as_bool(warnings.get("powerLimit")),
            power_system=_as_bool(warnings.get("powerSystem")),
            traction_battery_low=_as_bool(
                warnings.get("tractionBatteryLow")
            ),
            coolant_temperature=_as_bool(
                warnings.get("coolantTemperature")
            ),
        )
        if power_status == 0:
            # A sleeping car woken for a refresh reports the warning bits as 1
            # on a healthy vehicle. The gate is applied here, next to the
            # warning mapping, so the international REST and SDA conditions
            # follow the same rule as the S05 MQTT normalization.
            warnings_condition = WarningLightsCondition()

        return VehicleCondition(
            car_id=vehicle_id,
            vin=raw.get("vin") or vin or "",
            latitude=location[0] if location is not None else None,
            longitude=location[1] if location is not None else None,
            total_odometer_km=_as_float(status.get("totalMileage")),
            mileage_yesterday_km=_as_float(status.get("totalMeterYesterday")),
            trip_mileage_km=_as_float(status.get("igniteCumulativeMileage")),
            speed_kmh=_as_float(status.get("speed")),
            gear=(
                str(status["gearSignal"])
                if status.get("gearSignal") is not None
                else None
            ),
            epb_status=_as_int(status.get("epbSts")),
            power_status=power_status,
            vehicle_status=_as_int(status.get("status")),
            engine_on=engine_on,
            connected=(
                status.get("connectStatus") == 1
                if status.get("connectStatus") is not None
                else None
            ),
            battery=battery,
            fuel=fuel_condition,
            doors=doors_condition,
            windows=windows_condition,
            seats=seats_condition,
            climate=climate,
            tires=tires_condition,
            lamps=lamps,
            warnings=warnings_condition,
            key_battery_low=_as_bool(raw.get("keyBatteryLow")),
            air_recirculation=_as_bool(raw.get("airRecirculation")),
            window_openings=WindowOpeningsCondition(
                front_left=_as_int(window_openings.get("frontLeft")),
                front_right=_as_int(window_openings.get("frontRight")),
                rear_left=_as_int(window_openings.get("rearLeft")),
                rear_right=_as_int(window_openings.get("rearRight")),
            ),
            last_updated_timestamp=last_updated // 1000 if last_updated is not None else None,
            raw_data=raw,
        )

    MQTT_PROTOCOL_TYPES = frozenset({"MQTT", "SDA-MQTT"})

    @staticmethod
    def is_mqtt_vehicle(vehicle: Vehicle) -> bool:
        """Return whether the vehicle reports telemetry over MQTT.

        Both the legacy ``MQTT`` protocol (for example the S05) and the SDA
        ``SDA-MQTT`` protocol (for example the E07) use the CA broker; only the
        condition service differs.
        """
        return (vehicle.protocol_type or "").upper() in DeepalIntlClient.MQTT_PROTOCOL_TYPES

    @staticmethod
    def is_sda_mqtt_vehicle(vehicle: Vehicle) -> bool:
        """Return whether the vehicle uses the SDA condition service."""
        return (vehicle.protocol_type or "").upper() == "SDA-MQTT"

    async def get_mqtt_config(
        self, vehicle_id: str, force: bool = False
    ) -> dict[str, Any]:
        """Return the CA gateway MQTT connection configuration for a vehicle.

        The configuration is per vehicle and practically static, so it is
        reused within ``mqtt_config_ttl`` (660 seconds by default, about two
        default poll cycles) instead of fetched for every session: the wake
        report wait and its retries bootstrap once. ``force`` bypasses the
        cache, and a failed fetch never leaves a stale value behind.
        """
        cached = self._mqtt_configs.get(vehicle_id)
        if not force and cached is not None and time.monotonic() < cached[1]:
            return cached[0]
        self._mqtt_configs.pop(vehicle_id, None)
        payload = {
            "deviceId": self.device_id,
            "carId": vehicle_id,
            "deviceType": 1,
            "confTimestamp": 0,
            "deviceTimestamp": str(int(time.time() * 1000)),
        }
        try:
            data = await self._request(
                INTL_CA_GET_CONN_CONF,
                json_data=payload,
                auth_required=True,
                base_url=self.ca_base_url,
            )
        except DeepalRateLimitError:
            raise
        except (DeepalAPIError, DeepalSessionInvalidated) as exc:
            if not self.mqtt_config_fallback:
                raise
            logger.warning(
                "getConnConf failed (%s); retrying with appGetCarConfFunc", exc
            )
            data = await self._request(
                INTL_CA_GET_CAR_CONF_FUNC,
                json_data=payload,
                auth_required=True,
                base_url=self.ca_base_url,
            )
        if not isinstance(data, dict):
            raise DeepalAPIError("Unexpected S05 MQTT configuration response.")
        self._mqtt_configs[vehicle_id] = (
            data,
            time.monotonic() + self.mqtt_config_ttl,
        )
        return data

    def _invalidate_mqtt_token(self) -> None:
        """Drop the cached MQTT auth token (rejected, or the session changed)."""
        self._mqtt_token = None
        self._mqtt_token_expires_at = 0.0

    def _invalidate_mqtt_config(self) -> None:
        """Drop the cached CA connection configurations (rejected bootstrap)."""
        self._mqtt_configs.clear()

    async def get_mqtt_token(self, force: bool = False) -> str:
        """Exchange the account user id for a CA MQTT auth token.

        The token is account level and is reused within ``mqtt_token_ttl`` (one
        minute by default), so a refresh cycle with several vehicles asks the CA
        gateway once instead of once per MQTT session. ``force`` bypasses the
        cache after a rejection, and a failed fetch never leaves a stale value
        behind.

        The CA broker only accepts tokens issued by the CA
        ``getAuthTokenByUserId`` endpoint. The SDA ``/app-apigw/vot-auth`` route
        authenticates a different gateway and broker, so it is not a fallback
        here; a failure propagates unchanged (with its gateway code when
        present) so the coordinator can refresh the session and retry.
        """
        if not self.user_id:
            raise DeepalAPIError(
                "S05 MQTT telemetry requires the account user id; log in again."
            )
        if (
            not force
            and self._mqtt_token is not None
            and time.monotonic() < self._mqtt_token_expires_at
        ):
            return self._mqtt_token
        self._invalidate_mqtt_token()
        data = await self._request(
            INTL_CA_GET_AUTH_TOKEN,
            json_data={"userId": self.user_id},
            auth_required=True,
            base_url=self.ca_base_url,
        )
        if not isinstance(data, dict) or not data.get("authToken"):
            raise DeepalAPIError("S05 MQTT auth response did not include authToken.")
        token = str(data["authToken"])
        self._mqtt_token = token
        self._mqtt_token_expires_at = time.monotonic() + self.mqtt_token_ttl
        return token

    async def get_sda_broker_config(self, vehicle_id: str) -> SdaBrokerConfig:
        """Fetch the SDA broker connection configuration for a vehicle.

        The app calls the ``sda-app-control`` variant on the SDA gateway (the
        one the probe verified live on the E07, issue #2); the ``vot-app-conf``
        alternate recovered from the 1.12.0 DEX stays defined in ``endpoints``
        until the capture confirms which one the app uses.
        """
        data = await self._request(
            INTL_SDA_GET_MQTT_SERVER_CONFIG,
            auth_required=True,
            base_url=self.sda_base_url,
            method="GET",
            query={"carId": vehicle_id},
        )
        return parse_sda_broker_config(data)

    async def get_sda_auth_token(self) -> str:
        """Fetch the SDA ``vot-auth`` token the broker accepts as password.

        The official app calls this endpoint as a GET without parameters and
        the account identity travels in the session headers (issue #2 trace);
        the gateway envelope carries ``authToken`` flat or nested.
        """
        data = await self._request(
            INTL_SDA_GET_AUTH_TOKEN,
            auth_required=True,
            base_url=self.sda_base_url,
            method="GET",
        )
        token = _first_auth_token(data)
        if not token:
            raise DeepalAuthError("SDA auth response did not include an authToken.")
        return token

    async def _sda_device_ids(self, vehicle_id: str) -> tuple[str, ...]:
        """Collect the car's MQTT device DID candidates for an SDA session.

        The SDA broker configuration carries no device id, so the candidates
        come from the CA connection config and the function tree — the same
        sources the probe used on the E07 (issue #2). Each source is optional:
        a missing one only removes candidates.
        """
        candidates: list[str] = []
        config: Optional[Mapping[str, Any]] = None
        try:
            config = await self.get_mqtt_config(vehicle_id)
        except DeepalError:
            config = None
        if isinstance(config, Mapping):
            topics = resolve_mqtt_topics(config, None)
            for did in (topics.device_did, topics.login_did):
                if did and did not in candidates:
                    candidates.append(did)
            for did in device_id_candidates(config):
                if did not in candidates:
                    candidates.append(did)
        tree: Optional[Mapping[str, Any]] = None
        try:
            tree = await self.get_car_function_config(vehicle_id)
        except DeepalError:
            tree = None
        for did in device_id_candidates(tree or {}):
            if did not in candidates:
                candidates.append(did)
        return tuple(candidates)

    async def open_sda_session(
        self,
        vehicle_id: str,
        *,
        device_ids: Optional[Sequence[str]] = None,
        topics: Optional[Sequence[str]] = None,
        seconds: float = 10.0,
        login: bool = False,
    ) -> SdaSessionResult:
        """Open a read-only session on the SDA broker for an SDA-MQTT vehicle.

        Resolves the broker configuration and the ``vot-auth`` token, then
        connects with the app's confirmed ``authType 2`` identity
        (``clientId``/``username`` = a device DID, password = the token), trying
        the known DIDs in order and keeping the accepted one. Subscriptions
        default to the event and login topics the broker configuration and the
        CA configuration describe. No command is ever published; ``login`` opts
        into the ``client/loginout`` exchange that opens the app's session. A
        broker rejection raises a typed error so the integration can
        reauthenticate.
        """
        config = await self.get_sda_broker_config(vehicle_id)
        if not config.usable or not config.host or not config.port:
            raise DeepalAPIError(
                "SDA broker configuration did not include host and port."
            )
        token = await self.get_sda_auth_token()
        candidates = (
            tuple(device_ids)
            if device_ids
            else await self._sda_device_ids(vehicle_id)
        )
        if not candidates:
            raise DeepalAPIError(
                "SDA session needs the car's device DID; none was found in the "
                "CA configuration or the function tree."
            )
        subscriptions = (
            tuple(topics)
            if topics is not None
            else sda_session_topics(config.payload, candidates[0], car_id=vehicle_id)
        )
        result = await sda_broker_session(
            config.host,
            config.port,
            device_ids=candidates,
            password=token,
            topics=subscriptions,
            seconds=seconds,
            timeout=MQTT_SOCKET_TIMEOUT,
            keepalive=self.mqtt_keepalive,
            ssl_context=await asyncio.to_thread(self._mqtt_ssl_context),
            login=login,
        )
        if result.connected:
            return result
        if result.connack_reason is not None:
            reason = MQTT_CONNACK_REASONS.get(
                result.connack_reason, "unknown reason code"
            )
            raise DeepalAuthError(
                "SDA broker rejected the session: "
                f"reason code {result.connack_reason} ({reason}); the account "
                "session or the device DID may be stale."
            )
        raise DeepalConnectionError(
            "Could not reach the SDA broker for the resolved device DIDs."
        )

    async def s05_mqtt_condition(
        self, vehicle_id: str, vin: Optional[str] = None, *, sda: bool = False
    ) -> VehicleCondition:
        """Fetch a live condition snapshot over MQTT.

        ``sda`` selects the SDA/VOT condition service (``Get_CarCondition``)
        used by ``SDA-MQTT`` vehicles; the legacy ``car_condition`` request
        remains the default and the last fallback probe. Sessions are
        serialized per client because all vehicles of an account share the
        broker client identity.
        """
        async with self._mqtt_lock:
            return await self._s05_mqtt_condition_locked(
                vehicle_id, vin=vin, sda=sda
            )

    async def _s05_mqtt_condition_locked(
        self, vehicle_id: str, vin: Optional[str] = None, *, sda: bool = False
    ) -> VehicleCondition:
        config = await self.get_mqtt_config(vehicle_id)
        if sda:
            plan = sda_condition_plan(config)
            if plan.device_did is None and not plan.property_codes:
                tree = await self.get_car_function_config(vehicle_id)
                if tree:
                    config = {**config, "functionConfig": tree}
        token = await self.get_mqtt_token()
        try:
            try:
                result = await self._read_s05_params(
                    config, token, sda=sda, vehicle_id=vehicle_id
                )
            except (asyncio.TimeoutError, EOFError, OSError, ssl.SSLError) as exc:
                raise DeepalAPIError(f"S05 MQTT telemetry failed: {exc}") from exc
        except Exception as exc:
            self._emit_mqtt(
                "error",
                vehicle_id=vehicle_id,
                stage="condition",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise
        self._emit_mqtt(
            "result",
            vehicle_id=vehicle_id,
            stage="condition",
            source=result.source,
            variants=result.variants,
            plan=result.plan.as_dict() if result.plan else None,
            param_count=len(result.params),
        )
        self.last_mqtt_exchange = result
        if not result.params:
            raise DeepalAPIError("S05 MQTT telemetry did not return vehicle condition.")
        condition = self.parse_condition(
            normalize_s05_params(result.params), vehicle_id, vin=vin
        )
        location = find_location(result.params)
        if location is not None:
            condition.latitude, condition.longitude = location
        condition.mqtt_raw_data = result.params
        condition.condition_source = result.source
        condition.mqtt_variants = result.variants or None
        condition.sda_plan = result.plan.as_dict() if result.plan else None
        return condition

    async def get_sda_vehicle_condition(
        self, vehicle_id: str, vin: Optional[str] = None
    ) -> VehicleCondition:
        """Fetch the SDA condition over REST for an ``SDA-MQTT`` vehicle.

        The endpoint lives on the SDA gateway (``sda_base_url``), not on the
        international host. The official app calls it as a GET with the
        snake_case ``car_id`` query parameter and the login token without the
        ``Bearer`` prefix; the camelCase keys stay as fallbacks for other
        regions. The flat SDA response is normalized with the SDA mapping.
        """
        attempts: tuple[
            tuple[str, Optional[dict[str, Any]], Optional[dict[str, Any]]], ...
        ] = (
            ("GET", None, {"car_id": vehicle_id}),
            ("GET", None, {"carId": vehicle_id}),
            ("GET", None, {"vehicleId": vehicle_id}),
        )
        last_error: Optional[DeepalAPIError] = None
        for method, body, query in attempts:
            try:
                raw = await self._request(
                    INTL_SDA_GET_CAR_CONDITION,
                    json_data=body,
                    auth_required=True,
                    base_url=self.sda_base_url,
                    method=method,
                    query=query,
                )
            except DeepalAPIError as exc:
                last_error = exc
                continue
            if isinstance(raw, dict) and raw:
                return self._parse_sda_rest_condition(raw, vehicle_id, vin=vin)
        if last_error is not None:
            raise last_error
        raise DeepalAPIError("SDA REST condition did not return vehicle condition.")

    async def get_car_function_config(self, vehicle_id: str) -> dict[str, Any]:
        """Fetch the per-function VOT tree used to build the SDA plan.

        The app reads ``appGetCarConfFunc`` into ``CarFuncBean`` entries and
        derives the condition device and signals from it. The connection
        configuration does not always carry ``carConfigJson`` (the live E07 did
        not), so the tree is fetched explicitly, then from the SDA function
        config endpoints.
        """
        payload = {
            "deviceId": self.device_id,
            "carId": vehicle_id,
            "deviceType": 1,
            "confTimestamp": 0,
            "deviceTimestamp": str(int(time.time() * 1000)),
        }
        attempts: tuple[
            tuple[str, str, Optional[dict[str, Any]], Optional[dict[str, Any]]], ...
        ] = (
            ("POST", INTL_CA_GET_CAR_CONF_FUNC, payload, None),
            ("POST", INTL_SDA_GET_FUNCTION_CONFIG, {"carId": vehicle_id}, None),
            ("POST", INTL_SDA_VOT_FUNCTION_CONFIG, {"carId": vehicle_id}, None),
            ("GET", INTL_SDA_GET_FUNCTION_CONFIG, None, {"carId": vehicle_id}),
            ("GET", INTL_SDA_VOT_FUNCTION_CONFIG, None, {"carId": vehicle_id}),
        )
        for method, path, body, query in attempts:
            base_url = (
                self.ca_base_url
                if path == INTL_CA_GET_CAR_CONF_FUNC
                else self.sda_base_url
            )
            try:
                data = await self._request(
                    path,
                    json_data=body,
                    auth_required=True,
                    base_url=base_url,
                    method=method,
                    query=query,
                )
            except DeepalAPIError as exc:
                logger.debug(
                    "Deepal SDA function config %s %s failed: %s",
                    method,
                    path,
                    exc,
                )
                continue
            if isinstance(data, dict) and data:
                logger.debug(
                    "Deepal SDA function config %s %s returned keys=%s",
                    method,
                    path,
                    sorted(data)[:12],
                )
                return data
            logger.debug(
                "Deepal SDA function config %s %s returned no data", method, path
            )
        logger.debug("Deepal SDA function config was not found in any endpoint")
        return {}

    def _parse_sda_rest_condition(
        self, raw: dict[str, Any], vehicle_id: str, vin: Optional[str] = None
    ) -> VehicleCondition:
        """Map an SDA REST condition payload into the shared vehicle model."""
        payload: dict[str, Any] = raw
        for key in ("data", "params"):
            value = raw.get(key)
            if isinstance(value, dict) and value:
                payload = value
                break
        if any(key in payload for key in ("vehicleStatus", "door", "hvac", "charge")):
            normalized = payload
        elif any(
            key in payload
            for key in (
                "BcuSocDisp",
                "VIUSocDisp",
                "VcuResiMilg",
                "CdcTotMilg",
                "BcuChrgSts",
            )
        ):
            normalized = normalize_sda_params(payload)
        else:
            normalized = normalize_s05_params(payload)
        condition = self.parse_condition(normalized, vehicle_id, vin=vin)
        condition.mqtt_raw_data = payload
        condition.condition_source = "sda-rest"
        location = find_location(payload, normalized)
        if location is not None:
            condition.latitude, condition.longitude = location
        return condition

    @staticmethod
    def _log_s05_discovery(params: dict[str, Any]) -> None:
        """Log the S05 parameters the normalization does not consume yet.

        Debug-only discovery aid: it formats the candidate values only when
        debug logging is enabled and never changes the returned condition.
        """
        if not params or not logger.isEnabledFor(logging.DEBUG):
            return
        charge = {
            key: params[key] for key in S05_CHARGE_DEBUG_KEYS if key in params
        }
        if charge:
            logger.debug(
                "S05 MQTT charge parameters: %s",
                json.dumps(charge, ensure_ascii=False, sort_keys=True, default=str),
            )
        unmapped = unmapped_s05_keys(params)
        if not unmapped:
            return
        logger.debug(
            "S05 MQTT unmapped parameters: %s",
            json.dumps(
                {
                    key: "[redacted]" if is_sensitive_key(key) else params[key]
                    for key in sorted(unmapped)
                },
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ),
        )

    def _mqtt_ssl_context(self) -> ssl.SSLContext:
        """Build the TLS context, honouring the explicit insecure override."""
        if self.mqtt_tls_insecure:
            logger.warning(
                "Deepal MQTT TLS verification is disabled (mqtt_tls_insecure=True); "
                "certificate and hostname checks are skipped."
            )
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            return context
        return ssl.create_default_context()

    def _mqtt_basic_identifiers(
        self, config: dict[str, Any], login_did: str
    ) -> dict[str, Any]:
        """Collect the basic ReqPayLoad identifiers known to this client."""
        info = ((config.get("mqttConnectionInfos") or [None])[0]) or {}
        cluster = ((info.get("clusterInfos") or [None])[0]) or {}
        car_data = info.get("carConfigJson")
        if isinstance(car_data, str) and car_data.strip().startswith("{"):
            try:
                parsed = json.loads(car_data)
            except ValueError:
                parsed = {}
            car_data = parsed if isinstance(parsed, dict) else {}
        if not isinstance(car_data, dict):
            car_data = {}
        sources = (info, cluster, car_data, config)

        def first_value(*keys: str) -> Optional[str]:
            for source in sources:
                for key in keys:
                    value = source.get(key)
                    if value is not None and str(value):
                        return str(value)
            return None

        return basic_identifiers(
            ruid=login_did,
            uid=self.user_id or first_value("userId", "uid"),
            vin=first_value("vin"),
            cid=first_value("carId", "car_id", "cid"),
        )

    async def _open_s05_mqtt(
        self,
        config: dict[str, Any],
        token: str,
        *,
        sda: bool = False,
        vehicle_id: Optional[str] = None,
    ) -> tuple[
        asyncio.StreamReader,
        asyncio.StreamWriter,
        MqttTopics,
        dict[str, Any],
        Optional[str],
        Optional[SdaConditionPlan],
    ]:
        """Connect, subscribe and log in; return the open session and login result.

        The caller owns the returned writer and must close it with
        :meth:`_close_s05_mqtt`.
        """
        info = ((config.get("mqttConnectionInfos") or [None])[0]) or {}
        cluster = ((info.get("clusterInfos") or [None])[0]) or {}
        host = str(cluster.get("brokerUrl", "")).replace("ssl://", "")
        port = int(cluster.get("brokerPort") or 8883)
        resolved = resolve_mqtt_topics(config, fallback_did=self.mqtt_client_id)
        login_topic = resolved.login_publish
        login_did = resolved.login_did
        properties_topic = resolved.properties_publish
        device_did = resolved.device_did

        if not host or not login_topic or not login_did or not device_did:
            raise DeepalAPIError(
                "S05 MQTT configuration did not include required topics."
            )

        plan = sda_condition_plan(config) if sda else None
        sda_did = (plan.device_did if plan and plan.device_did else None) or device_did
        sda_topic = topic_with_device(properties_topic, sda_did) or properties_topic

        client_id, username = config_mqtt_identity(
            config,
            login_did,
            client_id=self.mqtt_client_id,
            username=self.mqtt_username,
        )
        basic_info = self._mqtt_basic_identifiers(config, login_did)
        self._emit_mqtt(
            "session_open",
            vehicle_id=vehicle_id,
            source="sda" if sda else "s05",
            host=host,
            port=port,
            topics={
                "login": login_topic,
                "properties": properties_topic,
                "properties_set": resolved.properties_set_publish,
                "sda": sda_topic,
                "subscriptions": list(resolved.subscriptions),
            },
        )
        context = await asyncio.to_thread(self._mqtt_ssl_context)
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=context, server_hostname=host),
            timeout=MQTT_SOCKET_TIMEOUT,
        )
        try:
            writer.write(
                build_connect_packet(
                    client_id,
                    username,
                    token,
                    keepalive=self.mqtt_keepalive,
                    clean_start=self.mqtt_clean_start,
                )
            )
            await writer.drain()
            first, body = await asyncio.wait_for(
                read_packet(reader), timeout=MQTT_SOCKET_TIMEOUT
            )
            _session_present, reason_code = parse_connack(first, body)
            if reason_code != 0:
                reason = MQTT_CONNACK_REASONS.get(reason_code, "unknown reason code")
                # A rejected token must not survive the reuse window; force a
                # fresh fetch on the next attempt. The cached connection
                # configuration is dropped too: the rejection may come from a
                # stale broker/topic set.
                self._invalidate_mqtt_token()
                self._invalidate_mqtt_config()
                self._emit_mqtt(
                    "error",
                    vehicle_id=vehicle_id,
                    stage="connack",
                    reason_code=reason_code,
                    reason=reason,
                )
                raise DeepalAPIError(
                    "S05 MQTT broker rejected connection: "
                    f"reason code {reason_code} ({reason})"
                )

            subscriptions = set(resolved.subscriptions)
            if sda and sda_topic and sda_topic != properties_topic:
                sda_response = (
                    sda_topic[:-4] + "/res"
                    if sda_topic.endswith("/req")
                    else sda_topic
                )
                subscriptions.add(sda_response)
            writer.write(build_subscribe_packet(1, sorted(subscriptions)))
            await writer.drain()
            first, body = await asyncio.wait_for(
                read_packet(reader), timeout=MQTT_SOCKET_TIMEOUT
            )
            packet_id, reasons = parse_suback(first, body)
            if packet_id != 1 or not reasons or any(
                reason >= 0x80 for reason in reasons
            ):
                self._emit_mqtt(
                    "error",
                    vehicle_id=vehicle_id,
                    stage="suback",
                    packet_id=packet_id,
                    reasons=reasons,
                )
                raise DeepalAPIError(
                    "S05 MQTT broker did not acknowledge the subscription."
                )

            login_req_id = new_request_id(login_did)
            login_payload = login_request_payload(
                login_did, login_req_id, basic_info=basic_info
            )
            self._emit_mqtt(
                "publish",
                vehicle_id=vehicle_id,
                stage="login",
                topic=login_topic,
                payload=login_payload,
                services=[
                    {
                        "service_code": "login",
                        "params": {"encryptEnable": 1, "zipType": "gzip"},
                    }
                ],
                request_id=login_req_id,
            )
            writer.write(build_publish_packet(login_topic, login_payload))
            await writer.drain()

            secret_key: Optional[str] = None
            loop = asyncio.get_running_loop()
            deadline = loop.time() + MQTT_EXCHANGE_TIMEOUT
            while loop.time() < deadline and secret_key is None:
                try:
                    first, body = await read_packet_with_keepalive(
                        reader,
                        writer,
                        max(0.05, deadline - loop.time()),
                        self.mqtt_keepalive,
                    )
                except asyncio.TimeoutError:
                    break
                if first >> 4 != 3:
                    continue
                try:
                    topic, payload, packet_id = parse_publish(first, body)
                except ValueError as err:
                    logger.debug(
                        "Deepal MQTT: skipping a malformed PUBLISH packet (%s)", err
                    )
                    continue
                if packet_id is not None:
                    writer.write(build_puback_packet(packet_id))
                    await writer.drain()
                received_secret = secret_from_login_payload(payload)
                self._emit_mqtt(
                    "receive",
                    vehicle_id=vehicle_id,
                    stage="login",
                    topic=topic,
                    payload=payload,
                    request_id=payload.get("r"),
                    secret_received=bool(received_secret),
                )
                secret_key = received_secret
            if secret_key is None:
                self._emit_mqtt(
                    "timeout",
                    vehicle_id=vehicle_id,
                    stage="login",
                )
        except BaseException:
            await self._close_s05_mqtt(writer, vehicle_id=vehicle_id)
            raise
        return reader, writer, resolved, basic_info, secret_key, plan

    async def _close_s05_mqtt(
        self, writer: asyncio.StreamWriter, *, vehicle_id: Optional[str] = None
    ) -> None:
        """Send DISCONNECT and close the one-shot MQTT session."""
        self._emit_mqtt("session_close", vehicle_id=vehicle_id)
        try:
            writer.write(build_disconnect_packet())
            await writer.drain()
        except (ConnectionError, OSError, ssl.SSLError):
            pass
        writer.close()
        try:
            await writer.wait_closed()
        except (ConnectionError, TimeoutError, ssl.SSLError):
            pass

    async def _read_s05_params(
        self,
        config: dict[str, Any],
        token: str,
        *,
        sda: bool = False,
        vehicle_id: Optional[str] = None,
    ) -> MqttExchangeResult:
        """Run one MQTT 5.0 login + condition exchange and return the raw parameters."""
        (
            reader,
            writer,
            resolved,
            basic_info,
            secret_key,
            plan,
        ) = await self._open_s05_mqtt(
            config, token, sda=sda, vehicle_id=vehicle_id
        )
        try:
            properties_topic = resolved.properties_publish
            device_did = resolved.device_did
            login_did = resolved.login_did or device_did
            sda_did = (
                (plan.device_did if plan and plan.device_did else None) or device_did
            )
            sda_topic = topic_with_device(properties_topic, sda_did) or properties_topic
            if not properties_topic or not device_did or not secret_key:
                return MqttExchangeResult(params={}, plan=plan)

            partial: dict[str, Any] = {}
            variants: dict[str, dict[str, Any]] = {}
            source: Optional[str] = None
            probe_labels: dict[str, str] = {}
            if sda:
                probes: tuple[tuple[str, Optional[tuple[str, ...]]], ...] = (
                    ("sda-mqtt", None),
                )
                if plan and plan.property_codes:
                    probes += (("sda-mqtt-properties", plan.property_codes),)
                if plan and plan.strategy_codes:
                    probes += (("sda-mqtt-strategies", plan.strategy_codes),)
                probes += (
                    ("sda-mqtt-sections", SDA_CONDITION_SECTIONS),
                    ("legacy-mqtt", None),
                )
            else:
                probes = (("legacy-mqtt", None),)
            probe_index = -1
            probe_deadline: Optional[float] = None
            loop = asyncio.get_running_loop()
            exchange_timeout = self.mqtt_exchange_timeout or MQTT_EXCHANGE_TIMEOUT
            deadline = loop.time() + exchange_timeout

            def publish_probe(index: int) -> None:
                nonlocal probe_deadline
                label, signal_list = probes[index]
                req_id = new_request_id(sda_did or device_did)
                if label.startswith("sda"):
                    services = sda_condition_request_services(
                        signal_list=list(signal_list) if signal_list else None,
                        service_code=(
                            plan.service_code if plan else SDA_CONDITION_SERVICE
                        ),
                        command_code=(
                            plan.command_code if plan else SDA_CONDITION_COMMAND
                        ),
                        strategy_code=(
                            plan.strategy_codes[0]
                            if plan and plan.strategy_codes
                            else None
                        ),
                        strategy_id=(
                            plan.strategy_ids[0]
                            if plan and plan.strategy_ids
                            else None
                        ),
                    )
                    request = sda_condition_request_payload(
                        sda_did or device_did,
                        login_did,
                        secret_key,
                        req_id,
                        basic_info=basic_info,
                        signal_list=list(signal_list) if signal_list else None,
                        service_code=(
                            plan.service_code if plan else SDA_CONDITION_SERVICE
                        ),
                        command_code=(
                            plan.command_code if plan else SDA_CONDITION_COMMAND
                        ),
                        strategy_code=(
                            plan.strategy_codes[0]
                            if plan and plan.strategy_codes
                            else None
                        ),
                        strategy_id=(
                            plan.strategy_ids[0]
                            if plan and plan.strategy_ids
                            else None
                        ),
                    )
                    topic = sda_topic or properties_topic
                else:
                    services = condition_request_services()
                    request = condition_request_payload(
                        device_did,
                        login_did,
                        secret_key,
                        req_id,
                        basic_info=basic_info,
                    )
                    topic = properties_topic
                probe_labels[req_id] = label
                probe_deadline = loop.time() + self.mqtt_sda_probe_grace
                self._emit_mqtt(
                    "publish",
                    vehicle_id=vehicle_id,
                    stage="condition",
                    source=label,
                    topic=topic,
                    payload=request,
                    services=services,
                    request_id=req_id,
                )
                writer.write(build_publish_packet(topic, request))

            def advance_probe() -> bool:
                """Publish the next condition variant; False when exhausted."""
                nonlocal probe_index
                if probe_index + 1 >= len(probes):
                    return False
                probe_index += 1
                publish_probe(probe_index)
                return True

            def attempted_variants() -> dict[str, dict[str, Any]]:
                for label, _signal_list in probes[: probe_index + 1]:
                    variants.setdefault(label, {})
                return variants

            if advance_probe():
                await writer.drain()

            while loop.time() < deadline:
                if (
                    probe_index >= 0
                    and probe_deadline is not None
                    and loop.time() >= probe_deadline
                    and advance_probe()
                ):
                    await writer.drain()
                wait = deadline - loop.time()
                if (
                    probe_index >= 0
                    and probe_deadline is not None
                    and probe_index + 1 < len(probes)
                ):
                    wait = min(wait, max(0.05, probe_deadline - loop.time()))
                try:
                    first, body = await read_packet_with_keepalive(
                        reader,
                        writer,
                        max(0.05, wait),
                        self.mqtt_keepalive,
                    )
                except asyncio.TimeoutError:
                    if advance_probe():
                        await writer.drain()
                        continue
                    break
                if first >> 4 != 3:
                    continue
                try:
                    topic, payload, packet_id = parse_publish(first, body)
                except ValueError as err:
                    self._emit_mqtt(
                        "error",
                        vehicle_id=vehicle_id,
                        stage="condition",
                        error=f"malformed publish: {err}",
                    )
                    logger.debug(
                        "Deepal MQTT: skipping a malformed PUBLISH packet (%s)", err
                    )
                    continue
                if packet_id is not None:
                    writer.write(build_puback_packet(packet_id))
                    await writer.drain()

                params = self._s05_params_from_payload(payload, secret_key)
                label = probe_labels.get(str(payload.get("r")), None)
                self._emit_mqtt(
                    "receive",
                    vehicle_id=vehicle_id,
                    stage="condition",
                    source=label,
                    topic=topic,
                    payload=payload,
                    params=params,
                    decoded=bool(params),
                    request_id=payload.get("r"),
                )
                if not params:
                    continue
                if label:
                    variants[label] = params
                    source = label
                if topic.endswith("/properties/get/res") and len(params) > 10:
                    self._log_s05_discovery(params)
                    return MqttExchangeResult(
                        params=params,
                        source=source,
                        variants=attempted_variants(),
                        plan=plan,
                    )
                partial.update(params)
                if probe_index >= 0 and len(partial) > 30:
                    self._log_s05_discovery(partial)
                    return MqttExchangeResult(
                        params=partial,
                        source=source,
                        variants=attempted_variants(),
                        plan=plan,
                    )

            self._log_s05_discovery(partial)
            self._emit_mqtt(
                "timeout",
                vehicle_id=vehicle_id,
                stage="condition",
                source=source,
                partial=partial,
                variants=attempted_variants(),
            )
            return MqttExchangeResult(
                params=partial,
                source=source,
                variants=attempted_variants(),
                plan=plan,
            )
        finally:
            await self._close_s05_mqtt(writer, vehicle_id=vehicle_id)

    async def s05_wait_for_report(
        self,
        vehicle_id: str,
        *,
        previous_timestamp: Optional[int] = None,
        interval: float = 5.0,
        timeout: float = 60.0,
        vin: Optional[str] = None,
    ) -> Optional[VehicleCondition]:
        """Wait for a newer S05 report over one bounded MQTT exchange.

        Opens a single session and re-publishes the condition request every
        ``interval`` seconds until a snapshot newer than ``previous_timestamp``
        arrives or the caller's ``timeout`` expires, so a wake refresh does not
        open one session per poll. Returns ``None`` when no newer report
        arrives in time; a broken session raises ``DeepalAPIError`` so the
        caller can retry with the remaining budget. The session stays under the
        client's MQTT lock for its whole (bounded) duration because the broker
        closes concurrent sessions that share the account identity.
        """
        async with self._mqtt_lock:
            config = await self.get_mqtt_config(vehicle_id)
            token = await self.get_mqtt_token()
            try:
                (
                    reader,
                    writer,
                    resolved,
                    basic_info,
                    secret_key,
                    _plan,
                ) = await self._open_s05_mqtt(
                    config, token, vehicle_id=vehicle_id
                )
            except (asyncio.TimeoutError, EOFError, OSError, ssl.SSLError) as exc:
                self._emit_mqtt(
                    "error",
                    vehicle_id=vehicle_id,
                    stage="report_wait",
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                raise DeepalAPIError(
                    f"S05 MQTT report wait failed: {exc}"
                ) from exc
            try:
                loop = asyncio.get_running_loop()
                deadline = loop.time() + timeout
                request_timeout = (
                    self.mqtt_exchange_timeout or MQTT_EXCHANGE_TIMEOUT
                )
                while True:
                    wait = max(
                        0.05, min(request_timeout, deadline - loop.time())
                    )
                    try:
                        condition = await self._request_condition_on_session(
                            reader,
                            writer,
                            resolved,
                            basic_info,
                            secret_key,
                            vehicle_id,
                            vin,
                            wait,
                            require_timestamp=previous_timestamp is not None,
                        )
                    except (
                        asyncio.TimeoutError,
                        EOFError,
                        OSError,
                        ssl.SSLError,
                    ) as exc:
                        self._emit_mqtt(
                            "error",
                            vehicle_id=vehicle_id,
                            stage="report_wait",
                            error=str(exc),
                            error_type=type(exc).__name__,
                        )
                        raise DeepalAPIError(
                            f"S05 MQTT report wait failed: {exc}"
                        ) from exc
                    if condition is not None:
                        timestamp = condition.last_updated_timestamp
                        if previous_timestamp is None or (
                            timestamp is not None
                            and timestamp > previous_timestamp
                        ):
                            self._emit_mqtt(
                                "result",
                                vehicle_id=vehicle_id,
                                stage="report_wait",
                                source="legacy-mqtt",
                                timestamp=timestamp,
                            )
                            return condition
                    remaining = deadline - loop.time()
                    if remaining <= 0:
                        self._emit_mqtt(
                            "timeout",
                            vehicle_id=vehicle_id,
                            stage="report_wait",
                            previous_timestamp=previous_timestamp,
                        )
                        return None
                    await asyncio.sleep(min(interval, remaining))
            finally:
                await self._close_s05_mqtt(writer, vehicle_id=vehicle_id)

    async def _request_condition_on_session(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        resolved: MqttTopics,
        basic_info: Mapping[str, Any],
        secret_key: str,
        vehicle_id: str,
        vin: Optional[str],
        wait: float,
        *,
        require_timestamp: bool,
    ) -> Optional[VehicleCondition]:
        """Request one condition snapshot on an already open MQTT session.

        Returns a complete snapshot, or ``None`` when the reply did not arrive
        within ``wait`` or was incomplete. With ``require_timestamp`` a
        response without a report timestamp field does not count: the parser's
        current-time fallback must not make it look fresh.
        """
        properties_topic = resolved.properties_publish
        device_did = resolved.device_did
        login_did = resolved.login_did or device_did
        if not properties_topic or not device_did or not secret_key:
            raise DeepalAPIError(
                "S05 MQTT session is missing the properties topic or the secretKey."
            )
        req_id = new_request_id(device_did)
        request = condition_request_payload(
            device_did,
            login_did,
            secret_key,
            req_id,
            basic_info=basic_info,
        )
        self._emit_mqtt(
            "publish",
            vehicle_id=vehicle_id,
            stage="report_wait_request",
            topic=properties_topic,
            payload=request,
            services=condition_request_services(),
            request_id=req_id,
        )
        writer.write(build_publish_packet(properties_topic, request))
        await writer.drain()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait
        partial: dict[str, Any] = {}
        while loop.time() < deadline:
            try:
                first, body = await read_packet_with_keepalive(
                    reader,
                    writer,
                    max(0.05, deadline - loop.time()),
                    self.mqtt_keepalive,
                )
            except asyncio.TimeoutError:
                self._emit_mqtt(
                    "timeout",
                    vehicle_id=vehicle_id,
                    stage="report_wait_request",
                    request_id=req_id,
                    partial=partial,
                )
                return None
            if first >> 4 != 3:
                continue
            try:
                topic, payload, packet_id = parse_publish(first, body)
            except ValueError as err:
                self._emit_mqtt(
                    "error",
                    vehicle_id=vehicle_id,
                    stage="report_wait_request",
                    error=f"malformed publish: {err}",
                )
                logger.debug(
                    "Deepal MQTT: skipping a malformed PUBLISH packet (%s)", err
                )
                continue
            if packet_id is not None:
                writer.write(build_puback_packet(packet_id))
                await writer.drain()
            # The vehicle may answer the condition request directly or emit an
            # asynchronous properties/report with its own request id. Both are
            # valid sources as long as they decrypt and carry a newer report;
            # the caller applies the timestamp check.
            params = self._s05_params_from_payload(payload, secret_key)
            self._emit_mqtt(
                "receive",
                vehicle_id=vehicle_id,
                stage="report_wait_request",
                topic=topic,
                payload=payload,
                params=params,
                decoded=bool(params),
                request_id=payload.get("r"),
            )
            if not params:
                continue
            partial.update(params)
            if len(partial) > 10:
                break
        else:
            self._emit_mqtt(
                "timeout",
                vehicle_id=vehicle_id,
                stage="report_wait_request",
                request_id=req_id,
                partial=partial,
            )
            return None
        if require_timestamp and not any(
            key in partial
            for key in ("lastUpdatedTime", "lastUpdatedAt", "latestDate")
        ):
            self._emit_mqtt(
                "timeout",
                vehicle_id=vehicle_id,
                stage="report_wait_request",
                request_id=req_id,
                partial=partial,
                reason="no_timestamp",
            )
            return None
        condition = self.parse_condition(
            normalize_s05_params(partial), vehicle_id, vin=vin
        )
        location = find_location(partial)
        if location is not None:
            condition.latitude, condition.longitude = location
        condition.mqtt_raw_data = partial
        condition.condition_source = "legacy-mqtt"
        return condition

    async def wake_vehicle(self, vehicle_id: str) -> None:
        """Wake an MQTT-backed vehicle so it publishes fresh condition data.

        Publishes the app's ``TxWakeup``/``Cnr_ReWakeup`` service on the
        ``properties/set/req`` topic and returns once the gateway acknowledges
        it with ``000000``. The vehicle then reports within a few seconds; the
        caller polls the condition for the fresh snapshot. Sessions are
        serialized per client because all vehicles of an account share the
        broker client identity. A failed wake drops the cached connection
        configuration and auth token, so the next attempt does not reuse
        material that may have caused the failure.
        """
        async with self._mqtt_lock:
            try:
                await self._wake_vehicle_locked(vehicle_id)
            except Exception:
                self._mqtt_configs.pop(vehicle_id, None)
                self._invalidate_mqtt_token()
                raise

    async def _wake_vehicle_locked(self, vehicle_id: str) -> None:
        config = await self.get_mqtt_config(vehicle_id)
        token = await self.get_mqtt_token()
        try:
            (
                reader,
                writer,
                resolved,
                basic_info,
                secret_key,
                _plan,
            ) = await self._open_s05_mqtt(
                config, token, vehicle_id=vehicle_id
            )
        except (asyncio.TimeoutError, EOFError, OSError, ssl.SSLError) as exc:
            self._emit_mqtt(
                "error",
                vehicle_id=vehicle_id,
                stage="wake",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise DeepalAPIError(f"S05 MQTT wake failed: {exc}") from exc

        try:
            try:
                set_topic = resolved.properties_set_publish
                device_did = resolved.device_did
                login_did = resolved.login_did
                if not set_topic or not device_did or not login_did:
                    raise DeepalAPIError(
                        "S05 MQTT configuration did not include the properties/set topic."
                    )
                if not secret_key:
                    raise DeepalAPIError("S05 MQTT login did not return a secretKey.")

                req_id = new_request_id(device_did)
                wake_payload = wake_request_payload(
                    device_did,
                    login_did,
                    secret_key,
                    req_id,
                    basic_info=basic_info,
                )
                self._emit_mqtt(
                    "publish",
                    vehicle_id=vehicle_id,
                    stage="wake",
                    topic=set_topic,
                    payload=wake_payload,
                    services=wake_request_services(req_id),
                    request_id=req_id,
                )
                writer.write(
                    build_publish_packet(
                        set_topic,
                        wake_payload,
                        # QoS 1: the broker queues the wake for the vehicle
                        # session when the car is deeply asleep and offline,
                        # instead of dropping it like a QoS 0 message. The
                        # packet identifier is distinct from the SUBSCRIBE one.
                        qos=1,
                        packet_id=WAKE_PACKET_ID,
                    )
                )
                await writer.drain()
                logger.info(
                    "Deepal wake for %s published on the properties/set topic",
                    vehicle_id,
                )

                loop = asyncio.get_running_loop()
                started = loop.time()
                wait_seconds = self.mqtt_wake_timeout or MQTT_EXCHANGE_TIMEOUT
                deadline = started + wait_seconds
                observed: list[str] = []
                while loop.time() < deadline:
                    try:
                        first, body = await read_packet_with_keepalive(
                            reader,
                            writer,
                            max(0.05, deadline - loop.time()),
                            self.mqtt_keepalive,
                        )
                    except asyncio.TimeoutError:
                        break
                    if first >> 4 != 3:
                        observed.append(f"packet_type={first >> 4}")
                        continue
                    try:
                        topic, payload, packet_id = parse_publish(first, body)
                    except ValueError as err:
                        logger.debug(
                            "Deepal MQTT: skipping a malformed PUBLISH packet (%s)",
                            err,
                        )
                        continue
                    if packet_id is not None:
                        writer.write(build_puback_packet(packet_id))
                        await writer.drain()
                    matched = payload.get("r") == req_id
                    result = self._service_result_from_payload(payload, secret_key)
                    self._emit_mqtt(
                        "receive",
                        vehicle_id=vehicle_id,
                        stage="wake",
                        topic=topic,
                        payload=payload,
                        request_id=payload.get("r"),
                        matched=matched,
                        result=result,
                    )
                    observed.append(
                        "topic={} r={} result={}".format(
                            "/".join(topic.rsplit("/", 2)[-2:]),
                            "match" if matched else "other",
                            result,
                        )
                    )
                    if not matched or result is None:
                        continue
                    code, success = result
                    if success or code in WAKE_OK_CODES:
                        self._emit_mqtt(
                            "result",
                            vehicle_id=vehicle_id,
                            stage="wake",
                            code=code,
                            success=success,
                            duration_s=round(loop.time() - started, 1),
                        )
                        logger.info(
                            "Deepal wake for %s acknowledged with code %s after "
                            "%.1f s",
                            vehicle_id,
                            code,
                            loop.time() - started,
                        )
                        return
                    self._emit_mqtt(
                        "error",
                        vehicle_id=vehicle_id,
                        stage="wake",
                        code=code,
                        error=f"wake rejected with code {code}",
                    )
                    raise DeepalAPIError(
                        f"Vehicle wake was rejected: {code}", code=code
                    )
                summary = "; ".join(observed[:8])
                if len(observed) > 8:
                    summary += f" (+{len(observed) - 8} more)"
                self._emit_mqtt(
                    "timeout",
                    vehicle_id=vehicle_id,
                    stage="wake",
                    observed=observed[:8],
                    wait_seconds=wait_seconds,
                )
                logger.warning(
                    "Deepal wake for %s got no acknowledgement within %.0f s: %s",
                    vehicle_id,
                    wait_seconds,
                    summary or "no publishes received",
                )
                raise DeepalAPIError("Vehicle wake did not return a response.")
            except (asyncio.TimeoutError, EOFError, OSError, ssl.SSLError) as exc:
                self._emit_mqtt(
                    "error",
                    vehicle_id=vehicle_id,
                    stage="wake",
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                raise DeepalAPIError(f"S05 MQTT wake failed: {exc}") from exc
        finally:
            await self._close_s05_mqtt(writer, vehicle_id=vehicle_id)

    @staticmethod
    def _service_result_from_payload(
        payload: dict[str, Any], secret_key: str
    ) -> Optional[tuple[str, bool]]:
        """Return the first service result ``(code, success)`` of one MQTT message."""
        req_id = payload.get("r")
        if not isinstance(req_id, str):
            return None
        for field in ("rs", "sers"):
            encrypted = payload.get(field)
            if not isinstance(encrypted, str) or not encrypted:
                continue
            try:
                items = aes_cbc_decrypt(encrypted, secret_key, req_id)
            except (ValueError, json.JSONDecodeError, OSError):
                continue
            for item in items:
                if isinstance(item, dict) and item.get("code"):
                    return str(item["code"]), bool(item.get("success"))
        return None

    @staticmethod
    def _s05_params_from_payload(
        payload: dict[str, Any], secret_key: str
    ) -> dict[str, Any]:
        """Decrypt the ``rs``/``sers`` fields of one MQTT message into parameters."""
        req_id = payload.get("r")
        if not isinstance(req_id, str):
            return {}
        params: dict[str, Any] = {}
        for field in ("rs", "sers"):
            encrypted = payload.get(field)
            if not isinstance(encrypted, str) or not encrypted:
                continue
            try:
                items = aes_cbc_decrypt(encrypted, secret_key, req_id)
            except (ValueError, json.JSONDecodeError, OSError):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                service_code = item.get("service_code")
                item_params = item.get("params")
                item_data = item.get("data")
                if service_code in S05_SERVICE_CODES or service_code in SDA_SERVICE_CODES:
                    merged = False
                    if isinstance(item_params, dict):
                        params.update(item_params)
                        merged = True
                    if isinstance(item_data, dict):
                        params.update(item_data)
                        merged = True
                    if merged:
                        continue
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "S05 MQTT unmapped service_code=%s keys=%s",
                        service_code,
                        sorted(item_params)
                        if isinstance(item_params, dict)
                        else repr(item_params),
                    )
        return params

    def _load_private_key(self):
        if not self.private_key_pem:
            raise DeepalCommandNotReady(
                "Login private key is required to sign commands."
            )
        try:
            return serialization.load_pem_private_key(
                self.private_key_pem.encode(), password=None
            )
        except (ValueError, TypeError) as exc:
            raise DeepalCommandAuthError(
                "The stored login private key is not usable; log in again to "
                "register a new command-signing key."
            ) from exc

    def sign_payload(
        self, payload: dict[str, Any], omit_keys: Optional[set[str]] = None
    ) -> str:
        """Sign a command payload with the login keypair.

        The default ``app`` policy signs alphabetically sorted ``key=value``
        pairs excluding exactly ``sign``, ``class`` and ``command``, including
        an empty ``rcToken``. The ``legacy`` policy keeps the per-command
        omission sets for rollback and live A/B checks.
        """
        private_key = self._load_private_key()
        if self.signing_policy == SIGNING_POLICY_LEGACY:
            omitted = set(omit_keys or ())
            omitted.add("sign")
        else:
            omitted = APP_SIGN_EXCLUDED_KEYS
        parts = []
        for key in sorted(payload):
            if key in omitted:
                continue
            value = payload[key]
            if isinstance(value, bool):
                value = str(value).lower()
            elif value is None:
                value = "null"
            parts.append(f"{key}={value}")
        canonical = "&".join(parts)
        signature = private_key.sign(
            canonical.encode(), padding.PKCS1v15(), hashes.SHA256()
        )
        return base64.encodebytes(signature).decode()

    async def get_serial_data(self, serial_type: str = "1") -> str:
        """Fetch the encrypted vehicle serial number used by signed commands."""
        data = await self._request(
            INTL_GET_SERIAL_NO,
            json_data={"type": serial_type},
            auth_required=True,
        )
        if not isinstance(data, str):
            raise DeepalAPIError("Unexpected serial number response.")
        return data

    def decrypt_serial_no(self, serial_data: str) -> str:
        """Decrypt a serial number with the login private key."""
        private_key = self._load_private_key()
        ciphertext = base64.b64decode("".join(serial_data.split()))
        try:
            return private_key.decrypt(ciphertext, padding.PKCS1v15()).decode().strip()
        except ValueError as exc:
            raise DeepalCommandAuthError(
                "Could not decrypt the vehicle serial number; log in again to "
                "register a new command-signing key."
            ) from exc

    async def get_security_code_status(self) -> dict[str, Any]:
        """Fetch the control PIN status before exchanging it.

        The official app always calls this immediately before ``check-code``
        (live capture, changelog of BeauGiles/ha-deepal-cloud 0.3.4).
        """
        data = await self._request(
            INTL_GET_SECURITY_CODE_STATUS, json_data={}, auth_required=True
        )
        return data if isinstance(data, dict) else {}

    async def check_control_code(self, control_pin: str) -> str:
        """Exchange the remote-control PIN for an rcToken."""
        status = await self.get_security_code_status()
        retry_quantity = status.get("retryQuantity")
        try:
            remaining = int(retry_quantity) if retry_quantity is not None else None
        except (TypeError, ValueError):
            remaining = None
        if remaining is not None and remaining <= 0:
            raise DeepalRateLimitError(
                "No control-code attempts left; wait for the lockout to expire or "
                "reset the PIN in the My Changan app."
            )
        data = await self._request(
            INTL_CHECK_CONTROL_CODE,
            json_data={"safeCode": self.encrypt_request_value(control_pin)},
            auth_required=True,
        )
        if not isinstance(data, dict) or not data.get("rcToken"):
            raise DeepalCommandAuthError("Control-code check did not return an rcToken.")
        self.rc_token = str(data["rcToken"])
        return self.rc_token

    async def _signed_command(
        self,
        path: str,
        vehicle_id: str,
        payload: dict[str, Any],
        serial_type: str = "1",
        require_rc_token: bool = False,
        sign_omit_keys: Optional[set[str]] = None,
    ) -> str:
        if not self.private_key_pem:
            raise DeepalCommandNotReady(
                "Login private key is required to sign commands."
            )
        reused_rc_token = False
        if require_rc_token:
            if self.rc_token:
                reused_rc_token = True
            elif self.control_pin:
                await self.check_control_code(self.control_pin)
            else:
                raise DeepalCommandNotReady("Control PIN is required for this command.")

        serial_data = await self.get_serial_data(serial_type)
        serial_no = self.decrypt_serial_no(serial_data)
        signed_payload = {
            **payload,
            "seriralNo": serial_no,
            "vehicleId": vehicle_id,
        }
        if require_rc_token and self.rc_token:
            signed_payload["rcToken"] = self.rc_token
        signed_payload["sign"] = self.sign_payload(
            signed_payload, omit_keys=sign_omit_keys
        )

        try:
            data = await self._request(
                path, json_data=signed_payload, auth_required=True
            )
        except (DeepalAPIError, DeepalAuthError):
            # A cached rcToken is a session that expires (the official app asks
            # for the control PIN again roughly weekly); the server only reveals
            # it is stale when it rejects a command that reused it. Exchange a
            # fresh token with the stored PIN and retry once.
            if not (require_rc_token and reused_rc_token and self.control_pin):
                raise
            self.rc_token = None
            await self.check_control_code(self.control_pin)
            signed_payload["rcToken"] = self.rc_token or ""
            signed_payload["sign"] = self.sign_payload(
                signed_payload, omit_keys=sign_omit_keys
            )
            data = await self._request(
                path, json_data=signed_payload, auth_required=True
            )

        if not isinstance(data, dict) or not data.get("commandId"):
            raise DeepalAPIError("Control command did not return a commandId.")
        return str(data["commandId"])

    async def control_air_conditioner(
        self,
        vehicle_id: str,
        enabled: bool,
        target_temp_c: float,
        run_time: int = 30,
        wind_mode: int = 1,
    ) -> str:
        """Turn the cabin air conditioner on or off and set its target temperature."""
        return await self._signed_command(
            path=INTL_CONTROL_AIR_CONDITIONER,
            vehicle_id=vehicle_id,
            payload={
                "command": "air",
                "enabled": enabled,
                "runTime": run_time,
                "targetTemp": int(round(target_temp_c * 10)),
                "windMode": wind_mode,
            },
            sign_omit_keys={"command", "rcToken"},
        )

    async def control_condition_inquiry(self, vehicle_id: str) -> str:
        """Ask the vehicle to report fresh condition data."""
        return await self._signed_command(
            path=INTL_CONDITION_INQUIRY,
            vehicle_id=vehicle_id,
            payload={"command": "COMMAND_GET_NEW_CONDITION"},
            sign_omit_keys={"command", "rcToken"},
        )

    async def control_doors(self, vehicle_id: str, open_value: bool) -> str:
        """Lock (`open_value=False`) or unlock (`open_value=True`) the vehicle.

        The app base request class always carries ``command``, set to ``lock``
        for this endpoint; it stays outside the canonical signature.
        """
        return await self._signed_command(
            path=INTL_CONTROL_DOORS,
            vehicle_id=vehicle_id,
            payload={"command": "lock", "open": open_value},
            require_rc_token=True,
            sign_omit_keys={"command"},
        )

    async def control_windows(
        self, vehicle_id: str, open_value: bool, open_type: int = 10
    ) -> str:
        """Open or close all windows."""
        return await self._signed_command(
            path=INTL_CONTROL_WINDOWS,
            vehicle_id=vehicle_id,
            payload={"command": "window", "open": open_value, "openType": open_type},
            require_rc_token=True,
            sign_omit_keys={"command"},
        )

    async def control_trunk(self, vehicle_id: str, open_value: bool) -> str:
        """Open or close the boot/trunk."""
        return await self._signed_command(
            path=INTL_CONTROL_TRUNK,
            vehicle_id=vehicle_id,
            payload={"command": "trunk", "open": open_value},
            require_rc_token=True,
            sign_omit_keys={"command"},
        )

    async def control_charge_limit(self, vehicle_id: str, percentage: int) -> str:
        """Set the maximum charge percentage."""
        return await self._signed_command(
            path=INTL_CHARGE_PERCENTAGE,
            vehicle_id=vehicle_id,
            payload={
                "chargePercentageMax": int(percentage),
                "command": "charge_max",
            },
            serial_type="2",
            sign_omit_keys={"command", "rcToken"},
        )

    async def control_charge_schedule(
        self,
        vehicle_id: str,
        plan_id: str,
        start_time: str,
        end_time: str,
        enabled: bool,
        plan_type: int = 1,
        time_format: int = 1,
        time_zone: str = "GMT+08:00",
    ) -> str:
        """Update the charging schedule plan."""
        switch = 1 if enabled else 0
        return await self._signed_command(
            path=INTL_CHARGE_MODIFY_PLAN,
            vehicle_id=vehicle_id,
            payload={
                "command": "modify-plan",
                "endSwitch": switch,
                "endTime": end_time,
                "planId": str(plan_id),
                "planType": plan_type,
                "startTime": start_time,
                "timeFormat": time_format,
                "timeZone": time_zone,
            },
            serial_type="2",
            sign_omit_keys={"command", "rcToken"},
        )

    async def control_flashing_honking(self, vehicle_id: str, action_type: int) -> str:
        """Flash the lights (`FLASH_HONK_FLASH`), sound the horn (`FLASH_HONK_BEE`),
        combine both (`FLASH_HONK_FLASH_BEE`) or turn them off (`FLASH_HONK_OFF`)."""
        return await self._signed_command(
            path=INTL_CONTROL_FLASHING_HONKING,
            vehicle_id=vehicle_id,
            payload={"command": "flash_bee", "type": action_type},
            sign_omit_keys={"command", "rcToken"},
        )

    async def control_defrost(
        self,
        vehicle_id: str,
        enabled: bool,
        serial_type: str = "1",
        require_rc_token: bool = False,
    ) -> str:
        """Turn the front defrost on or off (optional command)."""
        return await self._signed_command(
            path=INTL_CONTROL_DEFROST,
            vehicle_id=vehicle_id,
            payload={"command": "defrost", "enabled": enabled},
            serial_type=serial_type,
            require_rc_token=require_rc_token,
            sign_omit_keys={"command", "rcToken"},
        )

    @staticmethod
    def _seat_payload(
        command: str,
        master_switch: Optional[int],
        master_level: Optional[int],
        copilot_switch: Optional[int],
        copilot_level: Optional[int],
    ) -> dict[str, Any]:
        """Build a seat command body with only the provided positions.

        The app omits null fields (no ``serializeNulls``), and the live probe
        showed that turning a seat off must send ``switch: 0`` without a level:
        a zero level is rejected with ``COMMON_1_1_01_005``.
        """
        payload: dict[str, Any] = {"command": command}
        if master_switch is not None:
            payload["masterSwitch"] = master_switch
        if master_level:
            payload["masterLevel"] = master_level
        if copilot_switch is not None:
            payload["copilotSwitch"] = copilot_switch
        if copilot_level:
            payload["copilotLevel"] = copilot_level
        return payload

    async def control_seats_heat(
        self,
        vehicle_id: str,
        master_switch: Optional[int] = None,
        master_level: Optional[int] = None,
        copilot_switch: Optional[int] = None,
        copilot_level: Optional[int] = None,
        serial_type: str = "1",
        require_rc_token: bool = False,
    ) -> str:
        """Set the driver/copilot seat heating levels (optional command).

        Only the requested position is serialized: the app's Gson body omits null
        fields, and the endpoint rejects explicit nulls.
        """
        return await self._signed_command(
            path=INTL_CONTROL_SEATS_HEAT,
            vehicle_id=vehicle_id,
            payload=self._seat_payload(
                "seats_heat",
                master_switch,
                master_level,
                copilot_switch,
                copilot_level,
            ),
            serial_type=serial_type,
            require_rc_token=require_rc_token,
            sign_omit_keys={"command", "rcToken"},
        )

    async def control_seats_wind(
        self,
        vehicle_id: str,
        master_switch: Optional[int] = None,
        master_level: Optional[int] = None,
        copilot_switch: Optional[int] = None,
        copilot_level: Optional[int] = None,
        serial_type: str = "1",
        require_rc_token: bool = False,
    ) -> str:
        """Set the driver/copilot seat ventilation levels (optional command)."""
        return await self._signed_command(
            path=INTL_CONTROL_SEATS_WIND,
            vehicle_id=vehicle_id,
            payload=self._seat_payload(
                "seats_wind",
                master_switch,
                master_level,
                copilot_switch,
                copilot_level,
            ),
            serial_type=serial_type,
            require_rc_token=require_rc_token,
            sign_omit_keys={"command", "rcToken"},
        )

    async def control_steering_wheel_heat(
        self,
        vehicle_id: str,
        open_value: bool,
        serial_type: str = "1",
        require_rc_token: bool = False,
    ) -> str:
        """Turn the steering wheel heating on or off (optional command)."""
        return await self._signed_command(
            path=INTL_CONTROL_STEERING_WHEEL_HEAT,
            vehicle_id=vehicle_id,
            payload={"command": "steering_wheel_heating", "open": open_value},
            serial_type=serial_type,
            require_rc_token=require_rc_token,
            sign_omit_keys={"command", "rcToken"},
        )

    async def control_charge_plan_add(
        self,
        vehicle_id: str,
        start_time: str,
        end_time: str,
        end_switch: int,
        plan_type: int = 1,
        time_format: int = 1,
        time_zone: str = "GMT+08:00",
        serial_type: str = "2",
        require_rc_token: bool = False,
    ) -> str:
        """Add a charging schedule plan (optional command)."""
        return await self._signed_command(
            path=INTL_CHARGE_ADD_PLAN,
            vehicle_id=vehicle_id,
            payload={
                "command": "add_charge_plan",
                "endSwitch": end_switch,
                "endTime": end_time,
                "planType": plan_type,
                "startTime": start_time,
                "timeFormat": time_format,
                "timeZone": time_zone,
            },
            serial_type=serial_type,
            require_rc_token=require_rc_token,
            sign_omit_keys={"command", "rcToken"},
        )

    async def control_charge_plan_delete(
        self,
        vehicle_id: str,
        plan_id: str,
        serial_type: str = "2",
        require_rc_token: bool = False,
    ) -> str:
        """Delete a charging schedule plan (optional command)."""
        return await self._signed_command(
            path=INTL_CHARGE_DELETE_PLAN,
            vehicle_id=vehicle_id,
            payload={"command": "delete_charge_plan", "planId": str(plan_id)},
            serial_type=serial_type,
            require_rc_token=require_rc_token,
            sign_omit_keys={"command", "rcToken"},
        )

    async def control_charge_plan_validity(
        self,
        vehicle_id: str,
        plan_id: str,
        enabled: bool,
        serial_type: str = "2",
        require_rc_token: bool = False,
    ) -> str:
        """Enable or disable a charging schedule plan (optional command)."""
        return await self._signed_command(
            path=INTL_CHARGE_VALIDITY,
            vehicle_id=vehicle_id,
            payload={
                "command": "COMMAND_VALID_CHARGE_PLAN",
                "enabled": enabled,
                "planId": str(plan_id),
            },
            serial_type=serial_type,
            require_rc_token=require_rc_token,
            sign_omit_keys={"command", "rcToken"},
        )

    async def control_departure_plan_add(
        self,
        vehicle_id: str,
        start_time: str,
        weeks: str,
        plan_type: int = 1,
        schedule_type: int = 1,
        is_valid: int = 1,
        serial_type: str = "1",
        require_rc_token: bool = False,
    ) -> str:
        """Add a departure/charging-travel plan (optional command)."""
        return await self._signed_command(
            path=INTL_DEPARTURE_ADD_PLAN,
            vehicle_id=vehicle_id,
            payload={
                "command": "COMMAND_TRAVELPLAN_ADD",
                "isValid": is_valid,
                "planType": plan_type,
                "startTime": start_time,
                "type": schedule_type,
                "weeks": weeks,
            },
            serial_type=serial_type,
            require_rc_token=require_rc_token,
            sign_omit_keys={"command", "rcToken"},
        )

    async def control_departure_plan_modify(
        self,
        vehicle_id: str,
        plan_id: int,
        start_time: str,
        weeks: str,
        plan_type: int = 1,
        schedule_type: int = 1,
        is_valid: int = 1,
        serial_type: str = "1",
        require_rc_token: bool = False,
    ) -> str:
        """Modify a departure/charging-travel plan (optional command)."""
        return await self._signed_command(
            path=INTL_DEPARTURE_MODIFY_PLAN,
            vehicle_id=vehicle_id,
            payload={
                "command": "COMMAND_TRAVELPLAN_MODIFY_PLAN",
                "isValid": is_valid,
                "planId": int(plan_id),
                "planType": plan_type,
                "startTime": start_time,
                "type": schedule_type,
                "weeks": weeks,
            },
            serial_type=serial_type,
            require_rc_token=require_rc_token,
            sign_omit_keys={"command", "rcToken"},
        )

    async def control_departure_plan_delete(
        self,
        vehicle_id: str,
        plan_id: int,
        serial_type: str = "1",
        require_rc_token: bool = False,
    ) -> str:
        """Delete a departure/charging-travel plan (optional command)."""
        return await self._signed_command(
            path=INTL_DEPARTURE_DELETE,
            vehicle_id=vehicle_id,
            payload={
                "command": "COMMAND_TRAVELPLAN_DELETE",
                "planId": int(plan_id),
            },
            serial_type=serial_type,
            require_rc_token=require_rc_token,
            sign_omit_keys={"command", "rcToken"},
        )

    async def control_departure_plan_validity(
        self,
        vehicle_id: str,
        plan_id: int,
        enabled: bool,
        serial_type: str = "1",
        require_rc_token: bool = False,
    ) -> str:
        """Enable or disable a departure/charging-travel plan (optional command)."""
        return await self._signed_command(
            path=INTL_DEPARTURE_VALIDITY,
            vehicle_id=vehicle_id,
            payload={
                "command": "COMMAND_TRAVELPLAN_MODIFY_VALIDITY",
                "enabled": enabled,
                "planId": int(plan_id),
            },
            serial_type=serial_type,
            require_rc_token=require_rc_token,
            sign_omit_keys={"command", "rcToken"},
        )

    async def control_departure_plan_enabled(
        self,
        vehicle_id: str,
        plan_id: int,
        enabled: bool,
        serial_type: str = "1",
        require_rc_token: bool = False,
    ) -> str:
        """Start or stop a departure plan immediately (optional command)."""
        return await self._signed_command(
            path=INTL_DEPARTURE_ENABLED,
            vehicle_id=vehicle_id,
            payload={
                "command": "COMMAND_TRAVELPLAN_STARTSTOPPINGPLANNOW",
                "enabled": enabled,
                "planId": int(plan_id),
            },
            serial_type=serial_type,
            require_rc_token=require_rc_token,
            sign_omit_keys={"command", "rcToken"},
        )

    async def control_fota_plan(
        self,
        vehicle_id: str,
        appointment: bool,
        timestamp: str,
        serial_type: str = "1",
        require_rc_token: bool = False,
    ) -> str:
        """Schedule an OTA appointment (optional command)."""
        return await self._signed_command(
            path=INTL_CONTROL_FOTA_PLAN,
            vehicle_id=vehicle_id,
            payload={
                "command": "COMMAND_APPOINT_UPGRADE",
                "appointment": appointment,
                "timestamp": timestamp,
            },
            serial_type=serial_type,
            require_rc_token=require_rc_token,
            sign_omit_keys={"command", "rcToken"},
        )

    async def control_result(self, vehicle_id: str, command_id: str) -> dict[str, Any]:
        """Fetch the raw status payload of a signed command."""
        data = await self._request(
            INTL_CONTROL_RESULT,
            json_data={"vehicleId": vehicle_id, "commandId": command_id},
            auth_required=True,
        )
        return data if isinstance(data, dict) else {}

    async def control_result_status(
        self, vehicle_id: str, command_id: str
    ) -> CommandResult:
        """Fetch and classify the status of a signed command."""
        raw = await self.control_result(vehicle_id, command_id)
        return CommandResult.from_payload(raw)
