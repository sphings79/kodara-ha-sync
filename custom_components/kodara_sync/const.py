"""Constants for Kodara Sync."""

from __future__ import annotations

DOMAIN = "kodara_sync"
PROTO_VERSION = 1

CONF_WEBHOOK_ID = "webhook_id"
CONF_WARRANTY_DAYS = "warranty_days"
CONF_QUOTA_MB = "quota_mb"

DEFAULT_WARRANTY_DAYS = 60
DEFAULT_QUOTA_MB = 500

# Folder inside the HA config directory.
STORAGE_DIR = "kodara_sync"

# Largest body one request may carry. HA itself refuses more than 16 MiB.
MAX_BODY_BYTES = 12 * 1024 * 1024

SIGNAL_VIEW_UPDATED = f"{DOMAIN}_view_updated"

PANEL_URL_PATH = "kodara"
STATIC_URL = "/kodara_static"
