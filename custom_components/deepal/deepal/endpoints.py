"""API Endpoints and Base URLs for Changan Deepal API."""

# Base Hostnames
DEFAULT_BASE_URL = "https://pre-acenter.sda.changan.com.cn"
GATEWAY_BASE_URL = "https://pre-acenter.sda.changan.com.cn/app-apigw/store-sda-api/api/v2"
INTL_BASE_URL = "https://m.iov.changanauto.com.de"
INTL_CA_BASE_URL = "https://ca-m.iov.changanauto.com.de"

# Authentication Endpoints
LOGIN_SMS_CODE = "/appauth/sda-app/api/user/login/code"
OAUTH_TOKEN_BIND = "/appauth/sda-app/api/v2/oauth2-login/token/bind"
OAUTH_THIRD_UNBIND = "/appauth/sda-app/api/v2/oauth2/third/unbind"
INTL_SEND_EMAIL_CODE = "/intl-app-gw/intl-app-auth/api/login/email-send-auth-code"
INTL_LOGIN_BY_EMAIL_CODE = "/intl-app-gw/intl-app-auth/api/login/email-code-in"
INTL_SEND_SMS_CODE = "/intl-app-gw/intl-app-auth/api/login/send-auth-code"
INTL_LOGIN_BY_MOBILE_CODE = "/intl-app-gw/intl-app-auth/api/login/login-by-mobile-code"
INTL_REFRESH_TOKEN = "/intl-app-gw/intl-app-auth/api/auth/refresh-token"

# International Vehicle Endpoints
INTL_GET_MY_CARS = "/intl-app-gw/intl-app-user/api/car/vehicles"
INTL_GET_VEHICLE_CONDITION = "/intl-app-gw/intl-app-car-condition/api/vehicle/condition"

# International Control Endpoints
INTL_GET_SERIAL_NO = "/intl-app-gw/intl-app-car-control/api/serial-no/get"
INTL_CHECK_CONTROL_CODE = "/intl-app-gw/intl-app-car-control/api/security-code/check-code"
INTL_CONTROL_AIR_CONDITIONER = "/intl-app-gw/intl-app-car-control/api/control/air-conditioner"
INTL_CONDITION_INQUIRY = "/intl-app-gw/intl-app-car-control/api/control/condition-inquiry"
INTL_CONTROL_RESULT = "/intl-app-gw/intl-app-car-control/api/control/control-result"

# International CA gateway (S05 MQTT telemetry bootstrap)
INTL_CA_GET_CONN_CONF = "/user-apigw/vot-connect-conf-center/api/device/getConnConf"
INTL_CA_GET_AUTH_TOKEN = "/user-apigw/vot-connect-auth-center/api/auth/getAuthTokenByUserId"

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
