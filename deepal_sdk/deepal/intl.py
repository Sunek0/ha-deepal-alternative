"""Client for the Changan Deepal international gateway (email login)."""

import asyncio
import base64
from datetime import UTC, datetime
import json
import logging
import secrets
import ssl
import time
from typing import Any, Optional

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from deepal.endpoints import (
    DEFAULT_INTL_ENVIRONMENT,
    INTL_CA_APP_APIGW_GET_AUTH_TOKEN,
    INTL_CA_GET_AUTH_TOKEN,
    INTL_CA_GET_CAR_CONF_FUNC,
    INTL_CA_GET_CONN_CONF,
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
    INTL_GET_MY_CARS,
    INTL_GET_SERIAL_NO,
    INTL_GET_SECURITY_CODE_STATUS,
    INTL_GET_VEHICLE_CONDITION,
    INTL_LOGIN_BY_EMAIL_CODE,
    INTL_LOGIN_BY_EMAIL_PASSWORD,
    INTL_LOGIN_BY_MOBILE_CODE,
    INTL_LOGIN_BY_MOBILE_PASSWORD,
    INTL_LOGOUT,
    INTL_REFRESH_TOKEN,
    INTL_SEND_EMAIL_CODE,
    INTL_SEND_SMS_CODE,
    REQUEST_ENCRYPTION_PUBLIC_KEY,
    get_intl_environment,
)
from deepal.exceptions import (
    DeepalAPIError,
    DeepalAuthError,
    DeepalCommandAuthError,
    DeepalCommandNotReady,
    DeepalConnectionError,
    DeepalError,
    DeepalRateLimitError,
)
from deepal.redact import redact_for_log, safe_headers
from deepal.models import (
    AuthToken,
    BatteryCondition,
    ClimateCondition,
    CommandResult,
    DoorsCondition,
    LampsCondition,
    SeatsCondition,
    SeatStatus,
    TiresCondition,
    TireStatus,
    Vehicle,
    VehicleCondition,
    WindowsCondition,
)
from deepal.mqtt import (
    MQTT_CONNACK_REASONS,
    MQTT_DEFAULT_KEEPALIVE,
    S05_SERVICE_CODES,
    aes_cbc_decrypt,
    basic_identifiers,
    build_connect_packet,
    build_disconnect_packet,
    build_puback_packet,
    build_publish_packet,
    build_subscribe_packet,
    condition_request_payload,
    config_mqtt_identity,
    login_request_payload,
    new_request_id,
    normalize_s05_params,
    parse_connack,
    parse_publish,
    read_packet,
    read_packet_with_keepalive,
    resolve_mqtt_topics,
    secret_from_login_payload,
)

logger = logging.getLogger("deepal_sdk")

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
CAR_CONTROL_REFRESH_THROTTLE_SECONDS = 3300.0


def _is_auth_failure(code: Any) -> bool:
    code_str = str(code)
    return (
        "AUTH" in code_str.upper()
        or code_str.startswith("401")
        or code_str in _AUTH_ERROR_CODES
    )


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
        send_timestamps: bool = False,
        mqtt_config_fallback: bool = True,
        mqtt_token_fallback: bool = True,
        mqtt_client_id: Optional[str] = None,
        mqtt_username: Optional[str] = None,
        mqtt_keepalive: float = MQTT_DEFAULT_KEEPALIVE,
        mqtt_clean_start: bool = True,
        mqtt_tls_insecure: bool = False,
        device_id: Optional[str] = None,
        private_key_pem: Optional[str] = None,
        public_key: Optional[str] = None,
        base_url: Optional[str] = None,
        ca_base_url: Optional[str] = None,
        timeout: float = 15.0,
        enable_api_logging: bool = False,
        signing_policy: str = SIGNING_POLICY_APP,
        httpx_client: Optional[httpx.AsyncClient] = None,
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
        self.send_timestamps = send_timestamps
        self.mqtt_config_fallback = mqtt_config_fallback
        self.mqtt_token_fallback = mqtt_token_fallback
        self.mqtt_client_id = mqtt_client_id
        self.mqtt_username = mqtt_username
        self.mqtt_keepalive = mqtt_keepalive
        self.mqtt_clean_start = mqtt_clean_start
        self.mqtt_tls_insecure = mqtt_tls_insecure
        self.device_id = device_id or secrets.token_hex(16)
        self.base_url = (base_url or environment_config.intl_base_url).rstrip("/")
        self.ca_base_url = (ca_base_url or environment_config.ca_base_url).rstrip("/")
        self.timeout = timeout
        self.enable_api_logging = enable_api_logging
        self.signing_policy = signing_policy
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.cac_token: Optional[str] = None
        self.access_token_expires_at: Optional[int] = None
        self.user_id: Optional[str] = None
        self.ca_user_id: Optional[str] = None
        self.cac_user_id: Optional[str] = None
        self.control_pin: Optional[str] = None
        self.rc_token: Optional[str] = None
        self.public_key: Optional[str] = public_key
        self.private_key_pem: Optional[str] = private_key_pem
        self._external_client = httpx_client is not None
        self._client: Optional[httpx.AsyncClient] = httpx_client
        self._client_lock = asyncio.Lock()
        self._refresh_lock = asyncio.Lock()
        self._last_refresh_attempt_at: Optional[float] = None
        self._refresh_attempt_sequence = 0
        self._refresh_attempt_error: Optional[BaseException] = None

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

    @staticmethod
    def _public_body(public_key: rsa.RSAPublicKey) -> str:
        """Render an RSA public key as the app ``pubKey`` body."""
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
        return "\n".join(
            line
            for line in public_pem.splitlines()
            if "BEGIN" not in line and "END" not in line
        ) + "\n"

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
        the private PEM. Returns the resolved public key body.
        """
        if not private_key_pem:
            raise ValueError("private_key_pem is required.")
        self.private_key_pem = private_key_pem
        self.public_key = public_key or self.public_key_body_from_private(
            private_key_pem
        )
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
        if self.send_timestamps:
            headers["X-Tsp-Timestamp"] = str(int(time.time() * 1000))
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
        if self.enable_api_logging:
            logger.warning(
                "Deepal API request path=%s headers=%s payload=%s",
                path,
                safe_headers(headers),
                redact_for_log(json_data or {}),
            )

        try:
            http_client = await self._http_client()
            response = await http_client.request(
                method="POST",
                url=url,
                content=body,
                headers=headers,
            )
        except httpx.RequestError as exc:
            logger.error("Network error requesting %s: %s", url, exc)
            raise DeepalConnectionError(f"Failed to connect to Deepal API: {exc}") from exc

        if response.status_code in (401, 403):
            raise DeepalAuthError(
                f"Authentication failed with HTTP {response.status_code}."
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise DeepalAPIError(
                f"Invalid JSON response: {response.text[:200]}",
                status_code=response.status_code,
            ) from exc

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
            if _is_auth_failure(code):
                raise DeepalAuthError(f"Authentication failed: {code} {msg}")
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
        logger.warning(
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
            and not self.access_token_expires_soon()
            and self._refresh_is_throttled()
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

            if data.get("cacToken"):
                logger.info("Deepal token refresh returned a new CAC token")
            else:
                logger.warning(
                    "Deepal token refresh did not return a new CAC token; the CA/MQTT "
                    "bootstrap keeps the previous one"
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
                    car_name=item.get("nickName") or item.get("carName"),
                    license_plate=item.get("licensePlate") or item.get("plateNumber"),
                    thumbnail_url=item.get("imgUrl"),
                    protocol_type=item.get("protocolType") or item.get("protocol_type"),
                )
            )
        return vehicles

    async def get_vehicle_condition(
        self, vehicle_id: str, vin: Optional[str] = None
    ) -> VehicleCondition:
        """Fetch the telemetry condition of an international vehicle."""
        raw = await self._request(
            INTL_GET_VEHICLE_CONDITION,
            json_data={
                "vechileCriteria": {
                    "seat": "1",
                    "door": "1",
                    "hvac": "1",
                    "charge": "1",
                    "lamp": "1",
                    "window": "1",
                    "tire": "1",
                    "vehicleStatus": "1",
                },
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
        tire = raw.get("tire") or {}
        seat = raw.get("seat") or {}
        window = raw.get("window") or {}
        lamp = raw.get("lamp") or {}
        charge_plan = _path_value(charge, ("chargePlanList", 0)) or {}

        def _tenths(value: Any) -> Optional[float]:
            parsed = _as_float(value)
            return parsed / 10 if parsed is not None else None

        def _level(value: Any) -> int:
            level = _as_int(value)
            return level if level is not None and level > 0 else 0

        charge_status = charge.get("chargeStatus")
        charge_connection = charge.get("chargeConStatus")
        if charge_status not in (None, 0):
            charger_connected = True
        elif charge_connection is None:
            charger_connected = False
        else:
            charger_connected = charge_connection not in (0, 1)

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

        battery = BatteryCondition(
            soc_percentage=_as_int(status.get("soc")),
            remaining_range_km=_as_int(status.get("drvMileage")),
            charging_status=str(charge_status) if charge_status is not None else None,
            charger_connected=charger_connected,
            dc_gun_connected=charge.get("dcChargeGunConnectStatus") == 0,
            charge_current_a=_as_float(charge.get("chargeCurrent")),
            ac_charge_current_a=_as_float(charge.get("acChargeCurrent")),
            dc_charge_current_a=_as_float(charge.get("dcChargeCurrent")),
            remaining_charge_time_min=_as_int(charge.get("remainChargeTime")),
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
        ac_status = hvac.get("acStatus")

        climate = ClimateCondition(
            power_on=(
                ac_status not in (None, 0) if ac_status is not None else None
            ),
            target_temperature_c=target_temp / 10 if target_temp is not None else None,
            inside_temperature_c=_tenths(hvac.get("insideTemp")),
            outside_temperature_c=_tenths(hvac.get("outsideTemp")),
            humidity=_as_float(hvac.get("insideHumidity")),
            inside_pm25=_as_float(hvac.get("insidePm25")),
            air_quality_level=_as_int(hvac.get("insideAirQualityLevel")),
            defrost_on=hvac.get("defrostStatus") not in (None, 0),
            fan_level=_as_int(hvac.get("fanLevel")),
            steering_wheel_heater_on=steering_heater not in (None, 0),
            steering_wheel_heater_level=_as_int(status.get("steeringWheelHeaterLevel")) or 0,
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

        return VehicleCondition(
            car_id=vehicle_id,
            vin=raw.get("vin") or vin or "",
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
            power_status=_as_int(status.get("powerStatus")),
            vehicle_status=_as_int(status.get("status")),
            engine_on=_as_int(status.get("engineSts")) not in (None, 0),
            connected=(
                status.get("connectStatus") == 1
                if status.get("connectStatus") is not None
                else None
            ),
            battery=battery,
            doors=doors_condition,
            windows=windows_condition,
            seats=seats_condition,
            climate=climate,
            tires=tires_condition,
            lamps=lamps,
            last_updated_timestamp=last_updated // 1000 if last_updated is not None else None,
            raw_data=raw,
        )

    @staticmethod
    def is_mqtt_vehicle(vehicle: Vehicle) -> bool:
        """Return whether the vehicle reports telemetry over MQTT."""
        return (vehicle.protocol_type or "").upper() == "MQTT"

    async def get_mqtt_config(self, vehicle_id: str) -> dict[str, Any]:
        """Fetch the CA gateway MQTT connection configuration for a vehicle."""
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
        except DeepalAPIError as exc:
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
        return data

    async def get_mqtt_token(self) -> str:
        """Exchange the account user id for an MQTT auth token."""
        if not self.user_id:
            raise DeepalAPIError(
                "S05 MQTT telemetry requires the account user id; log in again."
            )
        try:
            data = await self._request(
                INTL_CA_GET_AUTH_TOKEN,
                json_data={"userId": self.user_id},
                auth_required=True,
                base_url=self.ca_base_url,
            )
        except DeepalRateLimitError:
            raise
        except DeepalAPIError as exc:
            if not self.mqtt_token_fallback:
                raise
            logger.warning(
                "getAuthTokenByUserId failed (%s); retrying with the app-apigw route",
                exc,
            )
            data = await self._request(
                INTL_CA_APP_APIGW_GET_AUTH_TOKEN,
                json_data={"userId": self.user_id},
                auth_required=True,
                base_url=self.ca_base_url,
            )
        if not isinstance(data, dict) or not data.get("authToken"):
            raise DeepalAPIError("S05 MQTT auth response did not include authToken.")
        return str(data["authToken"])

    async def s05_mqtt_condition(
        self, vehicle_id: str, vin: Optional[str] = None
    ) -> VehicleCondition:
        """Fetch a live S05 condition snapshot over MQTT."""
        config = await self.get_mqtt_config(vehicle_id)
        token = await self.get_mqtt_token()
        try:
            params = await self._read_s05_params(config, token)
        except (asyncio.TimeoutError, OSError, ssl.SSLError) as exc:
            raise DeepalAPIError(f"S05 MQTT telemetry failed: {exc}") from exc
        if not params:
            raise DeepalAPIError("S05 MQTT telemetry did not return vehicle condition.")
        return self.parse_condition(
            normalize_s05_params(params), vehicle_id, vin=vin
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

    async def _read_s05_params(
        self, config: dict[str, Any], token: str
    ) -> dict[str, Any]:
        """Run one MQTT 5.0 login + condition exchange and return the raw parameters."""
        info = ((config.get("mqttConnectionInfos") or [None])[0]) or {}
        cluster = ((info.get("clusterInfos") or [None])[0]) or {}
        host = str(cluster.get("brokerUrl", "")).replace("ssl://", "")
        port = int(cluster.get("brokerPort") or 8883)
        resolved = resolve_mqtt_topics(config, fallback_did=self.mqtt_client_id)
        login_topic = resolved.login_publish
        login_did = resolved.login_did
        properties_topic = resolved.properties_publish
        device_did = resolved.device_did

        if not host or not login_topic or not login_did or not properties_topic or not device_did:
            raise DeepalAPIError(
                "S05 MQTT configuration did not include required topics."
            )

        client_id, username = config_mqtt_identity(
            config,
            login_did,
            client_id=self.mqtt_client_id,
            username=self.mqtt_username,
        )
        basic_info = self._mqtt_basic_identifiers(config, login_did)
        context = await asyncio.to_thread(self._mqtt_ssl_context)
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=context, server_hostname=host),
            timeout=self.timeout,
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
                read_packet(reader), timeout=self.timeout
            )
            _session_present, reason_code = parse_connack(first, body)
            if reason_code != 0:
                reason = MQTT_CONNACK_REASONS.get(reason_code, "unknown reason code")
                raise DeepalAPIError(
                    "S05 MQTT broker rejected connection: "
                    f"reason code {reason_code} ({reason})"
                )

            writer.write(build_subscribe_packet(1, sorted(set(resolved.subscriptions))))
            await writer.drain()
            await asyncio.wait_for(read_packet(reader), timeout=self.timeout)

            login_req_id = new_request_id(login_did)
            writer.write(
                build_publish_packet(
                    login_topic,
                    login_request_payload(
                        login_did, login_req_id, basic_info=basic_info
                    ),
                )
            )
            await writer.drain()

            secret_key: Optional[str] = None
            partial: dict[str, Any] = {}
            requested = False
            loop = asyncio.get_running_loop()
            deadline = loop.time() + max(self.timeout, 20.0)

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
                    continue
                topic, payload, packet_id = parse_publish(first, body)
                if packet_id is not None:
                    writer.write(build_puback_packet(packet_id))
                    await writer.drain()

                if not secret_key:
                    secret_key = secret_from_login_payload(payload)
                    if secret_key:
                        req_id = new_request_id(device_did)
                        writer.write(
                            build_publish_packet(
                                properties_topic,
                                condition_request_payload(
                                    device_did,
                                    login_did,
                                    secret_key,
                                    req_id,
                                    basic_info=basic_info,
                                ),
                            )
                        )
                        await writer.drain()
                        requested = True
                    continue

                params = self._s05_params_from_payload(payload, secret_key)
                if not params:
                    continue
                if topic.endswith("/properties/get/res") and len(params) > 10:
                    return params
                partial.update(params)
                if requested and len(partial) > 30:
                    return partial

            return partial
        finally:
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
                if item.get("service_code") in S05_SERVICE_CODES and isinstance(
                    item.get("params"), dict
                ):
                    params.update(item["params"])
        return params

    def _load_private_key(self):
        if not self.private_key_pem:
            raise DeepalCommandNotReady(
                "Login private key is required to sign commands."
            )
        return serialization.load_pem_private_key(
            self.private_key_pem.encode(), password=None
        )

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
        if self.rc_token:
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
