"""Private, bounded finished-call notes; survives a service restart, never stores keys."""

from __future__ import annotations

import os
import re
import tempfile
import time
from pathlib import Path

from app.protocol import CallNotes


class NotesArchive:
    def __init__(self, directory: str | None, *, retention_s: float = 86400) -> None:
        self.directory = Path(directory) if directory else None
        self.retention_s = retention_s
        if self.directory:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.directory.chmod(0o700)

    def _path(self, call_id: str) -> Path | None:
        if self.directory is None or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", call_id):
            return None
        return self.directory / (call_id + ".json")

    def put(self, notes: CallNotes) -> None:
        path = self._path(notes.call_id)
        if path is None or not notes.ready:
            return
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as file:
            temporary = Path(file.name)
            file.write(notes.model_dump_json())
        try:
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def get(self, call_id: str) -> CallNotes | None:
        path = self._path(call_id)
        if path is None:
            return None
        try:
            if time.time() - path.stat().st_mtime > self.retention_s:
                path.unlink(missing_ok=True)
                return None
            return CallNotes.model_validate_json(path.read_text())
        except (OSError, ValueError):
            return None

    def recent(self, limit: int = 10) -> list[CallNotes]:
        if self.directory is None:
            return []
        paths = sorted(self.directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        return [notes for p in paths if (notes := self.get(p.stem)) is not None][:limit]
