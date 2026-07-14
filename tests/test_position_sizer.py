import pytest
from config.settings import TradingConfig
from strategy.position_sizer import PositionSizer

def test_position_sizer():
    config = TradingConfig(total_capital=30000.0, nifty_lot_size=65)
    sizer = PositionSizer()

    # Premium CE=100.0, PE=100.0 -> Combined=200.0. Lot cost = 200 * 65 = 13000
    # Qty = floor(30000 / 13000) = 2 lots
    lots = sizer.calculate_lots(100.0, 100.0, config)
    assert lots == 2

    # Insufficient capital
    lots_insufficient = sizer.calculate_lots(300.0, 300.0, config) # cost = 600 * 65 = 39000 > 30000
    assert lots_insufficient == 0

    # Zero price guards
    assert sizer.calculate_lots(0.0, 100.0, config) == 0


def test_position_sizer_keeps_quantity_dynamic_but_caps_low_premium_pair():
    config = TradingConfig(total_capital=45000.0, nifty_lot_size=65)

    lots = PositionSizer().calculate_lots(1.95, 1.90, config)

    assert lots == 27
    assert lots * config.nifty_lot_size == 1_755


def test_position_sizer_uses_remaining_available_capital():
    config = TradingConfig(total_capital=45_000.0, nifty_lot_size=65)

    lots = PositionSizer().calculate_lots(
        100.0, 100.0, config, available_capital=20_000.0
    )

    assert lots == 1
