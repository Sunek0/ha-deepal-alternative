"""Config flow for the Deepal Alternative integration."""

import hashlib
import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult, OptionsFlowWithReload
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import section
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import selector
from homeassistant.helpers.translation import async_get_translations

from .deepal import (
    AuthToken,
    DeepalAPIError,
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
    CONF_PUBLIC_KEY,
    CONF_CONTROL_PIN,
    CONF_DEVICE_ID,
    CONF_ENVIRONMENT,
    CONF_USER_ID,
    CONF_VEHICLE_ID,
    CONF_SCAN_INTERVAL,
    CONF_ENABLE_API_LOGGING,
    CONF_ENABLE_DIAGNOSTICS_CAPTURE,
    CONF_DIAGNOSTICS_ACTION,
    CONF_DIAGNOSTICS_CONFIRM_DELETE,
    CONF_ENABLE_LOCATION,
    CONF_WAKE,
    CONF_SHOW_PANEL,
    DEFAULT_COUNTRY,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_ENVIRONMENT,
    DEFAULT_WAKE,
    DEFAULT_SHOW_PANEL,
    DEFAULT_ENABLE_LOCATION,
    DIAGNOSTICS_ACTION_DELETE,
    DIAGNOSTICS_ACTION_DOWNLOAD,
    DIAGNOSTICS_ACTION_NEW,
    DIAGNOSTICS_ACTION_NONE,
    DIAGNOSTICS_ACTIONS,
)
from .deepal.endpoints import INTL_ENVIRONMENTS
from .diagnostics_capture import async_download_url, async_get_capture_manager

_LOGGER = logging.getLogger(__name__)

DEFAULT_PLATFORM = PLATFORM_INTL
DIAGNOSTICS_SECTION = "diagnostics"
DIAGNOSTICS_ACTION_TRANSLATION_KEY = "diagnostics_action"


def _format_size(value: int | float) -> str:
    """Render a byte count for the options form."""
    size = float(value or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{int(size)} B"

PLATFORM_OPTIONS = {
    PLATFORM_INTL: "International (Europe)",
    PLATFORM_SDA: "SDA (China)",
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
    "GR": "Greece (+30)",
    "NL": "Netherlands (+31)",
    "BE": "Belgium (+32)",
    "LU": "Luxembourg (+352)",
    "CH": "Switzerland (+41)",
    "AT": "Austria (+43)",
    "IL": "Israel (+972)",
    "AU": "Australia (+61)",
}

COUNTRY_DIAL_CODES = {
    "ES": "34",
    "PT": "351",
    "GB": "44",
    "IE": "353",
    "FR": "33",
    "DE": "49",
    "IT": "39",
    "GR": "30",
    "NL": "31",
    "BE": "32",
    "LU": "352",
    "CH": "41",
    "AT": "43",
    "IL": "972",
    "AU": "61",
}


def _environment_selector() -> selector.SelectSelector:
    """Return the regional environment dropdown."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                selector.SelectOptionDict(value=environment.id, label=environment.label)
                for environment in INTL_ENVIRONMENTS.values()
            ],
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


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


def _mask(value: str) -> str:
    """Mask an email address or phone number for display in the flow."""
    text = (value or "").strip()
    if not text:
        return ""
    if "@" in text:
        local, _, domain = text.partition("@")
        visible = local[:2]
        return f"{visible}{'*' * max(len(local) - len(visible), 0)}@{domain}"
    if len(text) <= 3:
        return "*" * len(text)
    return f"{'*' * (len(text) - 3)}{text[-3:]}"


async def _control_pin_validation_error(
    stored_pin: str, user_input: dict[str, Any], client: Any
) -> dict[str, str]:
    """Validate a changed control PIN against the account.

    Only a non-empty PIN different from the stored one is checked: clearing the
    field or keeping the current PIN never re-checks, because the PIN exchange
    consumes one of the account's attempts. Returns an options-form error dict
    (empty when the PIN is fine or cannot be checked with this client).
    """
    pin = str(user_input.get(CONF_CONTROL_PIN) or "")
    if not pin or pin == stored_pin:
        return {}
    if not isinstance(client, DeepalIntlClient) or not client.private_key_pem:
        return {}
    try:
        await client.check_control_code(pin)
    except DeepalRateLimitError:
        return {"base": "pin_rate_limited"}
    except (DeepalAuthError, DeepalAPIError):
        return {"base": "invalid_pin"}
    return {}


def _vehicle_device_entry(
    hass: HomeAssistant, car_id: str
) -> config_entries.ConfigEntry | None:
    """Return the config entry that owns a vehicle device, if any."""
    registry = dr.async_get(hass)
    # 2026.3 only has async_get_device; newer releases deprecate it because
    # identifiers are no longer unique across config entries, so prefer the
    # plural lookup when the running Home Assistant provides it.
    async_get_devices = getattr(registry, "async_get_devices", None)
    if async_get_devices is not None:
        # 2026.8 and newer: a device belongs to a single config entry,
        # available as config_entry_id. primary_config_entry is reported as
        # deprecated from 2026.10 and removed in 2027.10.
        for device in async_get_devices(identifiers={(DOMAIN, car_id)}):
            if device.config_entry_id is not None:
                return hass.config_entries.async_get_entry(device.config_entry_id)
        return None

    # 2026.3-2026.7: identifiers are globally unique and the device carries its
    # primary config entry, which is not deprecated on those versions.
    device = registry.async_get_device(identifiers={(DOMAIN, car_id)})
    if device is not None and device.primary_config_entry is not None:
        return hass.config_entries.async_get_entry(device.primary_config_entry)
    return None


def _sda_unique_id(phone: str, vehicles: list[Vehicle], token: str) -> str:
    """Return the stable unique id for an SDA entry.

    The account phone (digits only) is the preferred identifier, followed by a
    vehicle VIN. Accounts with neither fall back to an opaque digest of the
    access token: it cannot be replayed as a credential and no readable token
    fragment lands in the config entry or entity registries.
    """
    digits = "".join(character for character in phone if character.isdigit())
    if digits:
        return f"sda_phone_{digits}"
    vin = next((vehicle.vin for vehicle in vehicles if vehicle.vin), "")
    if vin:
        return f"sda_vin_{vin}"
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"sda_token_{digest[:16]}"


def _panel_schema() -> vol.Schema:
    """Schema of the sidebar panel question (disabled by default)."""
    return vol.Schema(
        {
            vol.Optional(CONF_SHOW_PANEL, default=DEFAULT_SHOW_PANEL): bool,
        }
    )


class DeepalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Deepal Alternative."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow."""
        self._pending_login: dict[str, Any] = {}
        self._reauth_identity: dict[str, Any] = {}
        self._pending_title = ""
        self._pending_data: dict[str, Any] = {}

    # ------------------------------------------------------------------ user
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step (platform selection)."""
        if user_input is not None:
            if user_input[CONF_PLATFORM] == PLATFORM_INTL:
                return await self.async_step_intl_method()
            return await self.async_step_sda()

        schema = vol.Schema(
            {
                vol.Required(CONF_PLATFORM, default=DEFAULT_PLATFORM): vol.In(
                    PLATFORM_OPTIONS
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    # ------------------------------------------------------------------ panel
    async def async_step_panel(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask whether to add the vehicle panel to the sidebar."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._pending_title,
                data=self._pending_data,
                options={
                    CONF_SHOW_PANEL: bool(
                        user_input.get(CONF_SHOW_PANEL, DEFAULT_SHOW_PANEL)
                    )
                },
            )
        return self.async_show_form(step_id="panel", data_schema=_panel_schema())

    # ------------------------------------------------------------------- SDA
    async def async_step_sda(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure an SDA entry with a pasted access token."""
        errors: dict[str, str] = {}

        if user_input is not None:
            token = user_input.get(CONF_ACCESS_TOKEN, "").strip()
            client = DeepalClient(access_token=token)
            try:
                vehicles = await client.get_vehicles()
                await self.async_set_unique_id(
                    _sda_unique_id(user_input.get(CONF_PHONE, ""), vehicles, token)
                )
                self._abort_if_unique_id_configured()
                for vehicle in vehicles:
                    if _vehicle_device_entry(self.hass, vehicle.car_id) is not None:
                        return self.async_abort(reason="already_configured")
                self._pending_title = f"Deepal Account ({len(vehicles)} vehicle/s)"
                self._pending_data = {
                    CONF_PLATFORM: PLATFORM_SDA,
                    CONF_ACCESS_TOKEN: token,
                    CONF_COUNTRY: user_input.get(CONF_COUNTRY) or DEFAULT_COUNTRY,
                    CONF_PHONE: user_input.get(CONF_PHONE) or "",
                    CONF_VEHICLE_ID: vehicles[0].car_id if vehicles else "",
                }
                return await self.async_step_panel()
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
    ) -> ConfigFlowResult:
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

    def _intl_login_client(
        self, country: str, environment: str | None = None
    ) -> DeepalIntlClient:
        """Build a client reusing the reauth entry identity, when present."""
        client = DeepalIntlClient(
            country=country,
            environment=(
                environment
                or self._reauth_identity.get(CONF_ENVIRONMENT)
                or DEFAULT_ENVIRONMENT
            ),
            device_id=self._reauth_identity.get(CONF_DEVICE_ID),
            private_key_pem=self._reauth_identity.get(CONF_PRIVATE_KEY),
            public_key=self._reauth_identity.get(CONF_PUBLIC_KEY),
        )
        stored_private_key = self._reauth_identity.get(CONF_PRIVATE_KEY)
        if stored_private_key:
            try:
                client.set_login_keypair(
                    stored_private_key,
                    self._reauth_identity.get(CONF_PUBLIC_KEY),
                )
            except (ValueError, TypeError) as err:
                _LOGGER.warning(
                    "Deepal reauthentication found an unusable stored login "
                    "private key (%s); a new keypair will be registered on login",
                    err,
                )
                client.private_key_pem = None
                client.public_key = None
        return client

    async def async_step_intl_email(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Request an email verification code."""
        errors: dict[str, str] = {}
        if user_input is not None:
            country = user_input.get(CONF_COUNTRY, DEFAULT_COUNTRY)
            environment = user_input.get(CONF_ENVIRONMENT, DEFAULT_ENVIRONMENT)
            email = str(user_input[CONF_EMAIL]).strip()
            client = self._intl_login_client(country, environment)
            try:
                await client.request_email_code(email)
            except DeepalError as err:
                _LOGGER.warning("Deepal email code request failed: %s", err)
                errors["base"] = _login_error(err)
            else:
                self._pending_login = {
                    CONF_COUNTRY: country,
                    CONF_ENVIRONMENT: environment,
                    CONF_EMAIL: email,
                    CONF_LOGIN_METHOD: LOGIN_METHOD_EMAIL,
                }
                return await self.async_step_intl_code_menu()
            finally:
                await client.close()

        return self._intl_email_form(errors)

    def _intl_email_form(self, errors: dict[str, str] | None = None) -> ConfigFlowResult:
        """Render the email destination form with the pending values."""
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_COUNTRY,
                    default=self._pending_login.get(CONF_COUNTRY, DEFAULT_COUNTRY),
                ): vol.In(COUNTRY_OPTIONS),
                vol.Optional(
                    CONF_ENVIRONMENT,
                    default=(
                        self._pending_login.get(CONF_ENVIRONMENT)
                        or self._reauth_identity.get(
                            CONF_ENVIRONMENT, DEFAULT_ENVIRONMENT
                        )
                    ),
                ): _environment_selector(),
                vol.Required(
                    CONF_EMAIL,
                    default=self._pending_login.get(CONF_EMAIL, ""),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.EMAIL)
                ),
            }
        )
        return self.async_show_form(
            step_id="intl_email", data_schema=schema, errors=errors or {}
        )

    async def async_step_intl_email_code(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Complete the email login with the verification code."""
        errors: dict[str, str] = {}
        if user_input is not None:
            info = self._pending_login
            client = self._intl_login_client(
                info.get(CONF_COUNTRY, DEFAULT_COUNTRY),
                info.get(CONF_ENVIRONMENT),
            )
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
                        client, token, info
                    )

        schema = vol.Schema({vol.Required("auth_code"): str})
        return self.async_show_form(
            step_id="intl_email_code", data_schema=schema, errors=errors
        )

    async def async_step_intl_phone(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Request an SMS verification code."""
        errors: dict[str, str] = {}
        if user_input is not None:
            country = user_input.get(CONF_COUNTRY, DEFAULT_COUNTRY)
            environment = user_input.get(CONF_ENVIRONMENT, DEFAULT_ENVIRONMENT)
            mobile = str(user_input[CONF_PHONE]).strip()
            dial_code = COUNTRY_DIAL_CODES[country]
            client = self._intl_login_client(country, environment)
            try:
                await client.request_sms_code(mobile, dial_code)
            except DeepalError as err:
                _LOGGER.warning("Deepal SMS code request failed: %s", err)
                errors["base"] = _login_error(err)
            else:
                self._pending_login = {
                    CONF_COUNTRY: country,
                    CONF_ENVIRONMENT: environment,
                    CONF_PHONE: mobile,
                    "dial_code": dial_code,
                    CONF_LOGIN_METHOD: LOGIN_METHOD_PHONE,
                }
                return await self.async_step_intl_code_menu()
            finally:
                await client.close()

        return self._intl_phone_form(errors)

    def _intl_phone_form(self, errors: dict[str, str] | None = None) -> ConfigFlowResult:
        """Render the phone destination form with the pending values."""
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_COUNTRY,
                    default=self._pending_login.get(CONF_COUNTRY, DEFAULT_COUNTRY),
                ): vol.In(COUNTRY_OPTIONS),
                vol.Optional(
                    CONF_ENVIRONMENT,
                    default=(
                        self._pending_login.get(CONF_ENVIRONMENT)
                        or self._reauth_identity.get(
                            CONF_ENVIRONMENT, DEFAULT_ENVIRONMENT
                        )
                    ),
                ): _environment_selector(),
                vol.Required(
                    CONF_PHONE,
                    default=self._pending_login.get(CONF_PHONE, ""),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEL)
                ),
            }
        )
        return self.async_show_form(
            step_id="intl_phone", data_schema=schema, errors=errors or {}
        )

    def _intl_login_method(self) -> str:
        """Return the pending international login method."""
        return self._pending_login.get(CONF_LOGIN_METHOD, LOGIN_METHOD_EMAIL)

    def _intl_code_menu_options(self) -> list[str]:
        """Return the code menu options for the pending login method."""
        if self._intl_login_method() == LOGIN_METHOD_PHONE:
            return ["intl_sms_code", "intl_code_resend", "intl_sms_change"]
        return ["intl_email_code", "intl_code_resend", "intl_email_change"]

    def _intl_destination(self) -> str:
        """Return the pending destination (email or mobile) for display."""
        if self._intl_login_method() == LOGIN_METHOD_PHONE:
            return self._pending_login.get(CONF_PHONE, "")
        return self._pending_login.get(CONF_EMAIL, "")

    def _intl_code_menu(self) -> ConfigFlowResult:
        """Show the post-request menu: enter, resend or correct the destination."""
        return self.async_show_menu(
            step_id="intl_code_menu",
            menu_options=self._intl_code_menu_options(),
            description_placeholders={"destination": _mask(self._intl_destination())},
        )

    async def async_step_intl_code_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer entering the code, resending it or changing the destination."""
        return self._intl_code_menu()

    async def async_step_intl_code_resend(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Resend the verification code to the pending destination."""
        info = self._pending_login
        country = info.get(CONF_COUNTRY, DEFAULT_COUNTRY)
        client = self._intl_login_client(country, info.get(CONF_ENVIRONMENT))
        errors: dict[str, str] = {}
        try:
            if self._intl_login_method() == LOGIN_METHOD_PHONE:
                dial_code = info.get("dial_code") or COUNTRY_DIAL_CODES.get(country, "")
                await client.request_sms_code(info.get(CONF_PHONE, ""), dial_code)
            else:
                await client.request_email_code(info.get(CONF_EMAIL, ""))
        except DeepalError as err:
            _LOGGER.warning("Deepal code resend failed: %s", err)
            errors["base"] = _login_error(err)
        finally:
            await client.close()
        if errors:
            if self._intl_login_method() == LOGIN_METHOD_PHONE:
                return self._intl_phone_form(errors)
            return self._intl_email_form(errors)
        return await self.async_step_intl_code_menu()

    async def async_step_intl_email_change(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reopen the email form to correct the address."""
        return await self.async_step_intl_email()

    async def async_step_intl_sms_change(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reopen the phone form to correct the mobile number."""
        return await self.async_step_intl_phone()

    async def async_step_intl_sms_code(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Complete the SMS login with the verification code."""
        errors: dict[str, str] = {}
        if user_input is not None:
            info = self._pending_login
            client = self._intl_login_client(
                info.get(CONF_COUNTRY, DEFAULT_COUNTRY),
                info.get(CONF_ENVIRONMENT),
            )
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
                        client, token, info
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
    ) -> ConfigFlowResult:
        """Validate the account and create or reauthenticate the entry."""
        try:
            vehicles = await client.get_vehicles()
        except DeepalError as err:
            _LOGGER.warning("Deepal vehicle list after login failed: %s", err)
            await client.close()
            return self.async_abort(reason="cannot_connect")
        if not vehicles:
            await client.close()
            return self.async_abort(reason="no_vehicles")

        if self.source != config_entries.SOURCE_REAUTH:
            for candidate in vehicles:
                if _vehicle_device_entry(self.hass, candidate.car_id) is not None:
                    await client.close()
                    return self.async_abort(reason="already_configured")

        entry = (
            self._get_reauth_entry()
            if self.source == config_entries.SOURCE_REAUTH
            else None
        )
        configured_vehicle_id: str | None = None
        if entry is not None:
            configured_user_id = entry.data.get(CONF_USER_ID)
            login_user_id = token.user_id or client.user_id
            if (
                configured_user_id
                and login_user_id
                and configured_user_id != login_user_id
            ):
                await client.close()
                return self.async_abort(reason="wrong_account")
            configured_vehicle_id = entry.data.get(CONF_VEHICLE_ID)

        vehicle: Vehicle = vehicles[0]
        if entry is not None and configured_vehicle_id:
            matched = next(
                (
                    candidate
                    for candidate in vehicles
                    if candidate.car_id == configured_vehicle_id
                ),
                None,
            )
            if matched is not None:
                vehicle = matched
        data_updates = {
            CONF_ACCESS_TOKEN: token.access_token,
            CONF_REFRESH_TOKEN: token.refresh_token or "",
            CONF_CAC_TOKEN: token.cac_token or "",
            CONF_USER_ID: token.user_id or client.user_id or "",
            CONF_PRIVATE_KEY: client.private_key_pem or "",
            CONF_PUBLIC_KEY: client.public_key or "",
            CONF_DEVICE_ID: client.device_id,
            CONF_VEHICLE_ID: vehicle.car_id,
            CONF_COUNTRY: info.get(CONF_COUNTRY, DEFAULT_COUNTRY),
            CONF_ENVIRONMENT: info.get(CONF_ENVIRONMENT, DEFAULT_ENVIRONMENT),
            CONF_EMAIL: info.get(CONF_EMAIL, ""),
            CONF_PHONE: info.get(CONF_PHONE, ""),
        }
        await client.close()

        if entry is not None:
            return self.async_update_reload_and_abort(
                entry, data_updates=data_updates, reason="reauth_successful"
            )

        await self.async_set_unique_id(vehicle.vin or vehicle.car_id)
        self._abort_if_unique_id_configured()
        self._pending_title = (
            vehicle.car_name or vehicle.series_name or "Deepal Alternative"
        )
        self._pending_data = {
            CONF_PLATFORM: PLATFORM_INTL,
            CONF_ACCESS_TOKEN: data_updates[CONF_ACCESS_TOKEN],
            CONF_REFRESH_TOKEN: data_updates[CONF_REFRESH_TOKEN],
            CONF_CAC_TOKEN: data_updates[CONF_CAC_TOKEN],
            CONF_USER_ID: data_updates[CONF_USER_ID],
            CONF_PRIVATE_KEY: data_updates[CONF_PRIVATE_KEY],
            CONF_PUBLIC_KEY: data_updates[CONF_PUBLIC_KEY],
            CONF_DEVICE_ID: data_updates[CONF_DEVICE_ID],
            CONF_VEHICLE_ID: data_updates[CONF_VEHICLE_ID],
            CONF_COUNTRY: data_updates[CONF_COUNTRY],
            CONF_ENVIRONMENT: data_updates[CONF_ENVIRONMENT],
            CONF_EMAIL: data_updates[CONF_EMAIL],
            CONF_PHONE: data_updates[CONF_PHONE],
            CONF_CONTROL_PIN: "",
        }
        return await self.async_step_panel()

    # ------------------------------------------------------------- reauth
    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Start the reauthentication flow."""
        entry = self._get_reauth_entry()
        if entry.data.get(CONF_PLATFORM, PLATFORM_SDA) == PLATFORM_INTL:
            self._reauth_identity = {
                CONF_DEVICE_ID: entry_data.get(CONF_DEVICE_ID),
                CONF_PRIVATE_KEY: entry_data.get(CONF_PRIVATE_KEY),
                CONF_PUBLIC_KEY: entry_data.get(CONF_PUBLIC_KEY),
                CONF_ENVIRONMENT: entry_data.get(CONF_ENVIRONMENT),
            }
            return await self.async_step_intl_method()
        return await self.async_step_sda_reauth()

    async def async_step_sda_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reauthenticate an SDA entry with a new access token."""
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input.get(CONF_ACCESS_TOKEN, "").strip()
            client = DeepalClient(access_token=token)
            try:
                vehicles = await client.get_vehicles()
            except DeepalAuthError:
                errors["base"] = "invalid_auth"
            except DeepalError:
                errors["base"] = "cannot_connect"
            else:
                entry = self._get_reauth_entry()
                if not vehicles:
                    return self.async_abort(reason="no_vehicles")
                configured_vehicle_id = entry.data.get(CONF_VEHICLE_ID)
                if configured_vehicle_id and not any(
                    vehicle.car_id == configured_vehicle_id for vehicle in vehicles
                ):
                    return self.async_abort(reason="wrong_account")
                data_updates: dict[str, Any] = {CONF_ACCESS_TOKEN: token}
                if not configured_vehicle_id:
                    data_updates[CONF_VEHICLE_ID] = vehicles[0].car_id
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates=data_updates,
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
    """Options for Deepal Alternative entries."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage integration options."""
        errors: dict[str, str] = {}
        options = dict(self.config_entry.options)
        if user_input is not None:
            options, action, confirm_delete = self._split_diagnostics(user_input)
            options.setdefault(
                CONF_ENABLE_DIAGNOSTICS_CAPTURE,
                self.config_entry.options.get(
                    CONF_ENABLE_DIAGNOSTICS_CAPTURE, False
                ),
            )
            errors = await self._async_validate_control_pin(options)
            if not errors:
                if action == DIAGNOSTICS_ACTION_NONE:
                    return self.async_create_entry(title="", data=options)
                errors = await self._async_apply_diagnostics_action(
                    action, confirm_delete, options
                )
                if not errors:
                    return self.async_show_form(
                        step_id="init",
                        data_schema=self._options_schema(options),
                        errors={},
                        description_placeholders={
                            "diagnostics_status": await self._diagnostics_status(
                                options
                            )
                        },
                    )

        return self.async_show_form(
            step_id="init",
            data_schema=self._options_schema(options),
            errors=errors,
            description_placeholders={
                "diagnostics_status": await self._diagnostics_status(options)
            },
        )

    @staticmethod
    def _split_diagnostics(
        user_input: dict[str, Any],
    ) -> tuple[dict[str, Any], str, bool]:
        """Flatten the diagnostics section and extract its action."""
        data = dict(user_input)
        diagnostics = dict(data.pop(DIAGNOSTICS_SECTION, {}) or {})
        action = str(
            diagnostics.pop(
                CONF_DIAGNOSTICS_ACTION,
                data.pop(CONF_DIAGNOSTICS_ACTION, DIAGNOSTICS_ACTION_NONE),
            )
        )
        confirm_delete = bool(
            diagnostics.pop(
                CONF_DIAGNOSTICS_CONFIRM_DELETE,
                data.pop(CONF_DIAGNOSTICS_CONFIRM_DELETE, False),
            )
        )
        data.update(diagnostics)
        if action not in DIAGNOSTICS_ACTIONS:
            action = DIAGNOSTICS_ACTION_NONE
        return data, action, confirm_delete

    async def _async_apply_diagnostics_action(
        self, action: str, confirm_delete: bool, options: dict[str, Any]
    ) -> dict[str, str]:
        """Apply one diagnostics action, save the options and reload the entry."""
        capture = async_get_capture_manager(self.hass, self.config_entry, create=True)
        capture.enabled = bool(
            options.get(CONF_ENABLE_DIAGNOSTICS_CAPTURE, False)
        )
        if action == DIAGNOSTICS_ACTION_DELETE and not confirm_delete:
            return {"base": "confirm_delete"}
        if action == DIAGNOSTICS_ACTION_DOWNLOAD:
            status = await capture.async_status()
            if not status.get("files"):
                return {"base": "no_diagnostics_file"}
        try:
            if action == DIAGNOSTICS_ACTION_NEW:
                await capture.async_new_segment()
            elif action == DIAGNOSTICS_ACTION_DELETE:
                await capture.async_delete_all()
            elif action == DIAGNOSTICS_ACTION_DOWNLOAD:
                await capture.async_flush()
        except Exception as err:  # noqa: BLE001 - surface it in the form
            _LOGGER.warning("Deepal diagnostics action %s failed: %s", action, err)
            return {"base": "diagnostics_action_failed"}

        previous = dict(self.config_entry.options)
        changed = dict(options) != previous
        self.hass.config_entries.async_update_entry(self.config_entry, options=options)
        if changed:
            try:
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            except Exception as err:  # noqa: BLE001 - the options are already saved
                _LOGGER.warning(
                    "Deepal options reload after diagnostics failed: %s", err
                )
                return {"base": "diagnostics_action_failed"}
        return {}

    async def _diagnostics_status(self, options: dict[str, Any]) -> str:
        """Build the Markdown status shown in the options form."""
        capture = async_get_capture_manager(self.hass, self.config_entry, create=True)
        status = await capture.async_status()
        translations = await self._async_status_translations()
        enabled = bool(options.get(CONF_ENABLE_DIAGNOSTICS_CAPTURE, False))
        lines = [
            self._status_text(
                translations, "enabled" if enabled else "disabled"
            ),
        ]
        files = status.get("files") or []
        if files:
            active = status.get("active_file")
            active_size = next(
                (
                    item.get("size", 0)
                    for item in files
                    if item.get("name") == active
                ),
                0,
            )
            if active:
                lines.append(
                    self._status_text(
                        translations,
                        "active_file",
                        name=active,
                        size=_format_size(active_size),
                    )
                )
            lines.append(
                self._status_text(
                    translations,
                    "files",
                    count=len(files),
                    size=_format_size(status.get("total_bytes", 0)),
                )
            )
            lines.append(
                f"[{self._status_text(translations, 'download')}]"
                f"({async_download_url(self.hass, self.config_entry.entry_id)})"
            )
        else:
            lines.append(self._status_text(translations, "no_file"))
        if status.get("dropped_events"):
            lines.append(
                self._status_text(
                    translations,
                    "dropped",
                    count=status["dropped_events"],
                )
            )
        if status.get("last_error"):
            lines.append(
                self._status_text(
                    translations,
                    "last_error",
                    error=status["last_error"],
                )
            )
        return "\n\n".join(lines)

    async def _async_status_translations(self) -> dict[str, str]:
        """Return the selector translations used by the status lines."""
        try:
            return await async_get_translations(
                self.hass,
                getattr(getattr(self.hass, "config", None), "language", "en")
                or "en",
                "common",
                [DOMAIN],
            )
        except Exception:  # noqa: BLE001 - the status still works with keys
            return {}

    @staticmethod
    def _status_text(
        translations: dict[str, str], key: str, **values: Any
    ) -> str:
        """Return one translated status line with its placeholders filled."""
        prefix = f"component.{DOMAIN}.common.diagnostics_status."
        text = translations.get(prefix + key) or key
        try:
            return text.format(**values)
        except (KeyError, IndexError):
            return text

    async def _async_validate_control_pin(
        self, user_input: dict[str, Any]
    ) -> dict[str, str]:
        """Verify a changed control PIN against the account before storing it.

        The check needs the loaded entry's client; an entry without runtime data
        (not set up, or already unloaded) cannot verify the PIN, so the options
        are accepted without the exchange and the command flow surfaces a wrong
        PIN with its own translated error.
        """
        runtime_data = getattr(self.config_entry, "runtime_data", None)
        coordinator = getattr(runtime_data, "coordinator", None)
        return await _control_pin_validation_error(
            self.config_entry.options.get(CONF_CONTROL_PIN, ""),
            user_input,
            getattr(coordinator, "client", None),
        )

    def _options_schema(self, options: Any) -> vol.Schema:
        """Build the options schema with the stored values as defaults."""
        return vol.Schema(
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
                vol.Optional(DIAGNOSTICS_SECTION): section(
                    vol.Schema(
                        {
                            vol.Optional(
                                CONF_ENABLE_DIAGNOSTICS_CAPTURE,
                                default=options.get(
                                    CONF_ENABLE_DIAGNOSTICS_CAPTURE, False
                                ),
                            ): bool,
                            vol.Optional(
                                CONF_DIAGNOSTICS_ACTION,
                                default=DIAGNOSTICS_ACTION_NONE,
                            ): selector.SelectSelector(
                                selector.SelectSelectorConfig(
                                    options=list(DIAGNOSTICS_ACTIONS),
                                    translation_key=DIAGNOSTICS_ACTION_TRANSLATION_KEY,
                                    mode=selector.SelectSelectorMode.DROPDOWN,
                                )
                            ),
                            vol.Optional(
                                CONF_DIAGNOSTICS_CONFIRM_DELETE, default=False
                            ): bool,
                        }
                    ),
                    {"collapsed": False},
                ),
                vol.Optional(
                    CONF_WAKE,
                    default=options.get(CONF_WAKE, DEFAULT_WAKE),
                ): bool,
                vol.Optional(
                    CONF_ENABLE_LOCATION,
                    default=options.get(
                        CONF_ENABLE_LOCATION, DEFAULT_ENABLE_LOCATION
                    ),
                ): bool,
                vol.Optional(
                    CONF_SHOW_PANEL,
                    default=options.get(CONF_SHOW_PANEL, True),
                ): bool,
                vol.Optional(
                    CONF_ENVIRONMENT,
                    default=(
                        options.get(CONF_ENVIRONMENT)
                        or self.config_entry.data.get(
                            CONF_ENVIRONMENT, DEFAULT_ENVIRONMENT
                        )
                    ),
                ): _environment_selector(),
            }
        )
