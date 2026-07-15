from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from threading import RLock
from typing import Iterable, Mapping


@dataclass(frozen=True)
class DiagnosticSnapshot:
    capturing: bool
    top_count: int
    rows: tuple[dict[str, object], ...]


class DiagnosticCaptureService:
    """Thread-safe, observational capture buffer for pair scan explanations."""

    def __init__(self, max_rows: int = 1_000) -> None:
        if max_rows <= 0:
            raise ValueError("max_rows must be positive.")
        self._max_rows = max_rows
        self._capturing = False
        self._top_count = 5
        self._rows: list[dict[str, object]] = []
        self._lock = RLock()

    def start(self, top_count: int) -> DiagnosticSnapshot:
        if top_count not in {5, 10}:
            raise ValueError("top_count must be 5 or 10.")
        with self._lock:
            self._capturing = True
            self._top_count = top_count
            self._rows = []
            return self._snapshot_unlocked()

    def stop(self) -> DiagnosticSnapshot:
        with self._lock:
            self._capturing = False
            return self._snapshot_unlocked()

    def record(self, rows: Iterable[Mapping[str, object]]) -> None:
        with self._lock:
            if not self._capturing:
                return
            self._rows.extend(dict(row) for row in rows)
            if len(self._rows) > self._max_rows:
                self._rows = self._rows[-self._max_rows :]

    def _snapshot_unlocked(self) -> DiagnosticSnapshot:
        return DiagnosticSnapshot(
            capturing=self._capturing,
            top_count=self._top_count,
            rows=tuple(dict(row) for row in self._rows),
        )

    def snapshot(self) -> DiagnosticSnapshot:
        with self._lock:
            return self._snapshot_unlocked()

    def to_json(self) -> str:
        return json.dumps(list(self.snapshot().rows), sort_keys=True, indent=2)

    def to_csv(self) -> str:
        rows = list(self.snapshot().rows)
        fieldnames = sorted({key for row in rows for key in row})
        output = io.StringIO(newline="")
        if fieldnames:
            writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        return output.getvalue()
