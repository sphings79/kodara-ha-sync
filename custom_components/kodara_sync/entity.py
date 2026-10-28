"""Entities for the devices and homes in the published view."""

from __future__ import annotations

from datetime import date

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, SIGNAL_VIEW_UPDATED
from .runtime import KodaraRuntime
from .view import days_left


class KodaraEntity(Entity):
    """Base: follows the view, no polling."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, runtime: KodaraRuntime, unique_id: str, translation_key: str):
        self._runtime = runtime
        self._attr_unique_id = unique_id
        self._attr_translation_key = translation_key

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_VIEW_UPDATED, self._changed)
        )

    @callback
    def _changed(self) -> None:
        if self.hass is not None and self.entity_id:
            self.async_write_ha_state()


class KodaraDeviceEntity(KodaraEntity):
    """An entity of one Kodara device."""

    def __init__(self, runtime: KodaraRuntime, device_id: str, key: str) -> None:
        super().__init__(runtime, f"{runtime.entry.entry_id}_{device_id}_{key}", key)
        self._device_id = device_id

    @property
    def _found(self):
        return self._runtime.devices.get(self._device_id)

    @property
    def available(self) -> bool:
        return self._found is not None

    @property
    def device_info(self) -> DeviceInfo:
        found = self._found
        info = DeviceInfo(identifiers={(DOMAIN, self._device_id)})
        if found is not None:
            _home, _room, dev = found
            info["name"] = dev["name"]
            info["manufacturer"] = dev["manufacturer"]
            info["model"] = dev["model"]
            info["sw_version"] = dev["firmware"]
        return info

    @property
    def extra_state_attributes(self) -> dict | None:
        found = self._found
        if found is None:
            return None
        home, room, dev = found
        return {
            "home": home["name"],
            "room": room,
            "device_type": dev["type"],
            "purchase_date": dev["purchaseDate"],
            "battery": dev["battery"],
        }

    def _days_left(self) -> int | None:
        found = self._found
        if found is None:
            return None
        return days_left(found[2]["warrantyUntil"], self._runtime.today)

    def _warranty_date(self) -> date | None:
        found = self._found
        if found is None or found[2]["warrantyUntil"] is None:
            return None
        return date.fromisoformat(found[2]["warrantyUntil"])
