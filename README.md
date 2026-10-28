# Kodara Sync for Home Assistant

A custom integration for the **Kodara Home** app. It does two things:

1. **Sync folder.** It gives the app a private place on your Home Assistant to keep
   its end-to-end encrypted sync files, so several devices can stay in step without
   a cloud. Home Assistant only stores bytes and cannot read them.
2. **Optional view.** If you switch on *Show in Home Assistant* in the app, the app
   publishes a readable copy of your homes, rooms and devices:
   - one device per Kodara device, with sensors for *Warranty until* and
     *Warranty ends soon*, and a device count per home;
   - an admin-only sidebar panel **Kodara** with search, and — if you also share
     pairing codes — the code as a QR code and as the 11-digit manual code, so you
     can scan it with your phone while pairing.

Pairing codes are never entity attributes (so they never end up in the recorder
history). They are only returned to administrators in the panel.

## Install

HACS → Custom repositories → add this repository as *Integration*, install, restart
Home Assistant, then *Settings → Devices & services → Add integration → Kodara Sync*.
The setup shows an address; type it into the app under *Data → Sync → Home Assistant*.
Treat the address like a password.

## Privacy and limits

- Files are stored in `<config>/kodara_sync/` (mode 0700/0600) and are included in
  Home Assistant backups. Sync files are encrypted by the app with your sync password.
- The view file `view.json` is **not** encrypted (Home Assistant has to read it). With
  pairing codes shared it contains them in plain text, and so does every backup.
  Switch the view off in the app and it is deleted here.
- Storage limit: 500 MB by default (integration options).
- Use https (Nabu Casa or a reverse proxy) when you sync from outside your network.

## Development

Tests use `pytest-homeassistant-custom-component`; see `tests/`. The panel bundles
[qrcode-generator](https://github.com/kazuhikoarase/qrcode-generator) 2.0.4 (MIT,
Kazuhiko Arase) as `frontend/qrcode.mjs`.

License: MIT.
