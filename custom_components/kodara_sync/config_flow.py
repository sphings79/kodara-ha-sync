"""Setting up Kodara Sync from the UI."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.network import NoURLAvailableError

from .const import (
    CONF_QUOTA_MB,
    CONF_WARRANTY_DAYS,
    CONF_WEBHOOK_ID,
    DEFAULT_QUOTA_MB,
    DEFAULT_WARRANTY_DAYS,
    DOMAIN,
)


def webhook_address(hass: HomeAssistant, webhook_id: str) -> str:
    """The address to type into the app."""
    try:
        return webhook.async_generate_url(
            hass, webhook_id, allow_internal=True, allow_ip=True
        )
    except NoURLAvailableError:
        return webhook.async_generate_path(webhook_id)


class KodaraConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._webhook_id: str | None = None

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            self._webhook_id = webhook.async_generate_id()
            return await self.async_step_address()
        return self.async_show_form(step_id="user")

    async def async_step_address(self, user_input=None):
        assert self._webhook_id is not None
        if user_input is not None:
            return self.async_create_entry(
                title="Kodara Sync", data={CONF_WEBHOOK_ID: self._webhook_id}
            )
        return self.async_show_form(
            step_id="address",
            description_placeholders={
                "address": webhook_address(self.hass, self._webhook_id)
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return KodaraOptionsFlow()


class KodaraOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_WARRANTY_DAYS,
                        default=options.get(CONF_WARRANTY_DAYS, DEFAULT_WARRANTY_DAYS),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=365)),
                    vol.Required(
                        CONF_QUOTA_MB,
                        default=options.get(CONF_QUOTA_MB, DEFAULT_QUOTA_MB),
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=10240)),
                }
            ),
            description_placeholders={
                "address": webhook_address(
                    self.hass, self.config_entry.data[CONF_WEBHOOK_ID]
                )
            },
        )
