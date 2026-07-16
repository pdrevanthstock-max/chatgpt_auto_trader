from __future__ import annotations

from datetime import datetime
from typing import Callable

from application.performance_service import PerformancePeriod, PerformanceService
from config.settings import TradingConfig
from database.capital_ledger import CapitalLedger, CapitalTransactionType
from database.trade_store import TradeStore


class DashboardService:
    """Builds UI read models without owning trading or execution decisions."""

    def __init__(
        self,
        trade_store: TradeStore,
        capital_ledger: CapitalLedger,
        config: TradingConfig,
        now_provider: Callable[[], datetime],
        active_trade_provider: Callable[[], object | None] | None = None,
    ) -> None:
        self._trade_store = trade_store
        self._capital_ledger = capital_ledger
        self._config = config
        self._now = now_provider
        self._active_trade_provider = active_trade_provider or (lambda: None)

    @staticmethod
    def _mode(value: str) -> str:
        mode = str(value).upper()
        if mode not in {"PAPER", "LIVE"}:
            raise ValueError("mode must be PAPER or LIVE.")
        return mode

    def _trades(self, mode: str) -> list[object]:
        normalized = self._mode(mode)
        return [
            trade
            for trade in self._trade_store.get_all_trades()
            if str(getattr(trade, "execution_mode", "UNKNOWN")).upper() == normalized
        ]

    @staticmethod
    def _active_pnl(trades: list[object]) -> float:
        total = 0.0
        for trade in trades:
            if not getattr(trade, "is_open", False):
                continue
            ce = float(getattr(trade, "ce_current_price", 0.0) or 0.0)
            pe = float(getattr(trade, "pe_current_price", 0.0) or 0.0)
            if ce > 0.0 and pe > 0.0:
                total += float(getattr(trade, "net_pnl", 0.0))
        return round(total, 2)

    def performance(self, period: str, mode: str) -> dict[str, object]:
        normalized = self._mode(mode)
        selected_period = PerformancePeriod(period)
        trades = self._trades(normalized)
        runtime_trade = self._active_trade_provider()
        active_pnl = self._active_pnl(trades)
        if (
            runtime_trade is not None
            and getattr(runtime_trade, "is_open", False)
            and str(getattr(runtime_trade, "execution_mode", "UNKNOWN")).upper() == normalized
        ):
            active_pnl = self._active_pnl([runtime_trade])
        result = PerformanceService.calculate(
            trades=trades,
            mode=normalized,
            period=selected_period,
            now=self._now(),
            active_pnl=active_pnl,
        )
        return {
            "period": result.period.value,
            "mode": result.mode,
            "realized_pnl": result.realized_pnl,
            "active_pnl": result.active_pnl,
            "total_pnl": result.total_pnl,
            "daily_risk_pnl": result.daily_risk_pnl,
            "period_start": result.period_start.isoformat() if result.period_start else None,
            "period_end": result.period_end.isoformat(),
        }

    @staticmethod
    def _trade_row(trade: object) -> dict[str, object]:
        entry_time = getattr(trade, "entry_time", None)
        exit_time = getattr(trade, "exit_time", None)
        exit_reason = getattr(trade, "exit_reason", None)
        return {
            "trade_id": getattr(trade, "display_id", getattr(trade, "id", "")),
            "execution_mode": str(getattr(trade, "execution_mode", "UNKNOWN")).upper(),
            "index_symbol": str(getattr(trade, "index_symbol", "NIFTY")).upper(),
            "direction": getattr(getattr(trade, "direction", None), "value", "UNKNOWN"),
            "regime": getattr(getattr(trade, "regime_at_entry", None), "value", "UNKNOWN"),
            "phase": getattr(getattr(trade, "phase", None), "value", "UNKNOWN"),
            "ce_strike": int(getattr(trade, "strike_ce", 0)),
            "pe_strike": int(getattr(trade, "strike_pe", 0)),
            "ce_entry": float(getattr(trade, "entry_ce_price", 0.0)),
            "pe_entry": float(getattr(trade, "entry_pe_price", 0.0)),
            "ce_exit": getattr(trade, "exit_ce_price", None),
            "pe_exit": getattr(trade, "exit_pe_price", None),
            "lots": int(getattr(trade, "quantity", 0)),
            "lot_size": int(getattr(trade, "lot_size", 0)),
            "units_per_leg": int(getattr(trade, "units_per_leg", 0)),
            "entry_time": entry_time.isoformat() if entry_time else None,
            "exit_time": exit_time.isoformat() if exit_time else None,
            "exit_reason": getattr(exit_reason, "value", None),
            "gross_pnl": float(getattr(trade, "gross_pnl", 0.0)),
            "transaction_costs": float(getattr(trade, "transaction_costs", 0.0)),
            "net_pnl": float(getattr(trade, "net_pnl", 0.0)),
            "hard_stop_loss": float(getattr(trade, "hard_stop_loss", 0.0)),
            "post_daily_sl": bool(getattr(trade, "post_daily_sl", False)),
        }

    def active_position(self, mode: str) -> dict[str, object] | None:
        normalized = self._mode(mode)
        runtime_trade = self._active_trade_provider()
        if (
            runtime_trade is not None
            and getattr(runtime_trade, "is_open", False)
            and str(getattr(runtime_trade, "execution_mode", "UNKNOWN")).upper() == normalized
        ):
            open_trades = [runtime_trade]
        else:
            open_trades = [trade for trade in self._trades(normalized) if getattr(trade, "is_open", False)]
        if not open_trades:
            return None
        trade = max(open_trades, key=lambda row: getattr(row, "entry_time", datetime.min) or datetime.min)
        row = self._trade_row(trade)
        ce = float(getattr(trade, "ce_current_price", 0.0) or 0.0)
        pe = float(getattr(trade, "pe_current_price", 0.0) or 0.0)
        available = ce > 0.0 and pe > 0.0
        row.update(
            {
                "ce_current": ce if available else None,
                "pe_current": pe if available else None,
                "mark_to_market_available": available,
                "active_pnl": float(getattr(trade, "net_pnl", 0.0)) if available else None,
            }
        )
        return row

    def journal(self, mode: str) -> list[dict[str, object]]:
        trades = self._trades(mode)
        trades.sort(key=lambda row: getattr(row, "entry_time", datetime.min) or datetime.min, reverse=True)
        return [self._trade_row(trade) for trade in trades]

    def capital(self, mode: str) -> dict[str, object]:
        normalized = self._mode(mode)
        transactions = list(reversed(self._capital_ledger.list_transactions(normalized)))
        rows = [
            {
                "id": item.id,
                "timestamp": item.timestamp.isoformat(),
                "mode": item.mode,
                "type": item.transaction_type.value,
                "amount": item.amount,
                "note": item.note,
                "reference_id": item.reference_id,
                "broker_balance": item.broker_balance,
                "allocation_after": item.allocation_after,
            }
            for item in transactions
        ]
        if normalized == "LIVE":
            return {
                "mode": normalized,
                "base_capital": None,
                "realized_pnl": None,
                "cash_adjustments": None,
                "equity": None,
                "live_allocation": self._capital_ledger.latest_live_allocation(),
                "transactions": rows,
                "read_only": True,
            }
        all_time = self.performance(PerformancePeriod.ALL_TIME.value, normalized)
        realized = float(all_time["realized_pnl"])
        # Older PAPER trades may predate execution_mode persistence and are
        # intentionally excluded from P&L period reports. Their append-only
        # TRADE_PNL ledger rows must still reduce available PAPER equity. Add
        # only ledger rows whose trade is not already represented by a
        # mode-scoped TradeStore row, avoiding double counting current trades.
        represented_trade_ids = {
            str(getattr(trade, "id", "")) for trade in self._trades(normalized)
        }
        orphaned_ledger_pnl = sum(
            item.amount
            for item in transactions
            if item.transaction_type is CapitalTransactionType.TRADE_PNL
            and str(item.reference_id or "") not in represented_trade_ids
        )
        realized = round(realized + orphaned_ledger_pnl, 2)
        adjustments = self._capital_ledger.cash_adjustment_total(normalized)
        return {
            "mode": normalized,
            "base_capital": float(self._config.total_capital),
            "realized_pnl": realized,
            "cash_adjustments": adjustments,
            "equity": self._capital_ledger.paper_equity(self._config.total_capital, realized),
            "live_allocation": None,
            "transactions": rows,
            "read_only": True,
        }

    def adjust_paper_target(
        self,
        target_equity: float,
        note: str,
        *,
        engine_running: bool,
        has_open_position: bool,
    ) -> dict[str, object]:
        current = self.capital("PAPER")
        self._capital_ledger.adjust_paper_to_target(
            current_equity=float(current["equity"]),
            target_equity=target_equity,
            note=note,
            engine_running=engine_running,
            has_open_position=has_open_position,
        )
        return self.capital("PAPER")
