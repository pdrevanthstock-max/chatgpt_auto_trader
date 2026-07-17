from dataclasses import dataclass
from datetime import datetime, timedelta

from application.index_selection import IndexSelectionService
from application.multi_index_coordinator import IndexScanResult
from application.multi_index_runtime import MultiIndexRuntime
from application.position_reservation import PositionReservation
from core.index_registry import IndexRegistry
from data.candle_store import CompletedCandleStore, spot_candle_key
from data.market_cache import MarketCacheRegistry


@dataclass(frozen=True)
class Candidate:
    projected_net: float
    confidence: float


class FakeScanner:
    def __init__(self, symbol: str, calls: list[tuple[str, str, str]]) -> None:
        self.symbol = symbol
        self.calls = calls
        self.config = None

    def scan(self, *, regime, spot_trend, **_):
        self.calls.append((self.symbol, regime.value, spot_trend))
        projected = {
            "NIFTY": 100.0,
            "BANKNIFTY": 250.0,
            "FINNIFTY": 150.0,
            "MIDCPNIFTY": 999.0,
            "NIFTYNXT50": 998.0,
        }[self.symbol]
        return IndexScanResult(
            self.symbol,
            Candidate(projected, 80.0),
            ({"index": self.symbol, "result": "PASS"},),
        )


def _seed_market_data(caches: MarketCacheRegistry, candles: CompletedCandleStore) -> None:
    now = datetime(2026, 7, 16, 10, 30)
    spots = {
        "NIFTY": 24_150.0,
        "BANKNIFTY": 58_000.0,
        "FINNIFTY": 26_900.0,
        "MIDCPNIFTY": 14_825.0,
        "NIFTYNXT50": 72_500.0,
    }
    for symbol, spot in spots.items():
        caches.get(symbol).update_spot(spot, now)
        for offset in range(11):
            timestamp = now - timedelta(minutes=10 - offset)
            candles.add_tick(
                spot_candle_key(symbol),
                timestamp=timestamp,
                price=spot + offset,
                volume=1_000,
            )


def _runtime(registry, selection, caches, candles, calls, executed, diagnostics):
    return MultiIndexRuntime(
        registry=registry,
        caches=caches,
        selection=selection,
        reservation=PositionReservation(),
        config=object(),
        execute=lambda symbol, candidate, token: executed.append(
            (symbol, candidate, token)
        ) or True,
        record_diagnostics=diagnostics.extend,
        candle_store=candles,
        scanner_factory=lambda spec, _cache, _config: FakeScanner(spec.symbol, calls),
    )


def test_runtime_scans_all_selected_indices_and_executes_best_tradable_only():
    registry = IndexRegistry.default()
    selection = IndexSelectionService(registry)
    caches = MarketCacheRegistry.default()
    candles = CompletedCandleStore()
    _seed_market_data(caches, candles)
    calls, executed, diagnostics = [], [], []
    runtime = _runtime(registry, selection, caches, candles, calls, executed, diagnostics)

    cycle = runtime.scan(
        now=datetime(2026, 7, 16, 10, 31),
        realized_pnl=0.0,
        active_trade=None,
        available_capital=45_000.0,
    )

    assert {symbol for symbol, _, _ in calls} == set(registry.symbols)
    assert cycle.outcome.executed is True
    assert cycle.outcome.index_symbol == "BANKNIFTY"
    assert executed[0][0] == "BANKNIFTY"
    assert {row.index_symbol for row in diagnostics} == set(registry.symbols)


def test_runtime_scans_only_selected_indices_and_zero_selection_pauses_entries():
    registry = IndexRegistry.default()
    selection = IndexSelectionService(registry)
    initial = selection.snapshot()
    selection.update({"FINNIFTY", "MIDCPNIFTY"}, expected_version=initial.version)
    caches = MarketCacheRegistry.default()
    candles = CompletedCandleStore()
    _seed_market_data(caches, candles)
    calls, executed, diagnostics = [], [], []
    runtime = _runtime(registry, selection, caches, candles, calls, executed, diagnostics)

    first = runtime.scan(
        now=datetime(2026, 7, 16, 10, 31), realized_pnl=0.0,
        active_trade=None, available_capital=45_000.0,
    )
    snapshot = selection.snapshot()
    selection.update(set(), expected_version=snapshot.version)
    second = runtime.scan(
        now=datetime(2026, 7, 16, 10, 32), realized_pnl=0.0,
        active_trade=None, available_capital=45_000.0,
    )

    assert {symbol for symbol, _, _ in calls} == {"FINNIFTY", "MIDCPNIFTY"}
    assert first.outcome.index_symbol == "FINNIFTY"
    assert second.outcome.reason == "PAUSE_NEW_ENTRIES"


def test_runtime_requires_completed_candles_per_index():
    registry = IndexRegistry.default()
    selection = IndexSelectionService(registry)
    initial = selection.snapshot()
    selection.update({"BANKNIFTY"}, expected_version=initial.version)
    caches = MarketCacheRegistry.default()
    caches.get("BANKNIFTY").update_spot(58_000.0, datetime(2026, 7, 16, 10, 30))
    calls, executed, diagnostics = [], [], []
    runtime = _runtime(
        registry, selection, caches, CompletedCandleStore(),
        calls, executed, diagnostics,
    )

    cycle = runtime.scan(
        now=datetime(2026, 7, 16, 10, 31), realized_pnl=0.0,
        active_trade=None, available_capital=45_000.0,
    )

    assert calls == []
    assert cycle.outcome.reason == "NO_EXECUTABLE_CANDIDATE"
    assert diagnostics[0].diagnostics[0]["reason"] == "COMPLETED_CANDLES_NOT_READY"


def test_rotation_scan_compares_all_tradable_indices_without_executing_entry():
    registry = IndexRegistry.default()
    selection = IndexSelectionService(registry)
    caches = MarketCacheRegistry.default()
    candles = CompletedCandleStore()
    _seed_market_data(caches, candles)
    calls, executed, diagnostics = [], [], []
    runtime = _runtime(registry, selection, caches, candles, calls, executed, diagnostics)

    cycle = runtime.scan_for_rotation(
        now=datetime(2026, 7, 17, 10, 31),
        realized_pnl=0.0,
        available_capital=45_000.0,
    )

    assert {symbol for symbol, _, _ in calls} == set(registry.symbols)
    assert executed == []
    assert cycle.winner is not None
    assert cycle.winner.index_symbol == "BANKNIFTY"
    assert {scan.index_symbol for scan in cycle.scans} == set(registry.symbols)
    assert {scan.index_symbol for scan in diagnostics} == set(registry.symbols)
