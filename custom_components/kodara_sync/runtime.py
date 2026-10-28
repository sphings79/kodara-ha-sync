"""The state of one Kodara Sync config entry."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .api import KodaraApi
from .const import (
    CONF_QUOTA_MB,
    CONF_WARRANTY_DAYS,
    DEFAULT_QUOTA_MB,
    DEFAULT_WARRANTY_DAYS,
    DOMAIN,
    SIGNAL_VIEW_UPDATED,
    STORAGE_DIR,
)
from .storage import KodaraStore
from .view import ViewError, parse_view, without_codes

_LOGGER = logging.getLogger(__name__)


class KodaraRuntime:
    """Holds the store, the published view and what is derived from it."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        quota = int(entry.options.get(CONF_QUOTA_MB, DEFAULT_QUOTA_MB)) * 1024 * 1024
        self.store = KodaraStore(Path(hass.config.path(STORAGE_DIR)), quota)
        self.api = KodaraApi(hass, self.store, self.set_view)
        self.view: dict | None = None
        self.public_view: dict | None = None
        # device id -> (home, room name, device)
        self.devices: dict[str, tuple[dict, str | None, dict]] = {}
        self.homes: dict[str, dict] = {}

    @property
    def warranty_days(self) -> int:
        return int(self.entry.options.get(CONF_WARRANTY_DAYS, DEFAULT_WARRANTY_DAYS))

    @property
    def today(self) -> date:
        return dt_util.now().date()

    async def async_start(self) -> None:
        await self.hass.async_add_executor_job(self.store.prepare)
        raw = await self.hass.async_add_executor_job(self.store.read_view)
        if raw is not None:
            try:
                self._apply(parse_view(raw))
            except ViewError:
                _LOGGER.warning("The stored Kodara view is not valid and is ignored")
        self.entry.async_on_unload(
            async_track_time_change(
                self.hass, self._new_day, hour=0, minute=5, second=0
            )
        )
        self._cleanup_devices()

    @callback
    def _new_day(self, _now) -> None:
        async_dispatcher_send(self.hass, SIGNAL_VIEW_UPDATED)

    @callback
    def set_view(self, view: dict | None) -> None:
        """Takes a new view (or none) and tells the entities."""
        self._apply(view)
        self._cleanup_devices()
        async_dispatcher_send(self.hass, SIGNAL_VIEW_UPDATED)

    def _apply(self, view: dict | None) -> None:
        self.view = view
        self.public_view = without_codes(view) if view else None
        self.devices = {}
        self.homes = {}
        if self.public_view is None:
            return
        for home in self.public_view["homes"]:
            self.homes[home["id"]] = home
            rooms = {r["id"]: r["name"] for r in home["rooms"]}
            for dev in home["devices"]:
                self.devices[dev["id"]] = (home, rooms.get(dev["roomId"]), dev)

    @callback
    def _cleanup_devices(self) -> None:
        """Brings the device registry in line with the view."""
        registry = dr.async_get(self.hass)
        wanted = set(self.devices) | {f"home:{h}" for h in self.homes}
        for device in dr.async_entries_for_config_entry(registry, self.entry.entry_id):
            ids = {i[1] for i in device.identifiers if i[0] == DOMAIN}
            if not ids:
                continue
            key = next(iter(ids))
            if key not in wanted:
                registry.async_remove_device(device.id)
                continue
            found = self.devices.get(key)
            if found is not None:
                _home, _room, dev = found
                registry.async_update_device(
                    device.id,
                    name=dev["name"],
                    manufacturer=dev["manufacturer"],
                    model=dev["model"],
                    sw_version=dev["firmware"],
                )
            elif key.startswith("home:"):
                registry.async_update_device(
                    device.id, name=self.homes[key[5:]]["name"]
                )
