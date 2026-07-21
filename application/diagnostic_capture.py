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
    full_rows: tuple[dict[str, object], ...] = ()


class DiagnosticCaptureService:
    """Thread-safe, observational capture buffer for pair scan explanations."""

    def __init__(self, max_rows: int = 1_000) -> None:
        if max_rows <= 0:
            raise ValueError("max_rows must be positive.")
        self._max_rows = max_rows
        self._capturing = False
        self._top_count = 5
        self._rows_by_index: dict[str, list[dict[str, object]]] = {}
        self._sequence = 0
        self._lock = RLock()

    def start(self, top_count: int) -> DiagnosticSnapshot:
        if top_count not in {5, 10}:
            raise ValueError("top_count must be 5 or 10.")
        with self._lock:
            self._capturing = True
            self._top_count = top_count
            self._rows_by_index = {}
            self._sequence = 0
            return self._snapshot_unlocked()

    def stop(self) -> DiagnosticSnapshot:
        with self._lock:
            self._capturing = False
            return self._snapshot_unlocked()

    def record(self, rows: Iterable[Mapping[str, object]]) -> None:
        with self._lock:
            if not self._capturing:
                return
            for source in rows:
                row = dict(source)
                index_symbol = str(
                    row.get("index", row.get("symbol", "__UNKNOWN__"))
                ).upper()
                row["__capture_sequence"] = self._sequence
                self._sequence += 1
                history = self._rows_by_index.setdefault(index_symbol, [])
                history.append(row)
                if len(history) > self._max_rows:
                    del history[: len(history) - self._max_rows]

    @staticmethod
    def _public_row(row: Mapping[str, object]) -> dict[str, object]:
        return {key: value for key, value in row.items() if key != "__capture_sequence"}

    def _full_rows_unlocked(self) -> list[dict[str, object]]:
        rows = [row for history in self._rows_by_index.values() for row in history]
        rows.sort(key=lambda row: int(row["__capture_sequence"]))
        return rows

    def _visible_rows_unlocked(self, full_rows: list[dict[str, object]]) -> list[dict[str, object]]:
        groups: dict[tuple[str, str], list[dict[str, object]]] = {}
        for row in full_rows:
            index_symbol = str(
                row.get("index", row.get("symbol", "__UNKNOWN__"))
            ).upper()
            cycle_id = str(row.get("cycle_id", "__LEGACY__"))
            groups.setdefault((cycle_id, index_symbol), []).append(row)

        latest_cycle_by_index: dict[str, tuple[str, int]] = {}
        for (cycle_id, index_symbol), group in groups.items():
            newest_sequence = max(int(row["__capture_sequence"]) for row in group)
            previous = latest_cycle_by_index.get(index_symbol)
            if previous is None or newest_sequence > previous[1]:
                latest_cycle_by_index[index_symbol] = (cycle_id, newest_sequence)

        visible: list[dict[str, object]] = []
        for index_symbol in sorted(latest_cycle_by_index):
            cycle_id, _ = latest_cycle_by_index[index_symbol]
            group = groups[(cycle_id, index_symbol)]
            ranked_rows = [
                row for row in group
                if isinstance(row.get("rank"), (int, float))
                or str(row.get("rank", "")).isdigit()
            ]
            candidates = ranked_rows or group
            ranked = sorted(
                candidates,
                key=lambda row: (
                    int(row.get("rank", 2**31 - 1)),
                    int(row["__capture_sequence"]),
                ),
            )
            # The API always exposes enough rows for the UI's Top 5/Top 10
            # toggle. ``top_count`` remains the user's initial display choice;
            # truncating here made Top 10 impossible without restarting capture.
            visible.extend(ranked[:10])
        return visible

    def _snapshot_unlocked(self) -> DiagnosticSnapshot:
        full_rows = self._full_rows_unlocked()
        visible_rows = self._visible_rows_unlocked(full_rows)
        return DiagnosticSnapshot(
            capturing=self._capturing,
            top_count=self._top_count,
            rows=tuple(self._public_row(row) for row in visible_rows),
            full_rows=tuple(self._public_row(row) for row in full_rows),
        )

    def snapshot(self) -> DiagnosticSnapshot:
        with self._lock:
            return self._snapshot_unlocked()

    def to_json(self) -> str:
        return json.dumps(list(self.snapshot().full_rows), sort_keys=True, indent=2)

    def to_csv(self) -> str:
        rows = list(self.snapshot().full_rows)
        fieldnames = sorted({key for row in rows for key in row})
        output = io.StringIO(newline="")
        if fieldnames:
            writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        return output.getvalue()
