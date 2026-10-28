"""Files of the sync folder, kept on disk.

The files are end-to-end encrypted by the app; this module only stores bytes.
Paths are checked against a fixed list of shapes, so no request can reach
anything else in the config directory.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

_FILE_PATH = re.compile(
    r"^(sync\.json|devices/[A-Za-z0-9_-]{1,100}\.snap|files/[0-9a-f]{64})$"
)
_FOLDERS = ("devices", "files")
_VIEW_FILE = "view.json"
_STALE_PART_SECONDS = 24 * 3600


class StoreError(Exception):
    """A request the store refuses; carries an HTTP status."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class KodaraStore:
    """Reads and writes the sync files. All methods block; run them in an
    executor."""

    def __init__(self, root: Path, quota_bytes: int) -> None:
        self.root = root
        self.quota_bytes = quota_bytes

    # Folder setup

    def prepare(self) -> None:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        for folder in _FOLDERS:
            (self.root / folder).mkdir(mode=0o700, exist_ok=True)
        now = time.time()
        for folder in _FOLDERS:
            for part in (self.root / folder).glob("*.part"):
                if now - part.stat().st_mtime > _STALE_PART_SECONDS:
                    part.unlink(missing_ok=True)

    def _resolve(self, path: str) -> Path:
        if not _FILE_PATH.match(path):
            raise StoreError(400, "bad path")
        return self.root / path

    def used_bytes(self) -> int:
        total = 0
        for base, _dirs, files in os.walk(self.root):
            for name in files:
                if name == _VIEW_FILE and base == str(self.root):
                    continue
                try:
                    total += os.stat(os.path.join(base, name)).st_size
                except FileNotFoundError:
                    pass
        return total

    # Sync files

    def read(
        self, path: str, offset: int = 0, length: int | None = None
    ) -> tuple[bytes, int]:
        """Returns (bytes, total size). Raises StoreError(404) if missing."""
        target = self._resolve(path)
        try:
            with target.open("rb") as handle:
                total = os.fstat(handle.fileno()).st_size
                handle.seek(offset)
                return handle.read(length if length is not None else -1), total
        except FileNotFoundError:
            raise StoreError(404, "not found") from None

    def write(
        self,
        path: str,
        data: bytes,
        *,
        if_absent: bool = False,
        offset: int | None = None,
        total: int | None = None,
    ) -> bool:
        """Writes a whole file, or one piece of it.

        With ``offset`` and ``total`` the file arrives in pieces: the piece at
        offset 0 starts it, the one that reaches ``total`` completes it. The
        result tells whether the file is complete now.
        """
        target = self._resolve(path)
        if if_absent and target.exists():
            raise StoreError(409, "exists")
        part = target.with_name(target.name + ".part")
        if offset is None:
            self._check_quota(len(data), replacing=target)
            self._atomic_write(target, data)
            return True
        if total is None or offset < 0 or total < 0 or offset + len(data) > total:
            raise StoreError(400, "bad range")
        if offset == 0:
            part.unlink(missing_ok=True)
            self._check_quota(total, replacing=target)
        elif not part.exists() or part.stat().st_size != offset:
            raise StoreError(409, "out of order")
        part.parent.mkdir(mode=0o700, exist_ok=True)
        fd = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "ab") as handle:
            handle.write(data)
        if offset + len(data) < total:
            return False
        if if_absent and target.exists():
            part.unlink(missing_ok=True)
            raise StoreError(409, "exists")
        os.replace(part, target)
        return True

    def delete(self, path: str) -> None:
        target = self._resolve(path)
        target.unlink(missing_ok=True)
        target.with_name(target.name + ".part").unlink(missing_ok=True)

    def list(self, folder: str) -> list[dict]:
        if folder not in _FOLDERS:
            raise StoreError(400, "bad folder")
        base = self.root / folder
        entries = []
        if not base.is_dir():
            return entries
        for item in sorted(base.iterdir()):
            if not _FILE_PATH.match(f"{folder}/{item.name}"):
                continue
            stat = item.stat()
            entries.append(
                {
                    "name": item.name,
                    "size": stat.st_size,
                    "modified": int(stat.st_mtime),
                    "version": f"{stat.st_mtime_ns}-{stat.st_size}",
                }
            )
        return entries

    def _check_quota(self, incoming: int, replacing: Path) -> None:
        current = replacing.stat().st_size if replacing.exists() else 0
        if self.used_bytes() - current + incoming > self.quota_bytes:
            raise StoreError(507, "quota")

    @staticmethod
    def _atomic_write(target: Path, data: bytes) -> None:
        target.parent.mkdir(mode=0o700, exist_ok=True)
        temp = target.with_name(target.name + ".tmp")
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)

    # The readable view for Home Assistant

    def read_view(self) -> bytes | None:
        try:
            return (self.root / _VIEW_FILE).read_bytes()
        except FileNotFoundError:
            return None

    def write_view(self, data: bytes) -> None:
        self._atomic_write(self.root / _VIEW_FILE, data)

    def delete_view(self) -> None:
        (self.root / _VIEW_FILE).unlink(missing_ok=True)
