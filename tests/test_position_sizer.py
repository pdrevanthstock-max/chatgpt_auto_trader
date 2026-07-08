"""
Tests: Position Sizer
──────────────────────
Unit tests for capital → lot quantity calculation.
"""

import pytest

from config.settings import TradingConfig
from strategy.position_sizer import PositionSizer


class TestPositionSizer:

    def test_basic_sizing(self):
        """With 30K capital, CE=200, PE=200 → cost per lot = 400×25 = 10K → 3 lots max, capped to 1."""
        config = TradingConfig(total_capital=30000, nifty_lot_size=25)
        qty = PositionSizer.calculate_quantity(200.0, 200.0, config)
        assert qty == 1  # Capped at 1 for v1

    def test_insufficient_capital(self):
        """Capital too low for even 1 lot → 0."""
        config = TradingConfig(total_capital=1000, nifty_lot_size=25)
        qty = PositionSizer.calculate_quantity(500.0, 500.0, config)
        # Cost = 1000 * 25 = 25,000 > 1000
        assert qty == 0

    def test_zero_price_returns_zero(self):
        """Zero price should not crash, returns 0."""
        config = TradingConfig(total_capital=30000)
        qty = PositionSizer.calculate_quantity(0.0, 100.0, config)
        assert qty == 0

    def test_negative_price_returns_zero(self):
        config = TradingConfig(total_capital=30000)
        qty = PositionSizer.calculate_quantity(-10.0, 100.0, config)
        assert qty == 0

    def test_capital_per_trade_calculation(self):
        """Capital allocated to a trade = (CE + PE) × qty × lot_size."""
        config = TradingConfig(nifty_lot_size=25)
        capital = PositionSizer.calculate_capital_per_trade(
            ce_price=200, pe_price=150, quantity=1, config=config,
        )
        assert capital == (200 + 150) * 1 * 25  # = 8750

    def test_equal_quantities_enforced(self):
        """The sizer returns ONE quantity used for BOTH legs (§4.6)."""
        config = TradingConfig(total_capital=30000, nifty_lot_size=25)
        qty = PositionSizer.calculate_quantity(100.0, 100.0, config)
        # Both legs use `qty` — there's no separate CE/PE quantity
        assert isinstance(qty, int)
        assert qty > 0
