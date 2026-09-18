"""Client for the Changan Deepal international gateway (email login)."""

import asyncio
import base64
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
    INTL_BASE_URL,
    INTL_CA_BASE_URL,
    INTL_CA_GET_AUTH_TOKEN,
    INTL_CA_GET_CONN_CONF,
    INTL_CHECK_CONTROL_CODE,
    INTL_CONDITION_INQUIRY,
    INTL_CONTROL_AIR_CONDITIONER,
    INTL_CONTROL_RESULT,
    INTL_GET_MY_CARS,
    INTL_GET_SERIAL_NO,
    INTL_GET_SECURITY_CODE_STATUS,
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
    DeepalCommandAuthError,
    DeepalCommandNotReady,
    DeepalConnectionError,
    DeepalRateLimitError,
)
from deepal.redact import redact_for_log, safe_headers
from deepal.models import (
    AuthToken,
    BatteryCondition,
    ClimateCondition,
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
    S05_SERVICE_CODES,
    aes_cbc_decrypt,
    build_connect_packet,
    build_puback_packet,
    build_publish_packet,
    build_subscribe_packet,
    condition_request_payload,
    login_request_payload,
    new_request_id,
    normalize_s05_params,
    parse_publish,
    read_packet,
    secret_from_login_payload,
    topic_device_id,
)

logger = logging.getLogger("deepal_sdk")

INTL_APP_ID = "ca"
INTL_APP_TYPE = "Android"
INTL_APP_VERSION = "V1.12.0"
INTL_DEVICE_TYPE = "samsung"
INTL_OS_VERSION = "15"
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
        enable_api_logging: bool = False,
        httpx_client: Optional[httpx.AsyncClient] = None,
    ):
        self.country = country
        self.language = language
        self.app_version = app_version
        self.device_id = device_id or secrets.token_hex(16)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.enable_api_logging = enable_api_logging
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.cac_token: Optional[str] = None
        self.user_id: Optional[str] = None
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
        pub_body = "\n".join(
            line for line in public_pem.splitlines() if "BEGIN" not in line and "END" not in line
        ) + "\n"
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
            if self.cac_token:
                headers["X-Tsp-User-Token"] = self.cac_token
                headers["X-VCS-User-Token"] = self.cac_token
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
            response = await self._client.request(
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
            if str(code) == "COMMON_1_1_01_001" and path.endswith("/serial-no/get"):
                raise DeepalCommandAuthError(
                    "Remote command signing was rejected; log in again to register "
                    "a new command-signing key."
                )
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
        self.user_id = data.get("userId")

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
        self.user_id = data.get("userId") or self.user_id

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
                    protocol_type=item.get("protocolType") or item.get("protocol_type"),
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

        return self.parse_condition(raw, vehicle_id)

    def parse_condition(self, raw: dict[str, Any], vehicle_id: str) -> VehicleCondition:
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

        last_updated = _as_int(raw.get("lastUpdatedAt"))

        return VehicleCondition(
            car_id=vehicle_id,
            vin=raw.get("vin") or "",
            total_odometer_km=_as_float(status.get("totalMileage")),
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
        data = await self._request(
            INTL_CA_GET_CONN_CONF,
            json_data={
                "deviceId": self.device_id,
                "carId": vehicle_id,
                "deviceType": 1,
                "confTimestamp": 0,
                "deviceTimestamp": str(int(time.time() * 1000)),
            },
            auth_required=True,
            base_url=INTL_CA_BASE_URL,
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
        data = await self._request(
            INTL_CA_GET_AUTH_TOKEN,
            json_data={"userId": self.user_id},
            auth_required=True,
            base_url=INTL_CA_BASE_URL,
        )
        if not isinstance(data, dict) or not data.get("authToken"):
            raise DeepalAPIError("S05 MQTT auth response did not include authToken.")
        return str(data["authToken"])

    async def s05_mqtt_condition(self, vehicle_id: str) -> VehicleCondition:
        """Fetch a live S05 condition snapshot over MQTT."""
        config = await self.get_mqtt_config(vehicle_id)
        token = await self.get_mqtt_token()
        try:
            params = await self._read_s05_params(config, token)
        except (asyncio.TimeoutError, OSError, ssl.SSLError) as exc:
            raise DeepalAPIError(f"S05 MQTT telemetry failed: {exc}") from exc
        if not params:
            raise DeepalAPIError("S05 MQTT telemetry did not return vehicle condition.")
        return self.parse_condition(normalize_s05_params(params), vehicle_id)

    async def _read_s05_params(
        self, config: dict[str, Any], token: str
    ) -> dict[str, Any]:
        """Run one MQTT login + condition exchange and return the raw parameters."""
        info = ((config.get("mqttConnectionInfos") or [None])[0]) or {}
        cluster = ((info.get("clusterInfos") or [None])[0]) or {}
        host = str(cluster.get("brokerUrl", "")).replace("ssl://", "")
        port = int(cluster.get("brokerPort") or 8883)
        topics: list[str] = []
        login_topic: Optional[str] = None
        login_did: Optional[str] = None
        properties_topic: Optional[str] = None
        device_did: Optional[str] = None

        for topic_info in info.get("topicInfos") or []:
            msg_type = topic_info.get("msgType")
            for topic in topic_info.get("pubTopics") or []:
                if msg_type == "loginout" and "/loginout/req" in topic:
                    login_topic = topic
                    login_did = topic_device_id(topic)
                if msg_type == "properties" and "/properties/get/req" in topic:
                    properties_topic = topic
                    device_did = topic_device_id(topic)
            for topic in topic_info.get("subTopics") or []:
                if "/commands/" not in topic and "/set/" not in topic:
                    topics.append(topic)
                if device_did is None and "/properties/" in topic:
                    device_did = topic_device_id(topic)

        if not host or not login_topic or not login_did or not properties_topic or not device_did:
            raise DeepalAPIError(
                "S05 MQTT configuration did not include required topics."
            )

        context = ssl.create_default_context()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=context, server_hostname=host),
            timeout=self.timeout,
        )
        try:
            writer.write(build_connect_packet(login_did, login_did, token))
            await writer.drain()
            first, body = await asyncio.wait_for(
                read_packet(reader), timeout=self.timeout
            )
            rc = body[1] if first == 0x20 and len(body) >= 2 else None
            if rc != 0:
                raise DeepalAPIError(f"S05 MQTT broker rejected connection: rc={rc}")

            writer.write(build_subscribe_packet(1, sorted(set(topics))))
            await writer.drain()
            await asyncio.wait_for(read_packet(reader), timeout=self.timeout)

            login_req_id = new_request_id(login_did)
            writer.write(
                build_publish_packet(
                    login_topic, login_request_payload(login_did, login_req_id)
                )
            )
            await writer.drain()

            secret_key: Optional[str] = None
            partial: dict[str, Any] = {}
            requested = False
            loop = asyncio.get_running_loop()
            deadline = loop.time() + max(self.timeout, 20.0)

            while loop.time() < deadline:
                first, body = await asyncio.wait_for(
                    read_packet(reader), timeout=max(1.0, deadline - loop.time())
                )
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
                                    device_did, login_did, secret_key, req_id
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
        await self.get_security_code_status()
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
            "rcToken": self.rc_token or "",
            "seriralNo": serial_no,
            "vehicleId": vehicle_id,
        }
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

    async def control_result(self, vehicle_id: str, command_id: str) -> dict[str, Any]:
        """Fetch the status of a signed command."""
        data = await self._request(
            INTL_CONTROL_RESULT,
            json_data={"vehicleId": vehicle_id, "commandId": command_id},
            auth_required=True,
        )
        return data if isinstance(data, dict) else {}
