"""The readable view the app publishes for Home Assistant.

The app sends it only when the user switched "show in Home Assistant" on.
Everything in it is checked and cut to size here, because it comes from the
network.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

VIEW_VERSION = 1
MAX_DEVICES = 5000
MAX_HOMES = 50
MAX_ROOMS = 1000

_ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_QR = re.compile(r"^MT:[0-9A-Z.\-]{8,200}$")
_MANUAL = re.compile(r"^(\d{11}|\d{21})$")


class ViewError(ValueError):
    """The view is not usable."""


def _text(value: Any, limit: int = 200) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())[:limit]
    return cleaned or None


def _day(value: Any) -> str | None:
    if not isinstance(value, str) or not _DATE.match(value):
        return None
    try:
        date.fromisoformat(value)
    except ValueError:
        return None
    return value


def _id(value: Any) -> str:
    if not isinstance(value, str) or not _ID.match(value):
        raise ViewError("bad id")
    return value


def parse_view(raw: bytes) -> dict:
    """Checks a published view and returns the cleaned version.

    Codes are kept only if the view says ``includeCodes`` and they have the
    shape of a Matter code.
    """
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as err:
        raise ViewError("not json") from err
    if not isinstance(data, dict) or data.get("version") != VIEW_VERSION:
        raise ViewError("unsupported version")
    include_codes = data.get("includeCodes") is True
    homes_in = data.get("homes")
    if not isinstance(homes_in, list) or len(homes_in) > MAX_HOMES:
        raise ViewError("bad homes")

    homes: list[dict] = []
    seen_devices: set[str] = set()
    device_count = 0
    for home in homes_in:
        if not isinstance(home, dict):
            raise ViewError("bad home")
        rooms = []
        room_names: dict[str, str] = {}
        for room in (home.get("rooms") or [])[:MAX_ROOMS]:
            if not isinstance(room, dict):
                continue
            room_id = _id(room.get("id"))
            name = _text(room.get("name")) or room_id
            room_names[room_id] = name
            rooms.append({"id": room_id, "name": name, "floor": _text(room.get("floor"))})
        devices = []
        for dev in home.get("devices") or []:
            if not isinstance(dev, dict):
                continue
            device_count += 1
            if device_count > MAX_DEVICES:
                raise ViewError("too many devices")
            dev_id = _id(dev.get("id"))
            if dev_id in seen_devices:
                continue
            seen_devices.add(dev_id)
            room_id = dev.get("roomId")
            room_id = room_id if isinstance(room_id, str) and room_id in room_names else None
            entry = {
                "id": dev_id,
                "name": _text(dev.get("name")) or dev_id,
                "type": _text(dev.get("type"), 60),
                "roomId": room_id,
                "manufacturer": _text(dev.get("manufacturer")),
                "model": _text(dev.get("model")),
                "firmware": _text(dev.get("firmware"), 60),
                "purchaseDate": _day(dev.get("purchaseDate")),
                "warrantyUntil": _day(dev.get("warrantyUntil")),
                "battery": _text(dev.get("battery"), 60),
                "qr": None,
                "manual": None,
            }
            if include_codes:
                qr = dev.get("qr")
                manual = dev.get("manual")
                if isinstance(qr, str) and _QR.match(qr):
                    entry["qr"] = qr
                if isinstance(manual, str) and _MANUAL.match(manual):
                    entry["manual"] = manual
            devices.append(entry)
        homes.append(
            {
                "id": _id(home.get("id")),
                "name": _text(home.get("name")) or "Home",
                "rooms": rooms,
                "devices": devices,
            }
        )
    return {
        "version": VIEW_VERSION,
        "generatedAt": _text(data.get("generatedAt"), 40),
        "includeCodes": include_codes,
        "homes": homes,
    }


def without_codes(view: dict) -> dict:
    """The view with every code removed, for use outside the admin panel."""
    return {
        **view,
        "includeCodes": False,
        "homes": [
            {
                **home,
                "devices": [
                    {**dev, "qr": None, "manual": None} for dev in home["devices"]
                ],
            }
            for home in view["homes"]
        ],
    }


def days_left(warranty_until: str | None, today: date) -> int | None:
    if warranty_until is None:
        return None
    return (date.fromisoformat(warranty_until) - today).days
