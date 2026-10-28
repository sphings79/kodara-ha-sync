import json
from datetime import timedelta

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kodara_sync.const import (
    CONF_WARRANTY_DAYS,
    CONF_WEBHOOK_ID,
    DOMAIN,
)

HOOK = "a" * 64
QR = "MT:Y.K9042C00KA0648G00"
H = "b" * 64


def hdr(op, path=None, **extra):
    h = {"X-Kodara-Proto": "1", "X-Kodara-Op": op}
    if path:
        h["X-Kodara-Path"] = path
    h.update(extra)
    return h


async def setup(hass: HomeAssistant, options=None) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_WEBHOOK_ID: HOOK},
        options=options or {},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def view(warranty="2027-01-02", include_codes=True, devices=None):
    today_devices = devices or [
        {
            "id": "d1",
            "name": "Lampe",
            "type": "light",
            "roomId": "r1",
            "manufacturer": "Acme",
            "model": "X1",
            "firmware": "1.2",
            "purchaseDate": "2025-01-02",
            "warrantyUntil": warranty,
            "qr": QR,
            "manual": "34970112332",
        }
    ]
    return json.dumps(
        {
            "version": 1,
            "includeCodes": include_codes,
            "homes": [
                {
                    "id": "h1",
                    "name": "Zuhause",
                    "rooms": [{"id": "r1", "name": "Wohnzimmer"}],
                    "devices": today_devices,
                }
            ],
        }
    ).encode()


async def test_unknown_webhook_has_no_marker(hass, hass_client_no_auth):
    await setup(hass)
    client = await hass_client_no_auth()
    resp = await client.post("/api/webhook/" + "c" * 64, headers=hdr("prepare"))
    assert resp.status == 200
    assert "X-Kodara" not in resp.headers


async def test_protocol_and_operation_checks(hass, hass_client_no_auth):
    await setup(hass)
    client = await hass_client_no_auth()
    url = f"/api/webhook/{HOOK}"
    resp = await client.post(url, headers={"X-Kodara-Op": "prepare"})
    assert resp.status == 426 and resp.headers["X-Kodara"] == "1"
    resp = await client.post(url, headers=hdr("explode"))
    assert resp.status == 400
    resp = await client.get(url)
    assert resp.status == 405


async def test_file_operations(hass, hass_client_no_auth):
    await setup(hass)
    client = await hass_client_no_auth()
    url = f"/api/webhook/{HOOK}"

    resp = await client.post(url, headers=hdr("prepare"))
    info = await resp.json()
    assert resp.status == 200 and info["proto"] == 1 and info["quota"] > 0

    resp = await client.post(url, headers=hdr("read", "sync.json"))
    assert resp.status == 404

    resp = await client.post(url, headers=hdr("write", "sync.json", **{"X-Kodara-If-Absent": "1"}), data=b"one")
    assert resp.status == 201
    resp = await client.post(url, headers=hdr("write", "sync.json", **{"X-Kodara-If-Absent": "1"}), data=b"two")
    assert resp.status == 409

    resp = await client.post(url, headers=hdr("read", "sync.json"))
    assert await resp.read() == b"one" and resp.headers["X-Kodara-Total"] == "3"
    resp = await client.post(url, headers=hdr("read", "sync.json", **{"X-Kodara-Offset": "1", "X-Kodara-Length": "1"}))
    assert await resp.read() == b"n"

    await client.post(url, headers=hdr("write", "devices/aa.snap"), data=b"snap")
    resp = await client.post(url, headers=hdr("list", "devices"))
    listing = await resp.json()
    assert [e["name"] for e in listing] == ["aa.snap"]

    resp = await client.post(url, headers=hdr("delete", "devices/aa.snap"))
    assert resp.status == 204
    resp = await client.post(url, headers=hdr("delete", "devices/aa.snap"))
    assert resp.status == 204
    resp = await client.post(url, headers=hdr("list", "devices"))
    assert await resp.json() == []

    resp = await client.post(url, headers=hdr("read", "../../secrets.yaml"))
    assert resp.status == 400


async def test_chunked_write_over_the_webhook(hass, hass_client_no_auth):
    await setup(hass)
    client = await hass_client_no_auth()
    url = f"/api/webhook/{HOOK}"
    path = f"files/{H}"
    resp = await client.post(url, headers=hdr("write", path, **{"X-Kodara-Offset": "0", "X-Kodara-Total": "6"}), data=b"abc")
    assert resp.status == 202
    resp = await client.post(url, headers=hdr("write", path, **{"X-Kodara-Offset": "3", "X-Kodara-Total": "6"}), data=b"def")
    assert resp.status == 201
    resp = await client.post(url, headers=hdr("read", path))
    assert await resp.read() == b"abcdef"


async def test_view_creates_entities_without_codes(hass, hass_client_no_auth):
    entry = await setup(hass)
    client = await hass_client_no_auth()
    resp = await client.post(f"/api/webhook/{HOOK}", headers=hdr("view_put"), data=view())
    assert resp.status == 204
    await hass.async_block_till_done()

    states = {s.entity_id: s for s in hass.states.async_all()}
    until = next(s for e, s in states.items() if e.startswith("sensor.") and "warranty" in e)
    assert until.state == "2027-01-02"
    assert until.attributes["room"] == "Wohnzimmer"
    assert until.attributes["home"] == "Zuhause"
    # No code anywhere in any state.
    blob = json.dumps([dict(s.attributes) | {"state": s.state} for s in states.values()])
    assert QR not in blob and "34970112332" not in blob

    count = next(s for e, s in states.items() if e.startswith("sensor.") and "devices" in e)
    assert count.state == "1"

    dev = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, "d1"), entry.entry_id)
    assert dev.name == "Lampe" and dev.manufacturer == "Acme" and dev.sw_version == "1.2"


async def test_warranty_binary_sensor_follows_the_threshold(hass, hass_client_no_auth):
    await setup(hass, {CONF_WARRANTY_DAYS: 60})
    today = dt_util.now().date()
    client = await hass_client_no_auth()
    for days, expected in ((30, "on"), (90, "off"), (-5, "off")):
        raw = view(warranty=(today + timedelta(days=days)).isoformat())
        await client.post(f"/api/webhook/{HOOK}", headers=hdr("view_put"), data=raw)
        await hass.async_block_till_done()
        state = next(
            s for s in hass.states.async_all("binary_sensor") if "warranty" in s.entity_id
        )
        assert state.state == expected, days
        assert state.attributes["days_left"] == days


async def test_device_without_warranty_is_unknown(hass, hass_client_no_auth):
    await setup(hass)
    client = await hass_client_no_auth()
    await client.post(f"/api/webhook/{HOOK}", headers=hdr("view_put"), data=view(warranty=None))
    await hass.async_block_till_done()
    states = hass.states.async_all()
    assert any(s.state == "unknown" for s in states if s.entity_id.startswith("sensor.") and "warranty" in s.entity_id)


async def test_removed_devices_disappear_and_changes_apply(hass, hass_client_no_auth):
    entry = await setup(hass)
    client = await hass_client_no_auth()
    url = f"/api/webhook/{HOOK}"
    two = [
        {"id": "d1", "name": "Lampe", "warrantyUntil": "2027-01-01"},
        {"id": "d2", "name": "Schalter", "warrantyUntil": "2027-02-02"},
    ]
    await client.post(url, headers=hdr("view_put"), data=view(devices=two))
    await hass.async_block_till_done()
    reg = dr.async_get(hass)
    assert reg.async_get_device_by_identifier((DOMAIN, "d2"), entry.entry_id) is not None

    two[0]["name"] = "Stehlampe"
    await client.post(url, headers=hdr("view_put"), data=view(devices=two[:1]))
    await hass.async_block_till_done()
    assert reg.async_get_device_by_identifier((DOMAIN, "d2"), entry.entry_id) is None
    assert reg.async_get_device_by_identifier((DOMAIN, "d1"), entry.entry_id).name == "Stehlampe"

    # Coming back creates it again.
    await client.post(url, headers=hdr("view_put"), data=view(devices=two))
    await hass.async_block_till_done()
    assert reg.async_get_device_by_identifier((DOMAIN, "d2"), entry.entry_id) is not None


async def test_view_delete_removes_everything(hass, hass_client_no_auth):
    entry = await setup(hass)
    client = await hass_client_no_auth()
    url = f"/api/webhook/{HOOK}"
    await client.post(url, headers=hdr("view_put"), data=view())
    await hass.async_block_till_done()
    assert er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    resp = await client.post(url, headers=hdr("view_delete"))
    assert resp.status == 204
    await hass.async_block_till_done()
    assert not er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert not any(dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id))


async def test_bad_view_is_refused_and_changes_nothing(hass, hass_client_no_auth):
    await setup(hass)
    client = await hass_client_no_auth()
    url = f"/api/webhook/{HOOK}"
    await client.post(url, headers=hdr("view_put"), data=view())
    await hass.async_block_till_done()
    resp = await client.post(url, headers=hdr("view_put"), data=b"{not json")
    assert resp.status == 400
    assert any(s.state == "2027-01-02" for s in hass.states.async_all("sensor"))


async def test_view_survives_a_reload(hass, hass_client_no_auth):
    entry = await setup(hass)
    client = await hass_client_no_auth()
    await client.post(f"/api/webhook/{HOOK}", headers=hdr("view_put"), data=view())
    await hass.async_block_till_done()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert any(s.state == "2027-01-02" for s in hass.states.async_all("sensor"))


async def test_panel_data_needs_an_admin(hass, hass_client_no_auth, hass_ws_client, hass_admin_user):
    await setup(hass)
    client = await hass_client_no_auth()
    await client.post(f"/api/webhook/{HOOK}", headers=hdr("view_put"), data=view())
    await hass.async_block_till_done()

    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "kodara/view"})
    reply = await ws.receive_json()
    assert reply["success"] is True
    dev = reply["result"]["homes"][0]["devices"][0]
    assert dev["qr"] == QR and dev["manual"] == "34970112332"


async def test_panel_data_refused_for_non_admin(hass, hass_ws_client, hass_read_only_user):
    await setup(hass)
    token = await hass.auth.async_create_refresh_token(
        hass_read_only_user, "https://example.com"
    )
    access = hass.auth.async_create_access_token(token)
    ws = await hass_ws_client(hass, access_token=access)
    await ws.send_json({"id": 1, "type": "kodara/view"})
    reply = await ws.receive_json()
    assert reply["success"] is False


async def test_panel_is_registered_for_admins_only(hass):
    await setup(hass)
    panel = hass.data["frontend_panels"]["kodara"]
    assert panel.require_admin is True
    assert panel.sidebar_title == "Kodara"


async def test_config_flow_shows_the_address_and_creates_the_entry(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "address"
    assert "/api/webhook/" in result["description_placeholders"]["address"]
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == "create_entry"
    hook = result["data"][CONF_WEBHOOK_ID]
    assert len(hook) >= 32


async def test_only_one_entry(hass):
    await setup(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] == "abort"


async def test_options_flow(hass):
    entry = await setup(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert hook_in(result["description_placeholders"]["address"])
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"warranty_days": 30, "quota_mb": 20}
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert entry.options["warranty_days"] == 30


def hook_in(address: str) -> bool:
    return HOOK in address
