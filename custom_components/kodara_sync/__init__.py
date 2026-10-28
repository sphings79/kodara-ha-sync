"""Kodara Sync: a sync folder for the Kodara Home app, and a view of its data."""

from __future__ import annotations

from pathlib import Path

import voluptuous as vol

from homeassistant.components import frontend, panel_custom, webhook, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback

from .const import CONF_WEBHOOK_ID, DOMAIN, PANEL_URL_PATH, STATIC_URL
from .runtime import KodaraRuntime

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]
_FRONTEND = Path(__file__).parent / "frontend"
_STATIC_FILES = ("kodara-panel.js", "qrcode.mjs")
_STATIC_DONE = f"{DOMAIN}_static_done"
_WS_DONE = f"{DOMAIN}_ws_done"


async def async_setup(hass: HomeAssistant, config) -> bool:
    return True


@websocket_api.websocket_command({vol.Required("type"): "kodara/view"})
@websocket_api.require_admin
@callback
def _ws_view(hass: HomeAssistant, connection, msg) -> None:
    """The full view, codes included, for the admin panel only."""
    runtimes = hass.data.get(DOMAIN, {})
    runtime = next(iter(runtimes.values()), None)
    connection.send_result(msg["id"], runtime.view if runtime else None)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    runtime = KodaraRuntime(hass, entry)
    await runtime.async_start()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime

    webhook.async_register(
        hass,
        DOMAIN,
        "Kodara Sync",
        entry.data[CONF_WEBHOOK_ID],
        runtime.api.handle,
        local_only=False,
        allowed_methods=["POST"],
    )

    if not hass.data.get(_WS_DONE):
        websocket_api.async_register_command(hass, _ws_view)
        hass.data[_WS_DONE] = True
    if not hass.data.get(_STATIC_DONE):
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(f"{STATIC_URL}/{name}", str(_FRONTEND / name), False)
                for name in _STATIC_FILES
            ]
        )
        hass.data[_STATIC_DONE] = True
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name="kodara-panel",
        frontend_url_path=PANEL_URL_PATH,
        sidebar_title="Kodara",
        sidebar_icon="mdi:qrcode-scan",
        module_url=f"{STATIC_URL}/kodara-panel.js",
        require_admin=True,
        embed_iframe=False,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def _reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        webhook.async_unregister(hass, entry.data[CONF_WEBHOOK_ID])
        frontend.async_remove_panel(hass, PANEL_URL_PATH)
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return ok
