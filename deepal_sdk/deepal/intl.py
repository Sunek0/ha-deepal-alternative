"""Client for the Changan Deepal international gateway (email login)."""

import base64
import json
import logging
import secrets
from typing import Any, Optional

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from deepal.endpoints import (
    INTL_BASE_URL,
    INTL_CHECK_CONTROL_CODE,
    INTL_CONDITION_INQUIRY,
    INTL_CONTROL_AIR_CONDITIONER,
    INTL_CONTROL_RESULT,
    INTL_GET_MY_CARS,
    INTL_GET_SERIAL_NO,
    INTL_GET_VEHICLE_CONDITION,
    INTL_LOGIN_BY_EMAIL_CODE,
    INTL_LOGIN_BY_MOBILE_CODE,
    INTL_REFRESH_TOKEN,
    INTL_SEND_EMAIL_CODE,
    INTL_SEND_SMS_CODE,
    REQUEST_ENCRYPTION_PUBLIC_KEY,
)
from deepal.exceptions import (
    DeepalAPIError,
    DeepalAuthError,
    DeepalConnectionError,
)
from deepal.models import (
    AuthToken,
    BatteryCondition,
    ClimateCondition,
    DoorsCondition,
    SeatsCondition,
    SeatStatus,
    TiresCondition,
    TireStatus,
    Vehicle,
    VehicleCondition,
    WindowsCondition,
)

logger = logging.getLogger("deepal_sdk")

INTL_APP_ID = "ca"
INTL_APP_TYPE = "Android"
INTL_APP_VERSION = "V1.11.0"
INTL_DEVICE_TYPE = "samsung"
INTL_OS_VERSION = "9"
INTL_USER_AGENT = "okhttp/4.12.0"
DEFAULT_COUNTRY = "GB"
DEFAULT_LANGUAGE = "en_US"

_AUTH_ERROR_CODES = {"APP_1_1_02_004", "APP_1_1_02_005"}


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


class DeepalIntlClient:
    """Asynchronous client for the Deepal international email login flow."""

    def __init__(
        self,
        country: str = DEFAULT_COUNTRY,
        language: str = DEFAULT_LANGUAGE,
        app_version: str = INTL_APP_VERSION,
        device_id: Optional[str] = None,
        base_url: str = INTL_BASE_URL,
        timeout: float = 15.0,
        httpx_client: Optional[httpx.AsyncClient] = None,
    ):
        self.country = country
        self.language = language
        self.app_version = app_version
        self.device_id = device_id or secrets.token_hex(16)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.cac_token: Optional[str] = None
        self.control_pin: Optional[str] = None
        self.rc_token: Optional[str] = None
        self.public_key: Optional[str] = None
        self.private_key_pem: Optional[str] = None
        self._external_client = httpx_client is not None
        self._client = httpx_client or httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        """Close the underlying HTTP client if managed internally."""
        if not self._external_client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self) -> "DeepalIntlClient":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    @staticmethod
    def generate_login_keypair() -> tuple[str, str]:
        """Generate the RSA keypair used for the login pubKey field."""
        key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
        private_pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
        public_pem = key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
        pub_body = "".join(
            line for line in public_pem.splitlines() if "BEGIN" not in line and "END" not in line
        )
        return private_pem, pub_body

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
            "appid": INTL_APP_ID,
            "language": self.language,
            "appversion": self.app_version,
            "apptype": INTL_APP_TYPE,
            "devicetype": INTL_DEVICE_TYPE,
            "deviceid": self.device_id,
            "selectcountry": self.country,
            "x-os-version": INTL_OS_VERSION,
            "accept-language": self.language,
            "content-type": "application/json; charset=UTF-8",
            "user-agent": INTL_USER_AGENT,
        }
        if self.access_token:
            headers["authorization"] = self._authorization_value()
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
    ) -> Any:
        """Perform an HTTP request against the international gateway."""
        if auth_required and not self.access_token:
            raise DeepalAuthError("Access token is required for this operation.")

        url = f"{self.base_url}{path}" if path.startswith("/") else path
        body = json.dumps(json_data or {}, separators=(",", ":"), ensure_ascii=False)

        try:
            response = await self._client.request(
                method="POST",
                url=url,
                content=body,
                headers=self._get_headers(),
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

        if payload.get("success") is False:
            code = payload.get("code")
            msg = payload.get("msg") or payload.get("message") or f"HTTP {response.status_code}"
            if _is_auth_failure(code):
                raise DeepalAuthError(f"Authentication failed: {code} {msg}")
            raise DeepalAPIError(
                f"API Error: {msg}",
                status_code=response.status_code,
                code=code,
            )

        if not response.is_success:
            raise DeepalAPIError(
                f"API Error: HTTP {response.status_code}",
                status_code=response.status_code,
                code=payload.get("code"),
            )

        return payload.get("data")

    def _ensure_pub_key(self, pub_key: Optional[str] = None) -> str:
        if pub_key:
            return pub_key
        if self.public_key:
            return self.public_key
        self.private_key_pem, self.public_key = self.generate_login_keypair()
        return self.public_key

    def _store_tokens(self, data: Any) -> AuthToken:
        if not isinstance(data, dict) or not data.get("token"):
            raise DeepalAuthError("Login response did not contain an access token.")

        self.access_token = str(data["token"])
        self.refresh_token = data.get("refreshToken")
        self.cac_token = data.get("cacToken")

        return AuthToken(
            access_token=self.access_token,
            refresh_token=self.refresh_token,
            cac_token=self.cac_token,
            user_id=data.get("userId"),
        )

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

    async def refresh_tokens(self) -> AuthToken:
        """Refresh the international session tokens."""
        if not self.refresh_token:
            raise DeepalAuthError("No refresh token is available.")

        data = await self._request(
            INTL_REFRESH_TOKEN,
            json_data={"refreshToken": self.refresh_token},
        )

        if not isinstance(data, dict) or not data.get("token"):
            raise DeepalAuthError("Refresh response did not contain an access token.")

        self.access_token = str(data["token"])
        self.refresh_token = data.get("refreshToken") or self.refresh_token
        self.cac_token = data.get("cacToken") or self.cac_token

        return AuthToken(
            access_token=self.access_token,
            refresh_token=self.refresh_token,
            cac_token=self.cac_token,
            user_id=data.get("userId"),
        )

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
                )
            )
        return vehicles

    async def get_vehicle_condition(self, vehicle_id: str) -> VehicleCondition:
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

        status = raw.get("vehicleStatus") or {}
        door = raw.get("door") or {}
        hvac = raw.get("hvac") or {}
        charge = raw.get("charge") or {}
        tire = raw.get("tire") or {}
        seat = raw.get("seat") or {}
        window = raw.get("window") or {}

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
        )

        doors_condition = DoorsCondition(
            locked=locked,
            driver_door_open=door_open(0),
            passenger_door_open=door_open(1),
            rear_left_door_open=door_open(2),
            rear_right_door_open=door_open(3),
            trunk_open=door.get("trunk") not in (None, 0),
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
                heating_level=_as_int(heating) or 0,
                ventilation_level=_as_int(data.get("ventStatus")) or 0,
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

        climate = ClimateCondition(
            power_on=hvac.get("acStatus") not in (None, 0),
            target_temperature_c=target_temp / 10 if target_temp is not None else None,
            steering_wheel_heater_on=steering_heater not in (None, 0),
            steering_wheel_heater_level=_as_int(status.get("steeringWheelHeaterLevel")) or 0,
        )

        last_updated = _as_int(raw.get("lastUpdatedAt"))

        return VehicleCondition(
            car_id=vehicle_id,
            vin=raw.get("vin") or "",
            total_odometer_km=_as_float(status.get("totalMileage")),
            battery=battery,
            doors=doors_condition,
            windows=windows_condition,
            seats=seats_condition,
            climate=climate,
            tires=tires_condition,
            last_updated_timestamp=last_updated // 1000 if last_updated is not None else None,
            raw_data=raw,
        )

    def _load_private_key(self):
        if not self.private_key_pem:
            raise DeepalAuthError("Login private key is required to sign commands.")
        return serialization.load_pem_private_key(
            self.private_key_pem.encode(), password=None
        )

    def sign_payload(
        self, payload: dict[str, Any], omit_keys: Optional[set[str]] = None
    ) -> str:
        """Sign a command payload with the login keypair."""
        private_key = self._load_private_key()
        omitted = omit_keys or set()
        parts = []
        for key in sorted(payload):
            if key == "sign" or key in omitted:
                continue
            value = payload[key]
            if isinstance(value, bool):
                value = str(value).lower()
            parts.append(f"{key}={value}")
        canonical = "&".join(parts)
        signature = private_key.sign(
            canonical.encode(), padding.PKCS1v15(), hashes.SHA256()
        )
        return base64.b64encode(signature).decode()

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
        return private_key.decrypt(ciphertext, padding.PKCS1v15()).decode().strip()

    async def check_control_code(self, control_pin: str) -> str:
        """Exchange the remote-control PIN for an rcToken."""
        data = await self._request(
            INTL_CHECK_CONTROL_CODE,
            json_data={"safeCode": self.encrypt_request_value(control_pin)},
            auth_required=True,
        )
        if not isinstance(data, dict) or not data.get("rcToken"):
            raise DeepalAuthError("Control-code check did not return an rcToken.")
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
            raise DeepalAuthError("Login private key is required to sign commands.")
        if require_rc_token and not self.rc_token:
            if not self.control_pin:
                raise DeepalAuthError("Control PIN is required for this command.")
            await self.check_control_code(self.control_pin)

        serial_data = await self.get_serial_data(serial_type)
        serial_no = self.decrypt_serial_no(serial_data)
        signed_payload = {
            **payload,
            "rcToken": self.rc_token or "",
            "seriralNo": serial_no,
            "vehicleId": vehicle_id,
        }
        signed_payload["sign"] = self.sign_payload(
            signed_payload, omit_keys=sign_omit_keys
        )

        data = await self._request(path, json_data=signed_payload, auth_required=True)
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

    async def control_result(self, vehicle_id: str, command_id: str) -> dict[str, Any]:
        """Fetch the status of a signed command."""
        data = await self._request(
            INTL_CONTROL_RESULT,
            json_data={"vehicleId": vehicle_id, "commandId": command_id},
            auth_required=True,
        )
        return data if isinstance(data, dict) else {}
