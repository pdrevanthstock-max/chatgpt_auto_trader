from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from application.performance_service import PerformancePeriod, PerformanceService
from config.settings import TradingConfig
from database.capital_ledger import CapitalLedger, CapitalTransactionType
from database.trade_store import TradeStore


@dataclass(frozen=True)
class PaperAccountSnapshot:
    available_equity: float
    lifetime_realized_pnl: float
    today_realized_pnl: float
    month_realized_pnl: float
    cash_adjustments: float


class PaperAccountService:
    """Builds one PAPER account view for runtime sizing and dashboard display."""

    def __init__(
        self,
        *,
        config: TradingConfig,
        capital_ledger: CapitalLedger,
        trade_store: TradeStore,
        now_provider: Callable[[], datetime],
    ) -> None:
        self._config = config
        self._ledger = capital_ledger
        self._store = trade_store
        self._now = now_provider

    def _paper_trades(self) -> list[object]:
        return [
            trade
            for trade in self._store.get_all_trades()
            if str(getattr(trade, "execution_mode", "UNKNOWN")).upper() == "PAPER"
        ]

    def _durable_lifetime_realized(self) -> float:
        # Legacy rows predate execution_mode persistence and belong to the
        # historical PAPER simulation. Include them for account equity while
        # keeping period reports mode-scoped.
        trades = [
            trade
            for trade in self._store.get_all_trades()
            if str(getattr(trade, "execution_mode", "UNKNOWN")).upper()
            in {"PAPER", "UNKNOWN"}
            and not bool(getattr(trade, "is_open", False))
        ]
        represented = {str(getattr(trade, "id", "")) for trade in trades}
        realized = sum(float(getattr(trade, "net_pnl", 0.0)) for trade in trades)
        realized += sum(
            item.amount
            for item in self._ledger.list_transactions("PAPER")
            if item.transaction_type is CapitalTransactionType.TRADE_PNL
            and str(item.reference_id or "") not in represented
        )
        return round(realized, 2)

    def _period_realized(
        self,
        period: PerformancePeriod,
        trades: list[object],
    ) -> float:
        now = self._now()
        result = PerformanceService.calculate(
            trades=trades,
            mode="PAPER",
            period=period,
            now=now,
            active_pnl=0.0,
        )
        represented = {str(getattr(trade, "id", "")) for trade in trades}
        orphaned = 0.0
        for item in self._ledger.list_transactions("PAPER"):
            if item.transaction_type is not CapitalTransactionType.TRADE_PNL:
                continue
            if str(item.reference_id or "") in represented:
                continue
            observed = PerformanceService._as_ist(item.timestamp)
            if result.period_start is not None and observed < result.period_start:
                continue
            if observed > result.period_end:
                continue
            orphaned += item.amount
        return round(result.realized_pnl + orphaned, 2)

    def snapshot(self, *, lifetime_realized_pnl: float) -> PaperAccountSnapshot:
        recovery_lifetime = round(float(lifetime_realized_pnl), 2)
        durable_lifetime = self._durable_lifetime_realized()
        # Use the more conservative total. A missing/corrupt recovery file
        # commonly reports zero and must never erase durable losses. Durable
        # storage remains the floor if the two sources temporarily disagree.
        lifetime = min(recovery_lifetime, durable_lifetime)
        adjustments = self._ledger.cash_adjustment_total("PAPER")
        available = max(
            0.0,
            round(float(self._config.total_capital) + lifetime + adjustments, 2),
        )
        trades = self._paper_trades()
        return PaperAccountSnapshot(
            available_equity=available,
            lifetime_realized_pnl=lifetime,
            today_realized_pnl=self._period_realized(PerformancePeriod.TODAY, trades),
            month_realized_pnl=self._period_realized(PerformancePeriod.MONTH, trades),
            cash_adjustments=adjustments,
        )
