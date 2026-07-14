from datetime import datetime, timedelta

from database.capital_ledger import CapitalTransaction, CapitalTransactionType
from strategy.live_readiness import evaluate_live_readiness


def _paper_pnl(index: int, amount: float) -> CapitalTransaction:
    return CapitalTransaction(
        id=f"ledger-{index}",
        timestamp=datetime(2026, 7, 1) + timedelta(days=index // 10, minutes=index),
        mode="PAPER",
        transaction_type=CapitalTransactionType.TRADE_PNL,
        amount=amount,
        note="paper result",
        reference_id=f"trade-{index}",
    )


def test_live_readiness_requires_enough_profitable_cost_inclusive_paper_evidence():
    transactions = [_paper_pnl(i, 200.0 if i % 2 == 0 else -100.0) for i in range(50)]

    report = evaluate_live_readiness(
        transactions=transactions,
        allocation=45_000.0,
        min_trades=50,
        min_days=5,
        min_profit_factor=1.2,
        max_drawdown_pct=0.10,
    )

    assert report.ready
    assert report.net_pnl == 2_500.0
    assert report.profit_factor == 2.0


def test_live_readiness_fails_closed_for_losses_or_insufficient_sample():
    transactions = [_paper_pnl(i, -100.0) for i in range(12)]

    report = evaluate_live_readiness(
        transactions=transactions,
        allocation=45_000.0,
        min_trades=50,
        min_days=5,
        min_profit_factor=1.2,
        max_drawdown_pct=0.10,
    )

    assert not report.ready
    assert "50 closed PAPER trades" in report.failures
    assert "positive net PAPER P&L after costs" in report.failures


def test_deposits_do_not_count_as_strategy_profitability():
    transactions = [_paper_pnl(i, -10.0) for i in range(50)]
    transactions.append(
        CapitalTransaction(
            id="deposit",
            timestamp=datetime(2026, 7, 10),
            mode="PAPER",
            transaction_type=CapitalTransactionType.DEPOSIT,
            amount=50_000.0,
            note="refill",
        )
    )

    report = evaluate_live_readiness(
        transactions=transactions,
        allocation=45_000.0,
        min_trades=50,
        min_days=5,
        min_profit_factor=1.2,
        max_drawdown_pct=0.10,
    )

    assert report.net_pnl == -500.0
    assert not report.ready
