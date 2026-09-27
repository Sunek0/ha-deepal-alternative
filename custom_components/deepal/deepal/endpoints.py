"""API Endpoints and Base URLs for Changan Deepal API."""

from dataclasses import dataclass

# Base Hostnames
DEFAULT_BASE_URL = "https://pre-acenter.sda.changan.com.cn"
GATEWAY_BASE_URL = "https://pre-acenter.sda.changan.com.cn/app-apigw/store-sda-api/api/v2"
INTL_BASE_URL = "https://m.iov.changanauto.com.de"
INTL_CA_BASE_URL = "https://ca-m.iov.changanauto.com.de"
INTL_SDA_BASE_URL = "https://sda-m.iov.changanauto.com.de"


@dataclass(frozen=True)
class IntlEnvironment:
    """Regional gateway definition recovered from the app's LocalEnvironments."""

    id: str
    label: str
    app_id: str
    intl_base_url: str
    ca_base_url: str
    sda_base_url: str
    intl_path_prefix: str = "/intl-app-gw"


INTL_ENVIRONMENTS: dict[str, IntlEnvironment] = {
    environment.id: environment
    for environment in (
        IntlEnvironment(
            "release_eu",
            "Europe",
            "ca",
            "https://m.iov.changanauto.com.de",
            "https://ca-m.iov.changanauto.com.de",
            "https://sda-m.iov.changanauto.com.de",
        ),
        IntlEnvironment(
            "release_znm",
            "Latin America",
            "ca",
            "https://m.mx.changanauto.link",
            "https://m.mx.changanauto.link",
            "https://sda-m.mx.changanauto.link",
        ),
    )
}
DEFAULT_INTL_ENVIRONMENT = "release_eu"

LEGACY_INTL_ENVIRONMENTS: dict[str, str] = {
    "release_eu_mix": "release_eu",
    "preprod_eu": "release_eu",
    "release_ase": "release_eu",
    "release_ase_connect": "release_eu",
    "release_dlt": "release_eu",
    "release_st": "release_eu",
    "release_alq": "release_eu",
}


def get_intl_environment(environment: str) -> IntlEnvironment:
    """Return the environment definition or raise for an unknown identifier."""
    environment = LEGACY_INTL_ENVIRONMENTS.get(environment, environment)
    try:
        return INTL_ENVIRONMENTS[environment]
    except KeyError as exc:
        supported = ", ".join(sorted(INTL_ENVIRONMENTS))
        raise ValueError(
            f"Unknown international environment {environment!r}; supported: {supported}."
        ) from exc

# Authentication Endpoints
LOGIN_SMS_CODE = "/appauth/sda-app/api/user/login/code"
OAUTH_TOKEN_BIND = "/appauth/sda-app/api/v2/oauth2-login/token/bind"
OAUTH_THIRD_UNBIND = "/appauth/sda-app/api/v2/oauth2/third/unbind"
INTL_SEND_EMAIL_CODE = "/intl-app-gw/intl-app-auth/api/login/email-send-auth-code"
INTL_LOGIN_BY_EMAIL_CODE = "/intl-app-gw/intl-app-auth/api/login/email-code-in"
INTL_LOGIN_BY_EMAIL_PASSWORD = "/intl-app-gw/intl-app-auth/api/login/email-pass-in"
INTL_SEND_SMS_CODE = "/intl-app-gw/intl-app-auth/api/login/send-auth-code"
INTL_LOGIN_BY_MOBILE_CODE = "/intl-app-gw/intl-app-auth/api/login/login-by-mobile-code"
INTL_LOGIN_BY_MOBILE_PASSWORD = "/intl-app-gw/intl-app-auth/api/login/login-by-pwd"
INTL_LOGOUT = "/intl-app-gw/intl-app-auth/api/logout"
INTL_REFRESH_TOKEN = "/intl-app-gw/intl-app-auth/api/auth/refresh-token"

# International Vehicle Endpoints
INTL_GET_MY_CARS = "/intl-app-gw/intl-app-user/api/car/vehicles"
INTL_GET_VEHICLE_CONDITION = "/intl-app-gw/intl-app-car-condition/api/vehicle/condition"
# Per-vehicle function configuration (CarApi.getCarConfig in the 1.12.0 DEX)
INTL_GET_FUNCTION_CONFIG = "/intl-app-gw/intl-app-user/api/vehicle/function-config"

# International Control Endpoints
INTL_GET_SERIAL_NO = "/intl-app-gw/intl-app-car-control/api/serial-no/get"
INTL_CHECK_CONTROL_CODE = "/intl-app-gw/intl-app-car-control/api/security-code/check-code"
INTL_GET_SECURITY_CODE_STATUS = "/intl-app-gw/intl-app-car-control/api/security-code/get-status"
INTL_CONTROL_AIR_CONDITIONER = "/intl-app-gw/intl-app-car-control/api/control/air-conditioner"
INTL_CONDITION_INQUIRY = "/intl-app-gw/intl-app-car-control/api/control/condition-inquiry"
INTL_CONTROL_RESULT = "/intl-app-gw/intl-app-car-control/api/control/control-result"
INTL_CONTROL_DOORS = "/intl-app-gw/intl-app-car-control/api/control/doors"
INTL_CONTROL_WINDOWS = "/intl-app-gw/intl-app-car-control/api/control/windows"
INTL_CONTROL_TRUNK = "/intl-app-gw/intl-app-car-control/api/control/trunk"
INTL_CONTROL_FLASHING_HONKING = (
    "/intl-app-gw/intl-app-car-control/api/control/flashing-honking"
)
INTL_CHARGE_PERCENTAGE = "/intl-app-gw/intl-app-car-control/api/charge/percentage"
INTL_CHARGE_MODIFY_PLAN = "/intl-app-gw/intl-app-car-control/api/charge/modify-plan"
INTL_CHARGE_ADD_PLAN = "/intl-app-gw/intl-app-car-control/api/charge/add-plan"
INTL_CHARGE_DELETE_PLAN = "/intl-app-gw/intl-app-car-control/api/charge/delete-plan"
INTL_CHARGE_VALIDITY = "/intl-app-gw/intl-app-car-control/api/charge/validity"
INTL_CONTROL_DEFROST = "/intl-app-gw/intl-app-car-control/api/control/defrost"
INTL_CONTROL_SEATS_HEAT = "/intl-app-gw/intl-app-car-control/api/control/seats/heat"
INTL_CONTROL_SEATS_WIND = "/intl-app-gw/intl-app-car-control/api/control/seats/wind"
INTL_CONTROL_STEERING_WHEEL_HEAT = (
    "/intl-app-gw/intl-app-car-control/api/control/steering-wheel/heat"
)
INTL_CONTROL_FOTA_PLAN = "/intl-app-gw/intl-app-car-control/api/control/fota-plan"
INTL_DEPARTURE_ADD_PLAN = (
    "/intl-app-gw/intl-app-car-control/api/departure-plans/add-plan"
)
INTL_DEPARTURE_MODIFY_PLAN = (
    "/intl-app-gw/intl-app-car-control/api/departure-plans/modify-plan"
)
INTL_DEPARTURE_DELETE = "/intl-app-gw/intl-app-car-control/api/departure-plans/delete"
INTL_DEPARTURE_VALIDITY = (
    "/intl-app-gw/intl-app-car-control/api/departure-plans/validity"
)
INTL_DEPARTURE_ENABLED = (
    "/intl-app-gw/intl-app-car-control/api/departure-plans/enabled"
)

# International CA gateway (S05 MQTT telemetry bootstrap)
INTL_CA_GET_CONN_CONF = "/user-apigw/vot-connect-conf-center/api/device/getConnConf"
INTL_CA_GET_AUTH_TOKEN = "/user-apigw/vot-connect-auth-center/api/auth/getAuthTokenByUserId"
# App fallbacks recovered from the 1.12.0 DEX (MqttConstansKt)
INTL_CA_GET_CAR_CONF_FUNC = (
    "/user-apigw/vot-connect-conf-center/api/device/appGetCarConfFunc"
)
INTL_CA_APP_APIGW_GET_AUTH_TOKEN = (
    "/app-apigw/vot-auth/api/token/getAuthTokenByUserId"
)

# Digital key endpoints (ApiKt.java in the 1.12.0 DEX). The /app-apigw prefix is
# served by the regional SDA gateway, not by the CA host (verified live).
INTL_CA_GET_CAR_AUTH_LIST = (
    "/app-apigw/car-permission-api/api/v1/sda-app/car-auth/get-car-auth-list"
)
INTL_CA_GET_DIGITAL_KEY_SUPPORT = (
    "/app-apigw/sda-app-control/api/v2/sda-app/dk/query-supported-featured"
)

# Vehicle Information & Telemetry Endpoints
GET_MY_CARS = "/dae-terminal-mobile/api/v1/car/my-cars"
GET_CAR_STATUS = "/dae-terminal-mobile/api/v1/car/status"
GET_CAR_FULL_CONDITION = "/dae-terminal-mobile/api/v1/car/full-condition"
GET_CAR_SETTINGS = "/dae-terminal-mobile/api/v1/car/settings"

# Charging & Home Charger Endpoints
GET_HOME_CHARGER_STATUS = "/dae-terminal-mobile/api/v1/charger/home-status"
GET_CHARGE_HISTORY = "/dae-terminal-mobile/api/v1/charger/history"

# Control Commands Endpoints
REMOTE_CLIMATE_CONTROL = "/dae-terminal-mobile/api/v1/control/climate"
REMOTE_DOOR_LOCK = "/dae-terminal-mobile/api/v1/control/lock"
PARKING_COMMAND = "/dae-terminal-mobile/api/v1/control/parking"

REQUEST_ENCRYPTION_PUBLIC_KEY = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAkyhr43cBPTJ3jLiYsmbUwUp74cMJIOju5vqVzgtuK63Q99qV6iVT8wN5cXlyMtWI2mfOmhIao/fUN821im69MfOHsWXdqQEo5e9v654GPw+bju0pCphEPtD1I0VcyS34QkAu04urSun2U1q3Dr2OICLVWSnLa+01ioKxkaB0D209zXcls2eFQpvRAWm7xxVsoqzSwqp+neu5quOpn+eO/bW0TxcSQ8VZcDEUvadRTLSR0eOWgRuHIBiD2RGqPIPzKCm5A14q1qhxUZ8U0pmYe0Sx7eMy4RVe2iW7fnjc6pxTUMBkercSL26mevYouuCKqyie+LVQAtGa29RMl/lyiwIDAQAB"
)
