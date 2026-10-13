"""Repair flows for the Deepal Alternative integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.repairs import RepairsFlow, RepairsFlowResult
from homeassistant.core import HomeAssistant


class MqttReauthRepairFlow(RepairsFlow):
    """Start the entry's reauthentication flow for the MQTT user id issue."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> RepairsFlowResult:
        """Handle the first step of the fix flow."""
        if user_input is not None:
            entry = self.hass.config_entries.async_get_entry(self.data["entry_id"])
            if entry is not None:
                entry.async_start_reauth(self.hass)
            return self.async_create_entry(data={})

        return self.async_show_form(step_id="init", data_schema=vol.Schema({}))


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create the fix flow for the MQTT re-authentication issue."""
    return MqttReauthRepairFlow()
