"""Config flow for Changan Deepal integration."""

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import OptionsFlowWithReload
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .deepal import (
    AuthToken,
    DeepalAuthError,
    DeepalClient,
    DeepalError,
    DeepalIntlClient,
    DeepalRateLimitError,
    Vehicle,
)
from .const import (
    DOMAIN,
    PLATFORM_SDA,
    PLATFORM_INTL,
    CONF_PLATFORM,
    CONF_PHONE,
    CONF_EMAIL,
    CONF_LOGIN_METHOD,
    CONF_COUNTRY,
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_CAC_TOKEN,
    CONF_PRIVATE_KEY,
    CONF_CONTROL_PIN,
    CONF_DEVICE_ID,
    CONF_OS_VERSION,
    CONF_TSP_TOKEN_SOURCE,
    CONF_ENVIRONMENT,
    CONF_SEND_TIMESTAMPS,
    CONF_USER_ID,
    CONF_VEHICLE_ID,
    CONF_SCAN_INTERVAL,
    CONF_ENABLE_API_LOGGING,
    CONF_ENABLE_MQTT_CONTROLS,
    DEFAULT_COUNTRY,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_OS_VERSION,
    DEFAULT_TSP_TOKEN_SOURCE,
    DEFAULT_ENVIRONMENT,
    DEFAULT_SEND_TIMESTAMPS,
)
from .deepal.endpoints import INTL_ENVIRONMENTS

_LOGGER = logging.getLogger(__name__)

PLATFORM_OPTIONS = {
    PLATFORM_SDA: "SDA (China)",
    PLATFORM_INTL: "International (Europe)",
}

LOGIN_METHOD_EMAIL = "email"
LOGIN_METHOD_PHONE = "phone"
LOGIN_METHOD_OPTIONS = {
    LOGIN_METHOD_EMAIL: "Email code",
    LOGIN_METHOD_PHONE: "Phone/SMS code",
}

COUNTRY_OPTIONS = {
    "ES": "España (+34)",
    "PT": "Portugal (+351)",
    "GB": "United Kingdom (+44)",
    "IE": "Ireland (+353)",
    "FR": "France (+33)",
    "DE": "Germany (+49)",
    "IT": "Italy (+39)",
    "NL": "Netherlands (+31)",
    "BE": "Belgium (+32)",
    "LU": "Luxembourg (+352)",
    "CH": "Switzerland (+41)",
    "AT": "Austria (+43)",
    "IL": "Israel (+972)",
}

COUNTRY_DIAL_CODES = {
    "ES": "34",
    "PT": "351",
    "GB": "44",
    "IE": "353",
    "FR": "33",
    "DE": "49",
    "IT": "39",
    "NL": "31",
    "BE": "32",
    "LU": "352",
    "CH": "41",
    "AT": "43",
    "IL": "972",
}


def _login_error(err: DeepalError) -> str:
    """Map a login failure to a user-facing form error key."""
    if isinstance(err, DeepalRateLimitError):
        return "too_many_codes"
    message = str(err)
    if "CAC_1_1_01_024" in message:
        return "account_not_registered"
    if "APP_1_1_07_002" in message:
        return "bad_code"
    if isinstance(err, DeepalAuthError):
        return "invalid_auth"
    return "cannot_connect"


class DeepalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Changan Deepal."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow."""
        self._pending_login: dict[str, Any] = {}

    # ------------------------------------------------------------------ user
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step (platform selection)."""
        if user_input is not None:
            if user_input[CONF_PLATFORM] == PLATFORM_INTL:
                return await self.async_step_intl_method()
            return await self.async_step_sda()

        schema = vol.Schema(
            {
                vol.Required(CONF_PLATFORM, default=PLATFORM_SDA): vol.In(
                    PLATFORM_OPTIONS
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    # ------------------------------------------------------------------- SDA
    async def async_step_sda(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure an SDA entry with a pasted access token."""
        errors: dict[str, str] = {}

        if user_input is not None:
            token = user_input.get(CONF_ACCESS_TOKEN, "").strip()
            client = DeepalClient(access_token=token)
            try:
                vehicles = await client.get_vehicles()
                await self.async_set_unique_id(token[:10])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Deepal Account ({len(vehicles)} vehicle/s)",
                    data={
                        CONF_PLATFORM: PLATFORM_SDA,
                        CONF_ACCESS_TOKEN: token,
                        CONF_COUNTRY: user_input.get(CONF_COUNTRY) or DEFAULT_COUNTRY,
                        CONF_PHONE: user_input.get(CONF_PHONE) or "",
                    },
                )
            except DeepalAuthError:
                errors["base"] = "invalid_auth"
            except DeepalError:
                errors["base"] = "cannot_connect"
            finally:
                await client.close()

        schema = vol.Schema(
            {
                vol.Required(CONF_ACCESS_TOKEN): str,
                vol.Optional(CONF_COUNTRY, default=DEFAULT_COUNTRY): str,
                vol.Optional(CONF_PHONE, default=""): str,
            }
        )
        return self.async_show_form(step_id="sda", data_schema=schema, errors=errors)

    # ----------------------------------------------------------- international
    async def async_step_intl_method(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Choose the international login method."""
        if user_input is not None:
            if user_input[CONF_LOGIN_METHOD] == LOGIN_METHOD_EMAIL:
                return await self.async_step_intl_email()
            return await self.async_step_intl_phone()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_LOGIN_METHOD, default=LOGIN_METHOD_EMAIL
                ): vol.In(LOGIN_METHOD_OPTIONS),
            }
        )
        return self.async_show_form(step_id="intl_method", data_schema=schema)

    async def async_step_intl_email(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Request an email verification code."""
        errors: dict[str, str] = {}
        if user_input is not None:
            country = user_input.get(CONF_COUNTRY, DEFAULT_COUNTRY)
            email = str(user_input[CONF_EMAIL]).strip()
            client = DeepalIntlClient(country=country)
            try:
                await client.request_email_code(email)
            except DeepalError as err:
                _LOGGER.warning("Deepal email code request failed: %s", err)
                errors["base"] = _login_error(err)
            else:
                self._pending_login = {
                    CONF_COUNTRY: country,
                    CONF_EMAIL: email,
                    CONF_LOGIN_METHOD: LOGIN_METHOD_EMAIL,
                }
                return await self.async_step_intl_email_code()
            finally:
                await client.close()

        schema = vol.Schema(
            {
                vol.Required(CONF_COUNTRY, default=DEFAULT_COUNTRY): vol.In(
                    COUNTRY_OPTIONS
                ),
                vol.Required(CONF_EMAIL): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.EMAIL)
                ),
            }
        )
        return self.async_show_form(
            step_id="intl_email", data_schema=schema, errors=errors
        )

    async def async_step_intl_email_code(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Complete the email login with the verification code."""
        errors: dict[str, str] = {}
        if user_input is not None:
            info = self._pending_login
            client = DeepalIntlClient(country=info.get(CONF_COUNTRY, DEFAULT_COUNTRY))
            try:
                token = await client.login_with_email_code(
                    info[CONF_EMAIL],
                    str(user_input["auth_code"]).strip(),
                    sales_country=info[CONF_COUNTRY],
                )
            except DeepalError as err:
                errors["base"] = _login_error(err)
                await client.close()
            else:
                if client.private_key_pem is None:
                    await client.close()
                    errors["base"] = "cannot_connect"
                else:
                    return await self._async_finish_intl_login(
                        client, token, info, step_id="intl_email_code", errors=errors
                    )

        schema = vol.Schema({vol.Required("auth_code"): str})
        return self.async_show_form(
            step_id="intl_email_code", data_schema=schema, errors=errors
        )

    async def async_step_intl_phone(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Request an SMS verification code."""
        errors: dict[str, str] = {}
        if user_input is not None:
            country = user_input.get(CONF_COUNTRY, DEFAULT_COUNTRY)
            mobile = str(user_input[CONF_PHONE]).strip()
            dial_code = COUNTRY_DIAL_CODES[country]
            client = DeepalIntlClient(country=country)
            try:
                await client.request_sms_code(mobile, dial_code)
            except DeepalError as err:
                _LOGGER.warning("Deepal SMS code request failed: %s", err)
                errors["base"] = _login_error(err)
            else:
                self._pending_login = {
                    CONF_COUNTRY: country,
                    CONF_PHONE: mobile,
                    "dial_code": dial_code,
                    CONF_LOGIN_METHOD: LOGIN_METHOD_PHONE,
                }
                return await self.async_step_intl_sms_code()
            finally:
                await client.close()

        schema = vol.Schema(
            {
                vol.Required(CONF_COUNTRY, default=DEFAULT_COUNTRY): vol.In(
                    COUNTRY_OPTIONS
                ),
                vol.Required(CONF_PHONE): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEL)
                ),
            }
        )
        return self.async_show_form(
            step_id="intl_phone", data_schema=schema, errors=errors
        )

    async def async_step_intl_sms_code(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Complete the SMS login with the verification code."""
        errors: dict[str, str] = {}
        if user_input is not None:
            info = self._pending_login
            client = DeepalIntlClient(country=info.get(CONF_COUNTRY, DEFAULT_COUNTRY))
            try:
                token = await client.login_with_sms_code(
                    info[CONF_PHONE],
                    str(user_input["auth_code"]).strip(),
                    info["dial_code"],
                    sales_country=info[CONF_COUNTRY],
                )
            except DeepalError as err:
                errors["base"] = _login_error(err)
                await client.close()
            else:
                if client.private_key_pem is None:
                    await client.close()
                    errors["base"] = "cannot_connect"
                else:
                    return await self._async_finish_intl_login(
                        client, token, info, step_id="intl_sms_code", errors=errors
                    )

        schema = vol.Schema({vol.Required("auth_code"): str})
        return self.async_show_form(
            step_id="intl_sms_code", data_schema=schema, errors=errors
        )

    async def _async_finish_intl_login(
        self,
        client: DeepalIntlClient,
        token: AuthToken,
        info: dict[str, Any],
        *,
        step_id: str,
        errors: dict[str, str],
    ) -> FlowResult:
        """Validate the account and create or reauthenticate the entry."""
        try:
            vehicles = await client.get_vehicles()
        except DeepalError as err:
            errors["base"] = _login_error(err)
            await client.close()
            return self.async_show_form(
                step_id=step_id,
                data_schema=vol.Schema({vol.Required("auth_code"): str}),
                errors=errors,
            )
        if not vehicles:
            await client.close()
            errors["base"] = "no_vehicles"
            return self.async_show_form(
                step_id=step_id,
                data_schema=vol.Schema({vol.Required("auth_code"): str}),
                errors=errors,
            )

        vehicle: Vehicle = vehicles[0]
        data_updates = {
            CONF_ACCESS_TOKEN: token.access_token,
            CONF_REFRESH_TOKEN: token.refresh_token or "",
            CONF_CAC_TOKEN: token.cac_token or "",
            CONF_USER_ID: token.user_id or client.user_id or "",
            CONF_PRIVATE_KEY: client.private_key_pem or "",
            CONF_DEVICE_ID: client.device_id,
            CONF_VEHICLE_ID: vehicle.car_id,
            CONF_COUNTRY: info.get(CONF_COUNTRY, DEFAULT_COUNTRY),
            CONF_EMAIL: info.get(CONF_EMAIL, ""),
            CONF_PHONE: info.get(CONF_PHONE, ""),
        }
        await client.close()

        if self.source == config_entries.SOURCE_REAUTH:
            entry = self._get_reauth_entry()
            configured = entry.data.get(CONF_VEHICLE_ID)
            if configured and vehicle.car_id != configured:
                return self.async_show_form(
                    step_id=step_id,
                    data_schema=vol.Schema({vol.Required("auth_code"): str}),
                    errors={"base": "wrong_account"},
                )
            return self.async_update_reload_and_abort(
                entry, data_updates=data_updates, reason="reauth_successful"
            )

        await self.async_set_unique_id(vehicle.vin or vehicle.car_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=vehicle.car_name or vehicle.series_name or "Changan Deepal",
            data={
                CONF_PLATFORM: PLATFORM_INTL,
                CONF_ACCESS_TOKEN: data_updates[CONF_ACCESS_TOKEN],
                CONF_REFRESH_TOKEN: data_updates[CONF_REFRESH_TOKEN],
                CONF_CAC_TOKEN: data_updates[CONF_CAC_TOKEN],
                CONF_USER_ID: data_updates[CONF_USER_ID],
                CONF_PRIVATE_KEY: data_updates[CONF_PRIVATE_KEY],
                CONF_DEVICE_ID: data_updates[CONF_DEVICE_ID],
                CONF_VEHICLE_ID: data_updates[CONF_VEHICLE_ID],
                CONF_COUNTRY: data_updates[CONF_COUNTRY],
                CONF_EMAIL: data_updates[CONF_EMAIL],
                CONF_PHONE: data_updates[CONF_PHONE],
                CONF_CONTROL_PIN: "",
            },
        )

    # ------------------------------------------------------------- reauth
    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Start the reauthentication flow."""
        entry = self._get_reauth_entry()
        if entry.data.get(CONF_PLATFORM, PLATFORM_SDA) == PLATFORM_INTL:
            return await self.async_step_intl_method()
        return await self.async_step_sda_reauth()

    async def async_step_sda_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Reauthenticate an SDA entry with a new access token."""
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input.get(CONF_ACCESS_TOKEN, "").strip()
            client = DeepalClient(access_token=token)
            try:
                await client.get_vehicles()
            except DeepalAuthError:
                errors["base"] = "invalid_auth"
            except DeepalError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates={CONF_ACCESS_TOKEN: token},
                    reason="reauth_successful",
                )
            finally:
                await client.close()

        return self.async_show_form(
            step_id="sda_reauth",
            data_schema=vol.Schema({vol.Required(CONF_ACCESS_TOKEN): str}),
            errors=errors,
        )

    # ------------------------------------------------------------- options
    @staticmethod
    @config_entries.callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OptionsFlowWithReload:
        """Create the options flow."""
        return DeepalOptionsFlow()


class DeepalOptionsFlow(OptionsFlowWithReload):
    """Options for Changan Deepal entries."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage integration options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=30,
                        max=3600,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
                vol.Optional(
                    CONF_CONTROL_PIN, default=options.get(CONF_CONTROL_PIN, "")
                ): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD
                    )
                ),
                vol.Optional(
                    CONF_ENABLE_API_LOGGING,
                    default=options.get(CONF_ENABLE_API_LOGGING, False),
                ): bool,
                vol.Optional(
                    CONF_ENABLE_MQTT_CONTROLS,
                    default=options.get(CONF_ENABLE_MQTT_CONTROLS, False),
                ): bool,
                vol.Optional(
                    CONF_OS_VERSION,
                    default=options.get(CONF_OS_VERSION, DEFAULT_OS_VERSION),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["15", "14", "13", "12", "11", "10", "9"],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_TSP_TOKEN_SOURCE,
                    default=options.get(
                        CONF_TSP_TOKEN_SOURCE, DEFAULT_TSP_TOKEN_SOURCE
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["access", "cac", "cac_user_id", "ca_user_id"],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_ENVIRONMENT,
                    default=options.get(CONF_ENVIRONMENT, DEFAULT_ENVIRONMENT),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=environment.id, label=environment.label
                            )
                            for environment in INTL_ENVIRONMENTS.values()
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_SEND_TIMESTAMPS,
                    default=options.get(
                        CONF_SEND_TIMESTAMPS, DEFAULT_SEND_TIMESTAMPS
                    ),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
