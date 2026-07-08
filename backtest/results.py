"""
Backtest Results
─────────────────
Collects trade results, computes statistics, and prepares
data for reporting and UI display.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional

from core.models import Trade, DaySession


@dataclass
class BacktestResults:
    """
    Aggregated backtest results across all trading days.
    Fed into reporting/excel_export and UI display.
    """
    sessions: List[DaySession] = field(default_factory=list)
    config_snapshot: Dict = field(default_factory=dict)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    def add_session(self, session: DaySession) -> None:
        """Add a completed day session."""
        self.sessions.append(session)

    @property
    def all_trades(self) -> List[Trade]:
        """Flatten all trades from all sessions."""
        trades = []
        for session in self.sessions:
            trades.extend(session.trades)
        return trades

    @property
    def closed_trades(self) -> List[Trade]:
        """Only completed (exited) trades."""
        return [t for t in self.all_trades if not t.is_open]

    @property
    def total_trades(self) -> int:
        return len(self.closed_trades)

    @property
    def winning_trades(self) -> int:
        return sum(1 for t in self.closed_trades if t.combined_pnl > 0)

    @property
    def losing_trades(self) -> int:
        return sum(1 for t in self.closed_trades if t.combined_pnl < 0)

    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return round(self.winning_trades / self.total_trades * 100, 2)

    @property
    def total_pnl(self) -> float:
        return round(sum(t.combined_pnl for t in self.closed_trades), 2)

    @property
    def max_drawdown(self) -> float:
        """Maximum peak-to-trough decline in cumulative PnL."""
        if not self.closed_trades:
            return 0.0

        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0

        for trade in self.closed_trades:
            cumulative += trade.combined_pnl
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative
            if dd > max_dd:
                max_dd = dd

        return round(max_dd, 2)

    @property
    def avg_profit(self) -> float:
        winners = [t.combined_pnl for t in self.closed_trades if t.combined_pnl > 0]
        if not winners:
            return 0.0
        return round(sum(winners) / len(winners), 2)

    @property
    def avg_loss(self) -> float:
        losers = [t.combined_pnl for t in self.closed_trades if t.combined_pnl < 0]
        if not losers:
            return 0.0
        return round(sum(losers) / len(losers), 2)

    @property
    def profit_factor(self) -> float:
        """Ratio of gross profit to gross loss."""
        gross_profit = sum(t.combined_pnl for t in self.closed_trades if t.combined_pnl > 0)
        gross_loss = abs(sum(t.combined_pnl for t in self.closed_trades if t.combined_pnl < 0))
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0
        return round(gross_profit / gross_loss, 2)

    @property
    def circuit_breaker_days(self) -> int:
        """Number of days where the circuit breaker was hit."""
        return sum(1 for s in self.sessions if s.circuit_breaker_hit)

    @property
    def daily_pnl(self) -> List[Dict]:
        """PnL broken down by day — for the history page."""
        result = []
        for session in self.sessions:
            result.append({
                "date": session.date,
                "trades": session.trade_count,
                "realized_pnl": session.realized_pnl,
                "circuit_breaker": session.circuit_breaker_hit,
            })
        return result

    @property
    def equity_curve(self) -> List[Dict]:
        """Cumulative PnL over time — for charting."""
        points = []
        cumulative = 0.0
        for trade in self.closed_trades:
            cumulative += trade.combined_pnl
            points.append({
                "time": trade.exit_time,
                "pnl": round(cumulative, 2),
                "trade_id": trade.id,
            })
        return points

    def summary(self) -> Dict:
        """Generate a summary dict for UI/reporting."""
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": f"{self.win_rate}%",
            "total_pnl": f"₹{self.total_pnl:,.2f}",
            "avg_profit": f"₹{self.avg_profit:,.2f}",
            "avg_loss": f"₹{self.avg_loss:,.2f}",
            "max_drawdown": f"₹{self.max_drawdown:,.2f}",
            "profit_factor": self.profit_factor,
            "circuit_breaker_days": self.circuit_breaker_days,
            "trading_days": len(self.sessions),
        }
