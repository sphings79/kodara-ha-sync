"""Binary sensor: the warranty ends soon."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_VIEW_UPDATED
from .entity import KodaraDeviceEntity
from .runtime import KodaraRuntime


class WarrantyExpiringSensor(KodaraDeviceEntity, BinarySensorEntity):
    """On from the threshold until the warranty has ended."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, runtime: KodaraRuntime, device_id: str) -> None:
        super().__init__(runtime, device_id, "warranty_expiring")

    @property
    def is_on(self) -> bool | None:
        left = self._days_left()
        if left is None:
            return None
        return 0 <= left <= self._runtime.warranty_days

    @property
    def extra_state_attributes(self) -> dict | None:
        attrs = super().extra_state_attributes
        if attrs is None:
            return None
        return {**attrs, "days_left": self._days_left()}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    runtime: KodaraRuntime = hass.data[DOMAIN][entry.entry_id]
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        wanted = {
            f"{entry.entry_id}_{device_id}_warranty_expiring": device_id
            for device_id in runtime.devices
        }
        known.intersection_update(wanted)
        fresh = [uid for uid in wanted if uid not in known]
        known.update(fresh)
        if fresh:
            async_add_entities(
                [WarrantyExpiringSensor(runtime, wanted[uid]) for uid in fresh]
            )

    _add_new()
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_VIEW_UPDATED, _add_new)
    )
