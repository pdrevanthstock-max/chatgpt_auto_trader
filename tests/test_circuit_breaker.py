"""
Tests: Daily Circuit Breaker
──────────────────────────────
Unit tests for the 3% daily loss limit.
"""

import pytest

from core.models import DaySession, Trade
from core.enums import TradeDirection, ExitReason
from config.settings import TradingConfig
from strategy.daily_circuit_breaker import DailyCircuitBreaker
from datetime import datetime


def _make_config(capital=30000, daily_limit=0.03) -> TradingConfig:
    return TradingConfig(total_capital=capital, daily_loss_limit_pct=daily_limit)


def _make_closed_trade(pnl: float) -> Trade:
    """Create a closed trade with the given PnL."""
    t = Trade(
        direction=TradeDirection.LONG_CE,
        entry_ce_price=100,
        entry_pe_price=100,
        quantity=1,
        lot_size=25,
        entry_time=datetime(2026, 7, 1, 10, 0),
        capital_allocated=5000,
        current_ce_price=100,
        current_pe_price=100,
    )
    # Manipulate prices to produce desired PnL
    # PnL = (exit_ce - entry_ce + exit_pe - entry_pe) * qty * lot
    # For simplicity, adjust CE exit
    ce_exit = 100 + (pnl / 25)  # 25 = qty*lot_size
    t.exit_ce_price = ce_exit
    t.exit_pe_price = 100
    t.exit_time = datetime(2026, 7, 1, 11, 0)
    t.exit_reason = ExitReason.PER_TRADE_STOP
    t.current_ce_price = ce_exit
    t.current_pe_price = 100
    return t


class TestDailyCircuitBreaker:

    def test_no_breaker_with_small_loss(self):
        """Small loss should not trigger breaker."""
        config = _make_config()  # limit = 900
        session = DaySession(date=datetime(2026, 7, 1))
        session.realized_pnl = -100  # well below 900

        assert not DailyCircuitBreaker.is_breaker_hit(session, config)

    def test_breaker_on_3_percent_loss(self):
        """Cumulative loss of 3% (₹900 on ₹30,000) → breaker hit."""
        config = _make_config()
        session = DaySession(date=datetime(2026, 7, 1))
        session.realized_pnl = -900

        assert DailyCircuitBreaker.is_breaker_hit(session, config)

    def test_breaker_includes_unrealized(self):
        """Unrealized PnL counts toward circuit breaker (§5.2)."""
        config = _make_config()
        session = DaySession(date=datetime(2026, 7, 1))
        session.realized_pnl = -500

        # Open trade with -500 unrealized
        open_trade = Trade(
            direction=TradeDirection.LONG_CE,
            entry_ce_price=100, entry_pe_price=100,
            quantity=1, lot_size=25,
            entry_time=datetime(2026, 7, 1, 12, 0),
            capital_allocated=5000,
            current_ce_price=80, current_pe_price=100,  # -500 PnL
        )
        session.trades.append(open_trade)

        # Total = -500 realized + -500 unrealized = -1000 > 900
        assert DailyCircuitBreaker.is_breaker_hit(session, config)

    def test_no_breaker_on_profit(self):
        """Profitable day should never trigger breaker."""
        config = _make_config()
        session = DaySession(date=datetime(2026, 7, 1))
        session.realized_pnl = 5000

        assert not DailyCircuitBreaker.is_breaker_hit(session, config)

    def test_can_open_trade_checks_breaker(self):
        """can_open_new_trade should check breaker status."""
        config = _make_config()
        session = DaySession(date=datetime(2026, 7, 1))
        session.realized_pnl = -1000  # over limit

        assert not DailyCircuitBreaker.can_open_new_trade(session, config)

    def test_cant_open_trade_with_existing_position(self):
        """Can't open new trade if one is already open."""
        config = _make_config()
        session = DaySession(date=datetime(2026, 7, 1))
        open_trade = Trade(
            direction=TradeDirection.LONG_CE,
            entry_ce_price=100, entry_pe_price=100,
            quantity=1, lot_size=25,
            entry_time=datetime(2026, 7, 1, 10, 0),
            capital_allocated=5000,
            current_ce_price=105, current_pe_price=100,
        )
        session.trades.append(open_trade)

        assert not DailyCircuitBreaker.can_open_new_trade(session, config)
