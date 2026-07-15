from dataclasses import dataclass

from application.index_selection import IndexSelectionService
from application.multi_index_coordinator import IndexScanResult, MultiIndexCoordinator
from application.position_reservation import PositionReservation
from core.index_registry import IndexRegistry


@dataclass(frozen=True)
class Candidate:
    name: str
    projected_net: float
    confidence: float


def test_coordinator_selects_one_best_tradable_candidate_and_records_all_diagnostics():
    registry = IndexRegistry.default()
    selection = IndexSelectionService(registry)
    reservation = PositionReservation()
    executed: list[tuple[str, Candidate]] = []
    captured: list[IndexScanResult] = []
    coordinator = MultiIndexCoordinator(
        registry=registry,
        selection=selection,
        reservation=reservation,
        execute=lambda symbol, candidate, token: executed.append((symbol, candidate)) or True,
        record_diagnostics=captured.extend,
    )

    outcome = coordinator.coordinate([
        IndexScanResult("NIFTY", Candidate("n", 200, 80), ("nifty row",)),
        IndexScanResult("BANKNIFTY", Candidate("b", 300, 75), ("bank row",)),
        IndexScanResult("MIDCPNIFTY", Candidate("m", 999, 99), ("observe row",)),
    ])

    assert outcome.executed is True
    assert outcome.index_symbol == "BANKNIFTY"
    assert executed == [("BANKNIFTY", Candidate("b", 300, 75))]
    assert [row.index_symbol for row in captured] == ["NIFTY", "BANKNIFTY", "MIDCPNIFTY"]


def test_zero_selection_pauses_entries_but_preserves_diagnostics():
    registry = IndexRegistry.default()
    selection = IndexSelectionService(registry)
    initial = selection.snapshot()
    selection.update(set(), expected_version=initial.version)
    captured: list[IndexScanResult] = []
    coordinator = MultiIndexCoordinator(
        registry=registry,
        selection=selection,
        reservation=PositionReservation(),
        execute=lambda *_: (_ for _ in ()).throw(AssertionError("must not execute")),
        record_diagnostics=captured.extend,
    )

    outcome = coordinator.coordinate([IndexScanResult("NIFTY", Candidate("n", 200, 80), ())])

    assert outcome.executed is False
    assert outcome.reason == "PAUSE_NEW_ENTRIES"
    assert len(captured) == 1


def test_failed_execution_releases_reservation_for_next_scan():
    registry = IndexRegistry.default()
    coordinator = MultiIndexCoordinator(
        registry=registry,
        selection=IndexSelectionService(registry),
        reservation=PositionReservation(),
        execute=lambda *_: False,
        record_diagnostics=lambda _: None,
    )

    first = coordinator.coordinate([IndexScanResult("NIFTY", Candidate("n", 200, 80), ())])
    second = coordinator.coordinate([IndexScanResult("NIFTY", Candidate("n", 200, 80), ())])

    assert first.reason == "EXECUTION_REJECTED"
    assert second.reason == "EXECUTION_REJECTED"
