"""Sensors: warranty date per device, device count per home."""

from __future__ import annotations

from datetime import date

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_VIEW_UPDATED
from .entity import KodaraDeviceEntity, KodaraEntity
from .runtime import KodaraRuntime


class WarrantyUntilSensor(KodaraDeviceEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, runtime: KodaraRuntime, device_id: str) -> None:
        super().__init__(runtime, device_id, "warranty_until")

    @property
    def native_value(self) -> date | None:
        return self._warranty_date()


class HomeDevicesSensor(KodaraEntity, SensorEntity):
    _attr_icon = "mdi:devices"
    _attr_native_unit_of_measurement = "devices"

    def __init__(self, runtime: KodaraRuntime, home_id: str) -> None:
        super().__init__(
            runtime, f"{runtime.entry.entry_id}_home_{home_id}_devices", "home_devices"
        )
        self._home_id = home_id

    @property
    def available(self) -> bool:
        return self._home_id in self._runtime.homes

    @property
    def device_info(self) -> DeviceInfo:
        home = self._runtime.homes.get(self._home_id)
        info = DeviceInfo(identifiers={(DOMAIN, f"home:{self._home_id}")})
        if home is not None:
            info["name"] = home["name"]
        return info

    @property
    def native_value(self) -> int | None:
        home = self._runtime.homes.get(self._home_id)
        return None if home is None else len(home["devices"])

    @property
    def extra_state_attributes(self) -> dict | None:
        home = self._runtime.homes.get(self._home_id)
        return None if home is None else {"rooms": len(home["rooms"])}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    runtime: KodaraRuntime = hass.data[DOMAIN][entry.entry_id]
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        wanted: dict[str, KodaraEntity] = {}
        for home_id in runtime.homes:
            sensor = HomeDevicesSensor(runtime, home_id)
            wanted[sensor.unique_id] = sensor
        for device_id in runtime.devices:
            sensor = WarrantyUntilSensor(runtime, device_id)
            wanted[sensor.unique_id] = sensor
        known.intersection_update(wanted)
        fresh = [e for uid, e in wanted.items() if uid not in known]
        known.update(e.unique_id for e in fresh)
        if fresh:
            async_add_entities(fresh)

    _add_new()
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_VIEW_UPDATED, _add_new)
    )
