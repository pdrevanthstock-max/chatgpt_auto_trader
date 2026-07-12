import logging
from datetime import datetime
from typing import List, Dict, Any
from core.models import Trade

logger = logging.getLogger("AutoTrader")

class BacktestResults:
    """
    Collects execution statistics from a backtest run.
    """
    def __init__(self, trades: List[Trade], initial_capital: float) -> None:
        self.trades = trades
        self.initial_capital = initial_capital
        self.total_trades = len(trades)

    def calculate_metrics(self) -> Dict[str, Any]:
        if not self.trades:
            return {
                "total_trades": 0,
                "total_pnl": 0.0,
                "win_rate": 0.0,
                "wins": 0,
                "losses": 0,
                "net_profit_pct": 0.0,
                "max_drawdown": 0.0,
                "profit_factor": 0.0
            }

        total_pnl = sum(t.combined_pnl for t in self.trades)
        total_net_pnl = sum(t.net_pnl for t in self.trades)
        total_costs = sum(t.transaction_costs for t in self.trades)

        wins = [t for t in self.trades if t.net_pnl > 0]
        losses = [t for t in self.trades if t.net_pnl <= 0]
        
        win_rate = (len(wins) / self.total_trades) * 100.0 if self.total_trades > 0 else 0.0

        gross_profit = sum(t.net_pnl for t in wins)
        gross_loss = abs(sum(t.net_pnl for t in losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (gross_profit if gross_profit > 0 else 1.0)

        # Calculate max drawdown in rupee terms using net equity curve
        equity = self.initial_capital
        peak = self.initial_capital
        max_dd = 0.0
        
        # Sort trades by exit time to trace equity curve
        sorted_trades = sorted(self.trades, key=lambda x: x.exit_time or datetime.now())
        for t in sorted_trades:
            equity += t.net_pnl
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd

        return {
            "total_trades": self.total_trades,
            "total_pnl": round(total_pnl, 2),
            "total_net_pnl": round(total_net_pnl, 2),
            "total_costs": round(total_costs, 2),
            "win_rate": round(win_rate, 2),
            "wins": len(wins),
            "losses": len(losses),
            "net_profit_pct": round((total_net_pnl / self.initial_capital) * 100.0, 2),
            "max_drawdown": round(max_dd, 2),
            "profit_factor": round(profit_factor, 2)
        }

    def summary(self) -> str:
        metrics = self.calculate_metrics()
        return (
            f"--- Backtest Summary ---\n"
            f"Total Trades: {metrics['total_trades']}\n"
            f"Gross PnL: ₹{metrics['total_pnl']:,.2f}\n"
            f"Transaction Costs: ₹{metrics['total_costs']:,.2f}\n"
            f"Net PnL: ₹{metrics['total_net_pnl']:,.2f} ({metrics['net_profit_pct']}%)\n"
            f"Win Rate: {metrics['win_rate']}%\n"
            f"Wins: {metrics['wins']} | Losses: {metrics['losses']}\n"
            f"Profit Factor (Net): {metrics['profit_factor']}\n"
            f"Max Drawdown (Net): ₹{metrics['max_drawdown']:,.2f}\n"
            f"------------------------"
        )
