"""The webhook the app talks to.

One POST per operation. The operation and the file path travel in headers,
the bytes in the body. Every answer carries ``X-Kodara: 1``; Home Assistant
answers an unknown webhook with an empty 200, and the missing header is how
the app notices a wrong address.
"""

from __future__ import annotations

import asyncio
import json
import logging

from aiohttp import web

from homeassistant.core import HomeAssistant

from .const import MAX_BODY_BYTES, PROTO_VERSION
from .storage import KodaraStore, StoreError
from .view import ViewError, parse_view

_LOGGER = logging.getLogger(__name__)

H_OP = "X-Kodara-Op"
H_PATH = "X-Kodara-Path"
H_IF_ABSENT = "X-Kodara-If-Absent"
H_OFFSET = "X-Kodara-Offset"
H_LENGTH = "X-Kodara-Length"
H_TOTAL = "X-Kodara-Total"
H_PROTO = "X-Kodara-Proto"


def _reply(
    status: int = 200, *, body: bytes = b"", headers: dict | None = None
) -> web.Response:
    return web.Response(
        status=status,
        body=body,
        headers={"X-Kodara": "1", "Cache-Control": "no-store", **(headers or {})},
    )


def _json(status: int, payload: object) -> web.Response:
    return _reply(
        status,
        body=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )


def _int(request: web.Request, name: str) -> int | None:
    raw = request.headers.get(name)
    if raw is None:
        return None
    if not raw.isdigit() or len(raw) > 12:
        raise StoreError(400, f"bad {name}")
    return int(raw)


class KodaraApi:
    """Handles the webhook requests of one config entry."""

    def __init__(self, hass: HomeAssistant, store: KodaraStore, on_view) -> None:
        self._hass = hass
        self.store = store
        self._on_view = on_view
        self._lock = asyncio.Lock()

    async def handle(
        self, hass: HomeAssistant, webhook_id: str, request: web.Request
    ) -> web.Response:
        if request.headers.get(H_PROTO) != str(PROTO_VERSION):
            return _json(426, {"error": "unsupported protocol"})
        op = request.headers.get(H_OP, "")
        try:
            if request.content_length is not None and (
                request.content_length > MAX_BODY_BYTES
            ):
                raise StoreError(413, "too large")
            body = await request.read()
            if len(body) > MAX_BODY_BYTES:
                raise StoreError(413, "too large")
            return await self._dispatch(op, request, body)
        except StoreError as err:
            return _json(err.status, {"error": err.message})
        except ViewError as err:
            return _json(400, {"error": f"view: {err}"})
        except OSError:
            _LOGGER.exception("Kodara storage failed")
            return _json(500, {"error": "storage"})

    async def _run(self, func, *args, **kwargs):
        return await self._hass.async_add_executor_job(
            lambda: func(*args, **kwargs)
        )

    async def _dispatch(self, op: str, request: web.Request, body: bytes):
        path = request.headers.get(H_PATH, "")
        store = self.store
        if op == "prepare":
            await self._run(store.prepare)
            used = await self._run(store.used_bytes)
            return _json(
                200,
                {"proto": PROTO_VERSION, "quota": store.quota_bytes, "used": used},
            )
        if op == "list":
            return _json(200, await self._run(store.list, path))
        if op == "read":
            data, total = await self._run(
                store.read, path, _int(request, H_OFFSET) or 0, _int(request, H_LENGTH)
            )
            return _reply(
                200,
                body=data,
                headers={
                    "Content-Type": "application/octet-stream",
                    H_TOTAL: str(total),
                },
            )
        if op == "write":
            async with self._lock:
                complete = await self._run(
                    store.write,
                    path,
                    body,
                    if_absent=request.headers.get(H_IF_ABSENT) == "1",
                    offset=_int(request, H_OFFSET),
                    total=_int(request, H_TOTAL),
                )
            return _json(201 if complete else 202, {"complete": complete})
        if op == "delete":
            async with self._lock:
                await self._run(store.delete, path)
            return _reply(204)
        if op == "view_put":
            view = parse_view(body)
            async with self._lock:
                await self._run(store.write_view, json.dumps(view).encode())
            self._on_view(view)
            return _reply(204)
        if op == "view_delete":
            async with self._lock:
                await self._run(store.delete_view)
            self._on_view(None)
            return _reply(204)
        raise StoreError(400, "unknown operation")
