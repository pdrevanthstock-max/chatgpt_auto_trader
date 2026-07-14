from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from database.capital_ledger import CapitalTransaction, CapitalTransactionType


@dataclass(frozen=True)
class LiveReadinessReport:
    ready: bool
    closed_trades: int
    trading_days: int
    net_pnl: float
    profit_factor: float
    max_drawdown: float
    failures: tuple[str, ...]


def evaluate_live_readiness(
    transactions: Iterable[CapitalTransaction],
    allocation: float,
    min_trades: int = 50,
    min_days: int = 5,
    min_profit_factor: float = 1.2,
    max_drawdown_pct: float = 0.10,
) -> LiveReadinessReport:
    """Evaluate cost-inclusive PAPER results; cash deposits never count as profit."""
    allocation = float(allocation)
    if not math.isfinite(allocation) or allocation <= 0.0:
        raise ValueError("LIVE readiness allocation must be finite and positive.")

    pnl_transactions = sorted(
        (
            item
            for item in transactions
            if item.mode == "PAPER"
            and item.transaction_type is CapitalTransactionType.TRADE_PNL
        ),
        key=lambda item: item.timestamp,
    )
    amounts = [float(item.amount) for item in pnl_transactions]
    gross_profit = sum(amount for amount in amounts if amount > 0.0)
    gross_loss = abs(sum(amount for amount in amounts if amount < 0.0))
    profit_factor = (
        gross_profit / gross_loss
        if gross_loss > 0.0
        else (math.inf if gross_profit > 0.0 else 0.0)
    )

    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for amount in amounts:
        cumulative += amount
        peak = max(peak, cumulative)
        max_drawdown = max(max_drawdown, peak - cumulative)

    trading_days = len({item.timestamp.date() for item in pnl_transactions})
    net_pnl = round(sum(amounts), 2)
    failures = []
    if len(amounts) < int(min_trades):
        failures.append(f"{int(min_trades)} closed PAPER trades")
    if trading_days < int(min_days):
        failures.append(f"{int(min_days)} PAPER trading days")
    if net_pnl <= 0.0:
        failures.append("positive net PAPER P&L after costs")
    if profit_factor < float(min_profit_factor):
        failures.append(f"profit factor >= {float(min_profit_factor):.2f}")
    if max_drawdown > allocation * float(max_drawdown_pct):
        failures.append(f"max drawdown <= {float(max_drawdown_pct):.1%} of allocation")

    return LiveReadinessReport(
        ready=not failures,
        closed_trades=len(amounts),
        trading_days=trading_days,
        net_pnl=net_pnl,
        profit_factor=round(profit_factor, 4),
        max_drawdown=round(max_drawdown, 2),
        failures=tuple(failures),
    )
