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
        contents = notes.model_dump_json()
        original_time = None
        try:
            original_time = path.stat().st_mtime
            if path.read_text() == contents:
                return
        except OSError:
            pass
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as file:
            temporary = Path(file.name)
            file.write(contents)
        try:
            os.replace(temporary, path)
            if original_time is not None:
                os.utime(path, (original_time, original_time))
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
        records = []
        for path in self.directory.glob("*.json"):
            notes = self.get(path.stem)
            if notes is not None:
                try:
                    first_at = min(
                        (entry.at for entry in notes.transcript), default=path.stat().st_mtime
                    )
                except OSError:
                    continue
                records.append((first_at, notes))
        return [notes for _, notes in sorted(records, key=lambda record: record[0], reverse=True)][
            :limit
        ]
