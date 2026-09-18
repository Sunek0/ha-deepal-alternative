"""Asynchronous HTTP Client for Changan Deepal API."""

import logging
import time
from typing import Any, Optional
import httpx

from .endpoints import (
    DEFAULT_BASE_URL,
    LOGIN_SMS_CODE,
    OAUTH_TOKEN_BIND,
    GET_MY_CARS,
    GET_CAR_FULL_CONDITION,
    GET_CAR_STATUS,
    GET_HOME_CHARGER_STATUS,
    REMOTE_CLIMATE_CONTROL,
    REMOTE_DOOR_LOCK,
)
from .exceptions import (
    DeepalAPIError,
    DeepalAuthError,
    DeepalConnectionError,
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


class DeepalClient:
    """Asynchronous client to interact with Changan Deepal Connected Vehicle API."""

    def __init__(
        self,
        access_token: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 15.0,
        httpx_client: Optional[httpx.AsyncClient] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.timeout = timeout
        self._external_client = httpx_client is not None
        self._client = httpx_client or httpx.AsyncClient(timeout=timeout)

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
            headers["Authorization"] = f"Bearer {self.access_token}"
            headers["token"] = self.access_token
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict[str, Any]] = None,
        json_data: Optional[dict[str, Any]] = None,
        auth_required: bool = True,
    ) -> dict[str, Any]:
        """Perform an HTTP request with error handling and model parsing."""
        if auth_required and not self.access_token:
            raise DeepalAuthError("Access token is required for this operation.")

        url = f"{self.base_url}{path}" if path.startswith("/") else path
        headers = self._get_headers()

        try:
            response = await self._client.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                headers=headers,
            )
        except httpx.RequestError as exc:
            logger.error("Network error requesting %s: %s", url, exc)
            raise DeepalConnectionError(f"Failed to connect to Deepal API: {exc}") from exc

        if response.status_code in (401, 403):
            raise DeepalAuthError("Authentication token expired or invalid.")

        try:
            data = response.json()
        except ValueError as exc:
            raise DeepalAPIError(
                f"Invalid JSON response: {response.text[:200]}",
                status_code=response.status_code,
            ) from exc

        if not response.is_success or (isinstance(data, dict) and data.get("code") not in (0, 200, "0", "200", None)):
            code = data.get("code") if isinstance(data, dict) else response.status_code
            msg = data.get("msg") or data.get("message") or f"HTTP {response.status_code}"
            raise DeepalAPIError(f"API Error: {msg}", status_code=response.status_code, code=code)

        return data

    async def request_sms_code(self, phone: str) -> bool:
        """Request SMS verification code for login."""
        payload = {"phone": phone}
        res = await self._request("POST", LOGIN_SMS_CODE, json_data=payload, auth_required=False)
        return res.get("code") in (0, 200, "0", "200")

    async def login_with_code(self, phone: str, code: str) -> AuthToken:
        """Login using phone number and SMS verification code."""
        payload = {"phone": phone, "code": code}
        data = await self._request("POST", OAUTH_TOKEN_BIND, json_data=payload, auth_required=False)
        
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
        """Fetch list of user's registered vehicles."""
        res = await self._request("GET", GET_MY_CARS)
        car_list = res.get("data", [])
        if isinstance(car_list, dict):
            car_list = car_list.get("list", [])

        vehicles = []
        for c in car_list:
            vehicles.append(
                Vehicle(
                    car_id=str(c.get("car_id") or c.get("carId") or c.get("id")),
                    vin=c.get("vin") or "",
                    series_name=c.get("series_name") or c.get("carModelName") or "Deepal S05",
                    car_name=c.get("car_name") or c.get("nickName"),
                    license_plate=c.get("car_num") or c.get("licensePlate"),
                    thumbnail_url=c.get("car_pic") or c.get("thumbnailUrl"),
                )
            )
        return vehicles

    async def get_vehicle_condition(self, car_id: str) -> VehicleCondition:
        """Fetch full telemetry condition of a vehicle (battery, doors, mileage, etc.)."""
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
            soc_percentage=int(soc_val) if soc_val is not None else None,
            remaining_range_km=int(range_val) if range_val is not None else None,
            charging_status=raw_data.get("ChargingState"),
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
            vin=raw_data.get("vin") or "",
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
