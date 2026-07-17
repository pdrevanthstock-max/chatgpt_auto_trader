from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol

from application.index_scanner import IndexScanner
from application.index_selection import IndexSelectionService
from application.multi_index_coordinator import (
    CoordinationOutcome,
    IndexScanResult,
    MultiIndexCoordinator,
    RankedCandidate,
)
from application.position_reservation import PositionReservation
from core.index_registry import IndexPermission, IndexRegistry, IndexSpec
from core.models import Trade
from data.candle_store import CompletedCandleStore, completed_candles, spot_candle_key
from data.market_cache import MarketCache, MarketCacheRegistry
from strategy.market_features import MarketFeatureCalculator
from strategy.regime_detector import RegimeDetector


class ScannerPort(Protocol):
    config: object

    def scan(self, **kwargs) -> IndexScanResult: ...


@dataclass(frozen=True)
class IndexMarketState:
    symbol: str
    ready: bool
    regime: object | None
    spot_trend: str
    completed_candles: int
    reason: str | None = None


@dataclass(frozen=True)
class MultiIndexCycle:
    outcome: CoordinationOutcome
    market_states: tuple[IndexMarketState, ...]


@dataclass(frozen=True)
class RotationScanCycle:
    winner: IndexScanResult | None
    scans: tuple[IndexScanResult, ...]
    market_states: tuple[IndexMarketState, ...]


class MultiIndexRuntime:
    """Owns isolated per-index regime/scanner contexts and global selection."""

    def __init__(
        self,
        *,
        registry: IndexRegistry,
        caches: MarketCacheRegistry,
        selection: IndexSelectionService,
        reservation: PositionReservation,
        config: object,
        execute: Callable[[str, RankedCandidate, str], bool],
        record_diagnostics: Callable[[list[IndexScanResult]], None],
        candle_store: CompletedCandleStore | None = None,
        scanner_factory: Callable[[IndexSpec, MarketCache, object], ScannerPort] | None = None,
    ) -> None:
        self.registry = registry
        self.caches = caches
        self.selection = selection
        self.reservation = reservation
        self.config = config
        self._record_diagnostics = record_diagnostics
        self.candle_store = candle_store or completed_candles
        factory = scanner_factory or (
            lambda spec, cache, current_config: IndexScanner(
                spec=spec,
                cache=cache,
                config=current_config,
                candle_store=self.candle_store,
            )
        )
        self.scanners = {
            symbol: factory(registry.get(symbol), caches.get(symbol), config)
            for symbol in sorted(registry.symbols)
        }
        self.regime_detectors = {
            symbol: RegimeDetector() for symbol in registry.symbols
        }
        self.coordinator = MultiIndexCoordinator(
            registry=registry,
            selection=selection,
            reservation=reservation,
            execute=execute,
            record_diagnostics=record_diagnostics,
        )

    def update_config(self, config: object) -> None:
        self.config = config
        for scanner in self.scanners.values():
            scanner.config = config

    def market_state(self, symbol: str) -> IndexMarketState:
        normalized = str(symbol).upper()
        cache = self.caches.get(normalized)
        spot, _ = cache.get_spot()
        if spot <= 0.0:
            return IndexMarketState(
                normalized, False, None, "UNKNOWN", 0, "SPOT_NOT_READY"
            )
        candles = self.candle_store.latest(spot_candle_key(normalized), count=20)
        if len(candles) < 10:
            return IndexMarketState(
                normalized,
                False,
                None,
                "UNKNOWN",
                len(candles),
                "COMPLETED_CANDLES_NOT_READY",
            )
        features = MarketFeatureCalculator.calculate(candles)
        regime, spot_trend = self.regime_detectors[normalized].detect_regime(
            spot_closes=list(features.closes),
            spot_highs=list(features.highs),
            spot_lows=list(features.lows),
            vwap_values=list(features.vwap_values),
            atr_values=list(features.atr_values),
            atm_strike=cache.get_atm_strike(),
        )
        return IndexMarketState(
            normalized, True, regime, spot_trend, len(candles), None
        )

    def _collect_scans(
        self,
        *,
        now: datetime,
        realized_pnl: float,
        active_trade: Trade | None,
        available_capital: float,
    ) -> tuple[list[IndexScanResult], list[IndexMarketState]]:
        selected = self.selection.snapshot()
        scans: list[IndexScanResult] = []
        states: list[IndexMarketState] = []
        for symbol in sorted(selected.symbols):
            state = self.market_state(symbol)
            states.append(state)
            if not state.ready:
                scans.append(IndexScanResult(
                    symbol,
                    None,
                    ({
                        "index": symbol,
                        "result": "WAIT",
                        "reason": state.reason,
                        "details": (
                            f"{state.completed_candles} of 10 completed one-minute "
                            "spot candles are available."
                        ),
                    },),
                ))
                continue
            scanner = self.scanners[symbol]
            scanner.config = self.config
            scans.append(scanner.scan(
                regime=state.regime,
                spot_trend=state.spot_trend,
                realized_pnl=realized_pnl,
                active_trade=active_trade,
                available_capital=available_capital,
                trading_day=now.date(),
                cycle_id=now.isoformat(),
            ))
        return scans, states

    def scan(
        self,
        *,
        now: datetime,
        realized_pnl: float,
        active_trade: Trade | None,
        available_capital: float,
    ) -> MultiIndexCycle:
        selected = self.selection.snapshot()
        if selected.pause_new_entries:
            outcome = self.coordinator.coordinate([])
            return MultiIndexCycle(outcome, ())

        scans, states = self._collect_scans(
            now=now,
            realized_pnl=realized_pnl,
            active_trade=active_trade,
            available_capital=available_capital,
        )
        outcome = self.coordinator.coordinate(scans)
        return MultiIndexCycle(outcome, tuple(states))

    def scan_for_rotation(
        self,
        *,
        now: datetime,
        realized_pnl: float,
        available_capital: float,
    ) -> RotationScanCycle:
        """Evaluate selected indices without dispatching a second entry."""
        selected = self.selection.snapshot()
        if selected.pause_new_entries:
            self._record_diagnostics([])
            return RotationScanCycle(None, (), ())

        scans, states = self._collect_scans(
            now=now,
            realized_pnl=realized_pnl,
            # A replacement is validated as the next position after the active
            # trade closes; the global reservation remains owned throughout.
            active_trade=None,
            available_capital=available_capital,
        )
        self._record_diagnostics(scans)
        eligible = [
            scan
            for scan in scans
            if scan.candidate is not None
            and scan.index_symbol in selected.symbols
            and self.registry.get(scan.index_symbol).permission is IndexPermission.TRADABLE
        ]
        winner = max(
            eligible,
            key=lambda scan: (
                float(scan.candidate.projected_net),
                float(scan.candidate.confidence),
                str(scan.index_symbol),
            ),
            default=None,
        )
        return RotationScanCycle(winner, tuple(scans), tuple(states))
