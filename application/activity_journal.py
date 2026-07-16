from __future__ import annotations

from pathlib import Path
from threading import RLock


class ActivityJournal:
    """Small dependency-free rotating journal for copyable engine activity."""

    def __init__(self, path: Path, max_bytes: int = 5_000_000, backup_count: int = 3) -> None:
        self.path = Path(path)
        self.max_bytes = max(1, int(max_bytes))
        self.backup_count = max(0, int(backup_count))
        self._lock = RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _rotate_if_needed(self, incoming_bytes: int) -> None:
        current_size = self.path.stat().st_size if self.path.exists() else 0
        if current_size + incoming_bytes <= self.max_bytes:
            return
        if self.backup_count == 0:
            self.path.unlink(missing_ok=True)
            return
        oldest = self.path.with_name(f"{self.path.name}.{self.backup_count}")
        oldest.unlink(missing_ok=True)
        for index in range(self.backup_count - 1, 0, -1):
            source = self.path.with_name(f"{self.path.name}.{index}")
            if source.exists():
                source.replace(self.path.with_name(f"{self.path.name}.{index + 1}"))
        if self.path.exists():
            self.path.replace(self.path.with_name(f"{self.path.name}.1"))

    def append(self, message: str) -> None:
        line = f"{message.rstrip()}\n"
        encoded = line.encode("utf-8")
        with self._lock:
            self._rotate_if_needed(len(encoded))
            with self.path.open("a", encoding="utf-8", newline="") as handle:
                handle.write(line)
