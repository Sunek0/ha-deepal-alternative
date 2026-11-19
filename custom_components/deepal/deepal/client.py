"""Asynchronous HTTP Client for Changan Deepal API."""

import logging
import math
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Optional
import httpx

from .endpoints import (
    DEFAULT_BASE_URL,
    LOGIN_SMS_CODE,
    OAUTH_TOKEN_BIND,
    GET_MY_CARS,
    GET_CAR_FULL_CONDITION,
    REMOTE_CLIMATE_CONTROL,
    REMOTE_DOOR_LOCK,
)
from .exceptions import (
    DeepalAPIError,
    DeepalAuthError,
    DeepalConnectionError,
    DeepalRateLimitError,
    parse_retry_after,
)
from .models import (
    AuthToken,
    Vehicle,
    VehicleCondition,
    BatteryCondition,
    DoorsCondition,
    ClimateCondition,
)

logger = logging.getLogger("deepal_sdk")


def _optional_int(value: Any) -> Optional[int]:
    """Return an integer reading, or ``None`` when missing or unparsable.

    Numeric strings such as ``"85"``, ``"85.0"`` or ``"85.7"`` follow the same
    truncation as their float form; a non-finite value (``inf``, ``nan``) is
    unknown instead of an ``OverflowError`` that would abort the poll.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return int(number)


def _percentage(value: Any) -> Optional[int]:
    """Return a 0-100 percentage, or ``None`` when missing or out of range.

    The app uses a ``255`` "invalid" marker for the SDA battery. Pydantic
    rejects it for ``BatteryCondition.soc_percentage``, and a ``ValidationError``
    is not a ``DeepalError``: one impossible reading would abort the vehicle
    poll, so an impossible percentage is unknown instead.
    """
    number = _optional_int(value)
    return number if number is not None and 0 <= number <= 100 else None


def _text(value: Any) -> Optional[str]:
    """Return a string for a scalar field, or ``None`` when it is unusable."""
    if value is None or isinstance(value, (dict, list, tuple)):
        return None
    return value if isinstance(value, str) else str(value)


class DeepalClient:
    """Asynchronous client to interact with Changan Deepal Connected Vehicle API."""

    def __init__(
        self,
        access_token: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        httpx_client: Optional[httpx.AsyncClient] = None,
        on_exchange: Optional[Callable[[dict[str, Any]], None]] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.timeout = timeout
        self.on_exchange = on_exchange
        self._external_client = httpx_client is not None
        self._client = httpx_client or httpx.AsyncClient(timeout=timeout)

    def _emit_exchange(self, event: dict[str, Any]) -> None:
        """Deliver one structured exchange event to the optional callback."""
        callback = getattr(self, "on_exchange", None)
        if callback is None:
            return
        try:
            callback(event)
        except Exception:  # noqa: BLE001 - diagnostics must never break a call
            logger.exception("Deepal exchange callback failed")

    async def close(self) -> None:
        """Close the underlying HTTP client if managed internally."""
        if not self._external_client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self) -> "DeepalClient":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json;charset=utf-8",
            "Timestamp": str(int(time.time())),
            "Version": "1.12.0",
            "User-Agent": "MyChangan/1.12.0 (Android; Deepal S05)",
        }
        if self.access_token:
            # The SDA gateway authenticates with the VCS header and ignores
            # Authorization/token (verified live: without it the gateway
            # answers 40005 "X-VCS-User-Token cannot be empty").
            headers["X-VCS-User-Token"] = self.access_token
        return headers

    @staticmethod
    def _is_auth_failure(code: Any, message: str, *, authenticated: bool) -> bool:
        """Return whether an SDA business code means the session is unusable.

        ``46000`` is the gateway's expired/invalid-token code. ``40005`` is a
        generic missing-parameter code, so it only counts as an auth failure on
        an authenticated request whose message names the VCS user token.
        """
        if not authenticated:
            return False
        normalized = str(code)
        if normalized == "46000":
            return True
        lowered = message.lower().replace("_", "-")
        return normalized == "40005" and "vcs" in lowered and "token" in lowered

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict[str, Any]] = None,
        json_data: Optional[dict[str, Any]] = None,
        form_data: Optional[dict[str, Any]] = None,
        auth_required: bool = True,
    ) -> dict[str, Any]:
        """Perform an HTTP request with error handling and model parsing.

        Exactly one of ``json_data`` and ``form_data`` is expected. The SDA
        login endpoints consume ``application/x-www-form-urlencoded`` bodies;
        the rest of the API uses JSON.
        """
        if auth_required and not self.access_token:
            raise DeepalAuthError("Access token is required for this operation.")

        url = f"{self.base_url}{path}" if path.startswith("/") else path
        headers = self._get_headers()
        is_form = form_data is not None
        payload = form_data if is_form else json_data
        body = {"data": form_data} if is_form else {"json": json_data}
        if is_form:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        method = method.upper()
        started = time.monotonic()

        try:
            response = await self._client.request(
                method=method,
                url=url,
                params=params,
                headers=headers,
                timeout=self.timeout,
                **body,
            )
        except httpx.RequestError as exc:
            self._emit_exchange(
                {
                    "ts": datetime.now(UTC).isoformat(),
                    "kind": "rest",
                    "event": "error",
                    "client": "sda",
                    "method": method,
                    "path": path,
                    "url": url,
                    "query": params,
                    "request": payload,
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
                    "client": "sda",
                    "method": method,
                    "path": path,
                    "url": url,
                    "query": params,
                    "request": payload,
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
                    "client": "sda",
                    "method": method,
                    "path": path,
                    "url": url,
                    "query": params,
                    "request": payload,
                    "headers": headers,
                    "status": response.status_code,
                    "response": response.text[:2000],
                    "duration_ms": round((time.monotonic() - started) * 1000, 1),
                }
            )
            raise DeepalAuthError("Authentication token expired or invalid.")

        try:
            data = response.json()
        except ValueError as exc:
            self._emit_exchange(
                {
                    "ts": datetime.now(UTC).isoformat(),
                    "kind": "rest",
                    "event": "response",
                    "client": "sda",
                    "method": method,
                    "path": path,
                    "url": url,
                    "query": params,
                    "request": payload,
                    "headers": headers,
                    "status": response.status_code,
                    "response": response.text[:2000],
                    "error": "invalid_json",
                    "duration_ms": round((time.monotonic() - started) * 1000, 1),
                }
            )
            raise DeepalAPIError(
                f"Invalid JSON response: {response.text[:200]}",
                status_code=response.status_code,
            ) from exc

        self._emit_exchange(
            {
                "ts": datetime.now(UTC).isoformat(),
                "kind": "rest",
                "event": "response",
                "client": "sda",
                "method": method,
                "path": path,
                "url": url,
                "query": params,
                "request": payload,
                "headers": headers,
                "status": response.status_code,
                "response": data,
                "duration_ms": round((time.monotonic() - started) * 1000, 1),
            }
        )

        if not response.is_success or (isinstance(data, dict) and data.get("code") not in (0, 200, "0", "200", None)):
            code = data.get("code") if isinstance(data, dict) else response.status_code
            msg = data.get("msg") or data.get("message") or f"HTTP {response.status_code}"
            if self._is_auth_failure(
                code,
                str(msg),
                authenticated=auth_required and bool(self.access_token),
            ):
                raise DeepalAuthError(f"Authentication token expired or invalid: {msg}")
            raise DeepalAPIError(f"API Error: {msg}", status_code=response.status_code, code=code)

        return data

    async def request_sms_code(self, phone: str) -> bool:
        """Request SMS verification code for login.

        The SDA gateway requires an out-of-band captcha authorization code for
        this request, which the client does not implement; the call surfaces
        the gateway's captcha error as ``DeepalAPIError``.
        """
        payload = {"phone": phone}
        res = await self._request(
            "POST", LOGIN_SMS_CODE, form_data=payload, auth_required=False
        )
        return res.get("code") in (0, 200, "0", "200")

    async def login_with_code(self, phone: str, code: str) -> AuthToken:
        """Login using phone number and SMS verification code."""
        payload = {"phone": phone, "code": code}
        data = await self._request(
            "POST", OAUTH_TOKEN_BIND, form_data=payload, auth_required=False
        )
        result_data = data.get("data", {})
        token_str = result_data.get("token") or result_data.get("access_token")
        if not token_str:
            raise DeepalAuthError("Login response did not contain access token.")

        self.access_token = token_str
        return AuthToken(
            access_token=token_str,
            expires_in=result_data.get("expires_in"),
            user_id=result_data.get("user_id"),
        )

    async def get_vehicles(self) -> list[Vehicle]:
        """Fetch list of user's registered vehicles.

        An unusable payload (a missing, non-list or non-object ``data`` value)
        returns an empty list instead of leaking ``AttributeError``/
        ``TypeError``: the coordinator keeps the current vehicles when the
        account reports none, so the next refresh recovers without touching the
        registries.
        """
        res = await self._request("GET", GET_MY_CARS)
        car_list = res.get("data", []) if isinstance(res, dict) else []
        if isinstance(car_list, dict):
            car_list = car_list.get("list", [])
        if not isinstance(car_list, list):
            car_list = []

        vehicles = []
        for c in car_list:
            if not isinstance(c, dict):
                continue
            car_id = c.get("car_id") or c.get("carId") or c.get("id")
            if not car_id:
                continue
            vehicles.append(
                Vehicle(
                    car_id=str(car_id),
                    vin=_text(c.get("vin")) or "",
                    series_name=(
                        _text(c.get("series_name") or c.get("carModelName"))
                        or "Deepal S05"
                    ),
                    car_name=_text(c.get("car_name") or c.get("nickName")),
                    license_plate=_text(
                        c.get("car_num") or c.get("licensePlate")
                    ),
                    thumbnail_url=_text(
                        c.get("car_pic") or c.get("thumbnailUrl")
                    ),
                )
            )
        return vehicles

    async def get_vehicle_condition(
        self, car_id: str, vin: Optional[str] = None
    ) -> VehicleCondition:
        """Fetch full telemetry condition of a vehicle (battery, doors, mileage, etc.).

        ``vin`` is accepted for call compatibility with the international client
        (the coordinator passes it for every platform) and ignored: the SDA
        condition endpoint addresses vehicles by car id.
        """
        params = {"carId": car_id}
        res = await self._request("GET", GET_CAR_FULL_CONDITION, params=params)
        raw_data = res.get("data", {})

        # Parse telemetry parameters
        tot_milg = raw_data.get("CdcTotMilg") or raw_data.get("total_odometer")
        try:
            tot_milg_val = float(tot_milg) if tot_milg is not None else None
        except (ValueError, TypeError):
            tot_milg_val = None

        soc_val = raw_data.get("BatterySoc") or raw_data.get("battery_level")
        range_val = raw_data.get("RemainingRange") or raw_data.get("battery_range")

        battery = BatteryCondition(
            soc_percentage=_percentage(soc_val),
            remaining_range_km=_optional_int(range_val),
            charging_status=_text(raw_data.get("ChargingState")),
            charger_connected=bool(raw_data.get("ChargerPlugged", False)),
        )

        doors = DoorsCondition(
            locked=bool(raw_data.get("DoorsLocked", True)),
            driver_door_open=bool(raw_data.get("DoorFLOpen", False)),
            passenger_door_open=bool(raw_data.get("DoorFROpen", False)),
            rear_left_door_open=bool(raw_data.get("DoorRLOpen", False)),
            rear_right_door_open=bool(raw_data.get("DoorRROpen", False)),
            trunk_open=bool(raw_data.get("TrunkOpen", False)),
            hood_open=bool(raw_data.get("HoodOpen", False)),
        )

        climate = ClimateCondition(
            power_on=bool(raw_data.get("AcPowerOn", False)),
            target_temperature_c=raw_data.get("AcTargetTemp"),
        )

        return VehicleCondition(
            car_id=car_id,
            vin=_text(raw_data.get("vin")) or "",
            total_odometer_km=tot_milg_val,
            battery=battery,
            doors=doors,
            climate=climate,
            last_updated_timestamp=int(time.time()),
            raw_data=raw_data,
        )

    async def set_climate_control(self, car_id: str, power_on: bool, target_temp_c: Optional[float] = None) -> bool:
        """Send remote climate control command."""
        payload = {
            "carId": car_id,
            "acPower": 1 if power_on else 0,
            "targetTemp": target_temp_c,
        }
        res = await self._request("POST", REMOTE_CLIMATE_CONTROL, json_data=payload)
        return res.get("code") in (0, 200, "0", "200")

    async def set_door_lock(self, car_id: str, lock: bool) -> bool:
        """Send remote door lock/unlock command."""
        payload = {
            "carId": car_id,
            "action": "lock" if lock else "unlock",
        }
        res = await self._request("POST", REMOTE_DOOR_LOCK, json_data=payload)
        return res.get("code") in (0, 200, "0", "200")
