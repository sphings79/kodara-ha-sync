// Admin panel of Kodara Sync: the devices published by the Kodara Home app,
// with pairing codes as a QR code to scan with a phone. Plain DOM calls only;
// nothing from the data is ever put into markup.
import qrcode from "./qrcode.mjs";

const TEXT = {
  en: {
    title: "Kodara",
    search: "Search devices",
    refresh: "Refresh",
    empty: "Nothing published yet. In the Kodara Home app, switch on “Show in Home Assistant”.",
    noRoom: "No room",
    show: "Show code",
    hide: "Hide code",
    manual: "Manual pairing code",
    noCode: "No code published",
    codesOff: "Pairing codes are not shared. Switch them on in the app to show them here.",
    warranty: "Warranty until",
    loadFailed: "The data could not be loaded.",
    scan: "Scan with your phone while pairing.",
  },
  de: {
    title: "Kodara",
    search: "Geräte suchen",
    refresh: "Aktualisieren",
    empty: "Noch nichts veröffentlicht. Schalte in der App Kodara Home „In Home Assistant anzeigen“ ein.",
    noRoom: "Ohne Raum",
    show: "Code anzeigen",
    hide: "Code verbergen",
    manual: "Manueller Kopplungscode",
    noCode: "Kein Code veröffentlicht",
    codesOff: "Kopplungscodes werden nicht geteilt. Schalte sie in der App ein, dann erscheinen sie hier.",
    warranty: "Garantie bis",
    loadFailed: "Die Daten konnten nicht geladen werden.",
    scan: "Beim Koppeln mit dem Handy scannen.",
  },
};

const STYLE = `
:host { display: block; padding: 16px; box-sizing: border-box; color: var(--primary-text-color); background: var(--primary-background-color); min-height: 100%; }
h1 { font-size: 22px; margin: 0 0 12px; font-weight: 500; }
.bar { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
input, select, button { font: inherit; padding: 8px 10px; border-radius: 8px; border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); }
input { flex: 1 1 200px; }
button { cursor: pointer; }
h2 { font-size: 16px; margin: 20px 0 8px; color: var(--secondary-text-color); font-weight: 500; }
.card { background: var(--card-background-color); border-radius: 12px; padding: 12px 16px; margin-bottom: 8px; box-shadow: var(--ha-card-box-shadow, none); border: 1px solid var(--divider-color); }
.row { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.name { font-weight: 500; }
.sub { color: var(--secondary-text-color); font-size: 13px; }
.code { display: flex; gap: 20px; align-items: center; margin-top: 12px; flex-wrap: wrap; }
canvas { width: 220px; height: 220px; image-rendering: pixelated; background: #fff; border-radius: 8px; }
.digits { font-size: 28px; letter-spacing: 2px; font-variant-numeric: tabular-nums; }
.note { color: var(--secondary-text-color); font-size: 13px; margin-top: 8px; }
.error { color: var(--error-color); }
`;

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node[key] = value;
  }
  for (const child of children) {
    if (child == null) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function groupManual(digits) {
  if (/^\d{11}$/.test(digits)) return `${digits.slice(0, 4)}-${digits.slice(4, 7)}-${digits.slice(7)}`;
  return digits.replace(/(\d{4})(?=\d)/g, "$1 ");
}

function drawQr(text) {
  const qr = qrcode(0, "M");
  qr.addData(text);
  qr.make();
  const count = qr.getModuleCount();
  const quiet = 4;
  const scale = 8;
  const size = (count + quiet * 2) * scale;
  const canvas = el("canvas", { width: size, height: size });
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, size, size);
  ctx.fillStyle = "#000";
  for (let r = 0; r < count; r++) {
    for (let c = 0; c < count; c++) {
      if (qr.isDark(r, c)) ctx.fillRect((c + quiet) * scale, (r + quiet) * scale, scale, scale);
    }
  }
  return canvas;
}

class KodaraPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._view = undefined;
    this._open = new Set();
    this._filter = "";
    this._home = null;
    this._loading = false;
    this._failed = false;
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._load();
  }

  get _t() {
    const lang = (this._hass?.language || "en").slice(0, 2);
    return TEXT[lang] || TEXT.en;
  }

  async _load() {
    if (this._loading) return;
    this._loading = true;
    try {
      this._view = await this._hass.callWS({ type: "kodara/view" });
      this._failed = false;
    } catch (_) {
      this._failed = true;
    }
    this._loading = false;
    this._render();
  }

  _render() {
    const t = this._t;
    const root = this.shadowRoot;
    root.replaceChildren(el("style", { textContent: STYLE }));
    root.append(el("h1", {}, t.title));

    const view = this._view;
    const homes = view?.homes ?? [];
    if (!this._home || !homes.some((h) => h.id === this._home)) this._home = homes[0]?.id ?? null;

    const search = el("input", {
      type: "search",
      placeholder: t.search,
      value: this._filter,
      oninput: (e) => {
        this._filter = e.target.value;
        this._renderList(list);
      },
    });
    const bar = el("div", { class: "bar" }, search);
    if (homes.length > 1) {
      const select = el("select", {
        onchange: (e) => {
          this._home = e.target.value;
          this._renderList(list);
        },
      });
      for (const h of homes) select.append(el("option", { value: h.id, selected: h.id === this._home }, h.name));
      bar.append(select);
    }
    bar.append(el("button", { onclick: () => this._load() }, t.refresh));
    root.append(bar);

    const list = el("div");
    root.append(list);
    this._renderList(list);
  }

  _renderList(list) {
    const t = this._t;
    list.replaceChildren();
    if (this._failed) {
      list.append(el("div", { class: "error" }, t.loadFailed));
      return;
    }
    const home = this._view?.homes.find((h) => h.id === this._home);
    if (!home) {
      list.append(el("div", { class: "note" }, t.empty));
      return;
    }
    if (!this._view.includeCodes) list.append(el("div", { class: "note" }, t.codesOff));

    const query = this._filter.trim().toLowerCase();
    const matches = (d) =>
      !query || [d.name, d.manufacturer, d.model, d.type].some((v) => v && v.toLowerCase().includes(query));

    const groups = new Map();
    for (const room of home.rooms) groups.set(room.id, { title: room.name, devices: [] });
    groups.set(null, { title: t.noRoom, devices: [] });
    for (const dev of home.devices) {
      if (!matches(dev)) continue;
      (groups.get(dev.roomId) ?? groups.get(null)).devices.push(dev);
    }
    for (const group of groups.values()) {
      if (!group.devices.length) continue;
      list.append(el("h2", {}, group.title));
      for (const dev of group.devices) list.append(this._deviceCard(dev, list));
    }
  }

  _deviceCard(dev, list) {
    const t = this._t;
    const sub = [dev.manufacturer, dev.model].filter(Boolean).join(" · ");
    const hasCode = Boolean(dev.qr || dev.manual);
    const open = this._open.has(dev.id);
    const head = el(
      "div",
      { class: "row" },
      el(
        "div",
        {},
        el("div", { class: "name" }, dev.name),
        sub ? el("div", { class: "sub" }, sub) : null,
        dev.warrantyUntil ? el("div", { class: "sub" }, `${t.warranty}: ${dev.warrantyUntil}`) : null,
      ),
      hasCode
        ? el(
            "button",
            {
              onclick: () => {
                if (open) this._open.delete(dev.id);
                else this._open.add(dev.id);
                this._renderList(list);
              },
            },
            open ? t.hide : t.show,
          )
        : this._view.includeCodes
          ? el("span", { class: "sub" }, t.noCode)
          : null,
    );
    const card = el("div", { class: "card" }, head);
    if (open && hasCode) {
      const body = el("div", { class: "code" });
      if (dev.qr) body.append(drawQr(dev.qr));
      const side = el("div");
      if (dev.manual) {
        side.append(el("div", { class: "sub" }, t.manual), el("div", { class: "digits" }, groupManual(dev.manual)));
      }
      if (dev.qr) side.append(el("div", { class: "note" }, t.scan));
      body.append(side);
      card.append(body);
    }
    return card;
  }
}

customElements.define("kodara-panel", KodaraPanel);
