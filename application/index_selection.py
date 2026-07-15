from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from core.index_registry import IndexRegistry


IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class IndexSelectionSnapshot:
    symbols: frozenset[str]
    all_symbols: frozenset[str]
    version: int

    @property
    def is_all(self) -> bool:
        return self.symbols == self.all_symbols

    @property
    def pause_new_entries(self) -> bool:
        return not self.symbols


@dataclass(frozen=True)
class IndexSelectionAuditEvent:
    timestamp: datetime
    previous: frozenset[str]
    current: frozenset[str]
    version: int
    execution_mode: str


class IndexSelectionService:
    """Owns an atomic, versioned runtime index-universe selection."""

    def __init__(self, registry: IndexRegistry) -> None:
        self._registry = registry
        self._all = frozenset(registry.symbols)
        self._symbols = self._all
        self._version = 0
        self._lock = threading.RLock()
        self._audit: list[IndexSelectionAuditEvent] = []

    def snapshot(self) -> IndexSelectionSnapshot:
        with self._lock:
            return IndexSelectionSnapshot(self._symbols, self._all, self._version)

    def update(
        self,
        symbols: set[str],
        *,
        expected_version: int,
        execution_mode: str = "PAPER",
    ) -> IndexSelectionSnapshot:
        normalized = frozenset(str(symbol).upper() for symbol in symbols)
        unknown = normalized - self._all
        if unknown:
            raise ValueError(f"Unsupported indices: {', '.join(sorted(unknown))}")
        with self._lock:
            if expected_version != self._version:
                raise ValueError(
                    f"Stale selection version {expected_version}; current version is {self._version}."
                )
            previous = self._symbols
            self._symbols = normalized
            self._version += 1
            self._audit.append(IndexSelectionAuditEvent(
                timestamp=datetime.now(IST),
                previous=previous,
                current=normalized,
                version=self._version,
                execution_mode=str(execution_mode).upper(),
            ))
            return IndexSelectionSnapshot(self._symbols, self._all, self._version)

    @property
    def audit_events(self) -> tuple[IndexSelectionAuditEvent, ...]:
        with self._lock:
            return tuple(self._audit)
