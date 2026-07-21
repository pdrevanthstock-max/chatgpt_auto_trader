from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Protocol

from application.index_selection import IndexSelectionService
from application.position_reservation import PositionReservation
from core.index_registry import IndexPermission, IndexRegistry


class RankedCandidate(Protocol):
    projected_net: float
    confidence: float


@dataclass(frozen=True)
class IndexScanResult:
    index_symbol: str
    candidate: RankedCandidate | None
    diagnostics: tuple[object, ...]


@dataclass(frozen=True)
class CoordinationOutcome:
    executed: bool
    index_symbol: str | None
    reason: str


class MultiIndexCoordinator:
    """Deterministically selects at most one candidate across index scans.

    Scanners and execution remain injected ports. This boundary owns global
    permission, selection, and reservation checks; it never calls a broker.
    """

    def __init__(
        self,
        *,
        registry: IndexRegistry,
        selection: IndexSelectionService,
        reservation: PositionReservation,
        execute: Callable[[str, RankedCandidate, str], bool],
        record_diagnostics: Callable[[list[IndexScanResult]], None],
    ) -> None:
        self._registry = registry
        self._selection = selection
        self._reservation = reservation
        self._execute = execute
        self._record_diagnostics = record_diagnostics

    def coordinate(self, scans: Iterable[IndexScanResult]) -> CoordinationOutcome:
        materialized = list(scans)
        self._record_diagnostics(materialized)
        selected = self._selection.snapshot()
        if selected.pause_new_entries:
            return CoordinationOutcome(False, None, "PAUSE_NEW_ENTRIES")
        if self._reservation.snapshot().state != "EMPTY":
            return CoordinationOutcome(False, None, "POSITION_SLOT_UNAVAILABLE")

        eligible: list[IndexScanResult] = []
        for scan in materialized:
            symbol = str(scan.index_symbol).upper()
            if symbol not in selected.symbols or scan.candidate is None:
                continue
            if self._registry.get(symbol).permission is not IndexPermission.TRADABLE:
                continue
            eligible.append(scan)
        if not eligible:
            return CoordinationOutcome(False, None, "NO_EXECUTABLE_CANDIDATE")

        winner = max(
            eligible,
            key=lambda scan: (
                float(scan.candidate.projected_net),
                float(scan.candidate.confidence),
                str(scan.index_symbol),
            ),
        )
        symbol = str(winner.index_symbol).upper()
        candidate_id = f"{symbol}:{winner.candidate!r}"
        token = self._reservation.try_reserve(candidate_id)
        if token is None:
            return CoordinationOutcome(False, None, "POSITION_SLOT_UNAVAILABLE")
        try:
            if not self._execute(symbol, winner.candidate, token):
                self._reservation.release(token)
                return CoordinationOutcome(False, symbol, "EXECUTION_REJECTED")
            if not self._reservation.activate(token):
                self._reservation.release(token)
                return CoordinationOutcome(False, symbol, "RESERVATION_ACTIVATION_FAILED")
            # The callback accepted the candidate for serialized execution; a
            # broker/PAPER fill has not happened yet.
            return CoordinationOutcome(True, symbol, "QUEUED")
        except Exception:
            self._reservation.release(token)
            raise
