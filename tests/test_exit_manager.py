"""
Tests: Exit Manager
─────────────────────
Unit tests for per-trade stop, trailing stop, and EOD flatten.
"""

import pytest
from datetime import datetime, time as dtime

from core.models import Trade
from core.enums import TradeDirection, ExitReason
from config.settings import TradingConfig
from strategy.exit_manager import ExitManager


def _make_trade(
    entry_ce=100.0, entry_pe=100.0,
    current_ce=100.0, current_pe=100.0,
    quantity=1, lot_size=25,
    capital=5000.0,
    peak_pnl=0.0, trailing_stop=0.0,
) -> Trade:
    """Helper: create a Trade with sensible defaults."""
    return Trade(
        direction=TradeDirection.LONG_CE,
        entry_ce_price=entry_ce,
        entry_pe_price=entry_pe,
        quantity=quantity,
        lot_size=lot_size,
        entry_time=datetime(2026, 7, 1, 10, 0),
        capital_allocated=capital,
        current_ce_price=current_ce,
        current_pe_price=current_pe,
        peak_combined_pnl=peak_pnl,
        trailing_stop_pnl=trailing_stop,
    )


class TestPerTradeStop:

    def test_no_stop_when_profitable(self):
        """Profitable trade should not trigger per-trade stop."""
        trade = _make_trade(current_ce=110, current_pe=100, capital=5000)
        config = TradingConfig(per_trade_stop_pct=0.02)

        result = ExitManager.check_per_trade_stop(trade, config)
        assert result is None

    def test_stop_triggered_on_loss(self):
        """Loss exceeding 2% of allocated capital → stop."""
        # Capital = 5000, 2% = 100
        # CE loss: (96 - 100) * 1 * 25 = -100
        # PE loss: (96 - 100) * 1 * 25 = -100
        # Combined: -200, exceeds 100
        trade = _make_trade(
            entry_ce=100, entry_pe=100,
            current_ce=96, current_pe=96,
            capital=5000,
        )
        config = TradingConfig(per_trade_stop_pct=0.02)

        result = ExitManager.check_per_trade_stop(trade, config)
        assert result == ExitReason.PER_TRADE_STOP

    def test_no_stop_below_threshold(self):
        """Small loss below threshold should not trigger."""
        trade = _make_trade(
            current_ce=99.5, current_pe=99.5, capital=5000,
        )
        config = TradingConfig(per_trade_stop_pct=0.02)

        result = ExitManager.check_per_trade_stop(trade, config)
        assert result is None


class TestTrailingStop:

    def test_trailing_updates_on_new_peak(self):
        """Peak PnL → trailing stop should update."""
        trade = _make_trade(
            entry_ce=100, entry_pe=100,
            current_ce=104, current_pe=100,  # CE profit = 4*25 = 100
            capital=5000,
        )
        config = TradingConfig(trail_lock_factor=0.85)

        trade = ExitManager.update_trailing_stop(trade, config)

        # Combined PnL = (104-100)*25 + (100-100)*25 = 100
        assert trade.peak_combined_pnl == 100.0
        assert trade.trailing_stop_pnl == pytest.approx(85.0, abs=0.01)

    def test_trailing_stop_triggers_on_decline(self):
        """PnL dropping below trailing level → exit."""
        trade = _make_trade(
            entry_ce=100, entry_pe=100,
            current_ce=101, current_pe=99,  # PnL = 25 - 25 = 0
            peak_pnl=100.0,
            trailing_stop=85.0,
        )
        config = TradingConfig(trail_lock_factor=0.85)

        result = ExitManager.check_trailing_stop(trade, config)
        assert result == ExitReason.TRAILING_STOP

    def test_no_trailing_without_profit(self):
        """No trailing stop if never been in profit."""
        trade = _make_trade(peak_pnl=0.0)
        config = TradingConfig()

        result = ExitManager.check_trailing_stop(trade, config)
        assert result is None

    def test_trailing_stop_only_moves_up(self):
        """Trailing stop should never decrease."""
        trade = _make_trade(
            entry_ce=100, entry_pe=100,
            current_ce=103, current_pe=100,  # PnL = 75
            peak_pnl=200.0,        # previous peak was higher
            trailing_stop=170.0,    # previous trailing stop
        )
        config = TradingConfig(trail_lock_factor=0.85)

        trade = ExitManager.update_trailing_stop(trade, config)

        # 75 < 200 so peak shouldn't update, trailing stays at 170
        assert trade.trailing_stop_pnl == 170.0

    def test_85_percent_lock_example(self):
        """User's example: ₹100 profit → stop at ₹85."""
        trade = _make_trade(
            entry_ce=100, entry_pe=100,
            current_ce=104, current_pe=100,  # PnL = 100
        )
        config = TradingConfig(trail_lock_factor=0.85)

        trade = ExitManager.update_trailing_stop(trade, config)
        assert trade.trailing_stop_pnl == pytest.approx(85.0, abs=0.01)


class TestEODFlatten:

    def test_flatten_at_1500(self):
        """Should trigger at 15:00."""
        config = TradingConfig(scan_end="15:00")

        result = ExitManager.check_eod_flatten(dtime(15, 0), config)
        assert result == ExitReason.EOD_FLATTEN

    def test_no_flatten_before_1500(self):
        """Should not trigger before 15:00."""
        config = TradingConfig(scan_end="15:00")

        result = ExitManager.check_eod_flatten(dtime(14, 59), config)
        assert result is None

    def test_flatten_after_1500(self):
        """Should trigger after 15:00."""
        config = TradingConfig(scan_end="15:00")

        result = ExitManager.check_eod_flatten(dtime(15, 15), config)
        assert result == ExitReason.EOD_FLATTEN
