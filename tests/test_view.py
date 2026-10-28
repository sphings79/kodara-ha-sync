import json
from datetime import date

import pytest

from custom_components.kodara_sync.view import (
    ViewError,
    days_left,
    parse_view,
    without_codes,
)

QR = "MT:Y.K9042C00KA0648G00"


def make(**over):
    view = {
        "version": 1,
        "generatedAt": "2026-10-28T12:00:00Z",
        "includeCodes": True,
        "homes": [
            {
                "id": "h1",
                "name": "Zuhause",
                "rooms": [{"id": "r1", "name": "Wohnzimmer", "floor": "EG"}],
                "devices": [
                    {
                        "id": "d1",
                        "name": "Lampe",
                        "type": "light",
                        "roomId": "r1",
                        "manufacturer": "Acme",
                        "model": "X1",
                        "firmware": "1.2",
                        "purchaseDate": "2025-01-02",
                        "warrantyUntil": "2027-01-02",
                        "battery": None,
                        "qr": QR,
                        "manual": "34970112332",
                    }
                ],
            }
        ],
    }
    view.update(over)
    return json.dumps(view).encode()


def test_good_view_roundtrips():
    v = parse_view(make())
    dev = v["homes"][0]["devices"][0]
    assert dev["name"] == "Lampe" and dev["qr"] == QR and dev["manual"] == "34970112332"
    assert v["homes"][0]["rooms"][0]["floor"] == "EG"


def test_codes_are_dropped_unless_shared():
    v = parse_view(make(includeCodes=False))
    dev = v["homes"][0]["devices"][0]
    assert dev["qr"] is None and dev["manual"] is None and v["includeCodes"] is False


def test_codes_of_wrong_shape_are_dropped():
    raw = json.loads(make())
    raw["homes"][0]["devices"][0]["qr"] = "<script>alert(1)</script>"
    raw["homes"][0]["devices"][0]["manual"] = "12345"
    dev = parse_view(json.dumps(raw).encode())["homes"][0]["devices"][0]
    assert dev["qr"] is None and dev["manual"] is None


@pytest.mark.parametrize(
    "raw",
    [b"nope", b"[]", b'{"version": 2, "homes": []}', b'{"version": 1}'],
)
def test_bad_documents(raw):
    with pytest.raises(ViewError):
        parse_view(raw)


def test_bad_ids_are_refused():
    raw = json.loads(make())
    raw["homes"][0]["devices"][0]["id"] = "../x"
    with pytest.raises(ViewError):
        parse_view(json.dumps(raw).encode())


def test_text_is_cleaned_and_cut():
    raw = json.loads(make())
    raw["homes"][0]["devices"][0]["name"] = "  A\n\nB  " + "x" * 500
    raw["homes"][0]["devices"][0]["warrantyUntil"] = "2027-13-45"
    raw["homes"][0]["devices"][0]["roomId"] = "unknown-room"
    dev = parse_view(json.dumps(raw).encode())["homes"][0]["devices"][0]
    assert dev["name"].startswith("A B xxx") and len(dev["name"]) == 200
    assert dev["warrantyUntil"] is None
    assert dev["roomId"] is None


def test_duplicate_devices_are_kept_once():
    raw = json.loads(make())
    raw["homes"][0]["devices"].append(dict(raw["homes"][0]["devices"][0]))
    assert len(parse_view(json.dumps(raw).encode())["homes"][0]["devices"]) == 1


def test_without_codes():
    v = without_codes(parse_view(make()))
    dev = v["homes"][0]["devices"][0]
    assert dev["qr"] is None and dev["manual"] is None and v["includeCodes"] is False


def test_days_left():
    today = date(2026, 10, 28)
    assert days_left(None, today) is None
    assert days_left("2026-10-28", today) == 0
    assert days_left("2026-10-27", today) == -1
    assert days_left("2026-12-27", today) == 60
