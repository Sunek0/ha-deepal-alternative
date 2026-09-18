"""Config flow for Changan Deepal integration."""

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .deepal import DeepalClient, DeepalIntlClient, DeepalAuthError, DeepalError
from .const import (
    DOMAIN,
    PLATFORM_SDA,
    PLATFORM_INTL,
    CONF_PLATFORM,
    CONF_PHONE,
    CONF_COUNTRY,
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_CAC_TOKEN,
    CONF_PRIVATE_KEY,
    CONF_CONTROL_PIN,
    CONF_USER_ID,
    DEFAULT_COUNTRY,
)

_LOGGER = logging.getLogger(__name__)

PLATFORM_OPTIONS = {
    PLATFORM_SDA: "SDA (China)",
    PLATFORM_INTL: "International (Europe)",
}


def _build_client(user_input: dict[str, Any]) -> DeepalClient | DeepalIntlClient:
    token = user_input[CONF_ACCESS_TOKEN].strip()
    platform = user_input.get(CONF_PLATFORM, PLATFORM_SDA)

    if platform == PLATFORM_INTL:
        client = DeepalIntlClient(
            country=user_input.get(CONF_COUNTRY) or DEFAULT_COUNTRY,
        )
        client.access_token = token
        client.refresh_token = (user_input.get(CONF_REFRESH_TOKEN) or "").strip() or None
        client.cac_token = (user_input.get(CONF_CAC_TOKEN) or "").strip() or None
        client.private_key_pem = (user_input.get(CONF_PRIVATE_KEY) or "").strip() or None
        client.control_pin = (user_input.get(CONF_CONTROL_PIN) or "").strip() or None
        return client

    return DeepalClient(access_token=token)


class DeepalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Changan Deepal."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow."""
        self._phone: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step (platform and credentials)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            token = user_input.get(CONF_ACCESS_TOKEN, "").strip()
            phone = user_input.get(CONF_PHONE) or ""

            client = _build_client(user_input)
            try:
                vehicles = await client.get_vehicles()

                await self.async_set_unique_id(token[:10])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"Deepal Account ({len(vehicles)} vehicle/s)",
                    data={
                        CONF_PLATFORM: user_input.get(CONF_PLATFORM, PLATFORM_SDA),
                        CONF_ACCESS_TOKEN: token,
                        CONF_REFRESH_TOKEN: (user_input.get(CONF_REFRESH_TOKEN) or "").strip(),
                        CONF_CAC_TOKEN: (user_input.get(CONF_CAC_TOKEN) or "").strip(),
                        CONF_USER_ID: (user_input.get(CONF_USER_ID) or "").strip(),
                        CONF_PRIVATE_KEY: (user_input.get(CONF_PRIVATE_KEY) or "").strip(),
                        CONF_CONTROL_PIN: (user_input.get(CONF_CONTROL_PIN) or "").strip(),
                        CONF_COUNTRY: user_input.get(CONF_COUNTRY) or DEFAULT_COUNTRY,
                        CONF_PHONE: phone,
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
                vol.Required(CONF_PLATFORM, default=PLATFORM_SDA): vol.In(PLATFORM_OPTIONS),
                vol.Required(CONF_ACCESS_TOKEN): str,
                vol.Optional(CONF_REFRESH_TOKEN, default=""): str,
                vol.Optional(CONF_CAC_TOKEN, default=""): str,
                vol.Optional(CONF_USER_ID, default=""): str,
                vol.Optional(CONF_PRIVATE_KEY, default=""): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=True)
                ),
                vol.Optional(CONF_CONTROL_PIN, default=""): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Optional(CONF_COUNTRY, default=DEFAULT_COUNTRY): str,
                vol.Optional(CONF_PHONE, default=""): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )
