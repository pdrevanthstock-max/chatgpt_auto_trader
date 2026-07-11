import pytest
from datetime import datetime
from core.models import Trade
from core.enums import ExitReason, MarketRegime, TradeDirection, TradePhase
from config.settings import TradingConfig
from strategy.exit_manager import ExitManager

def test_exit_manager_giveback_and_target():
    config = TradingConfig(giveback_pct=0.10)
    manager = ExitManager()

    # LONG_CE trade in DIRECTIONAL mode (so target exit is not checked)
    trade = Trade(
        direction=TradeDirection.LONG_CE,
        strike_ce=24300,
        strike_pe=24300,
        entry_ce_price=100.0,
        entry_pe_price=100.0,
        quantity=1,
        lot_size=65,
        entry_time=datetime.now(),
        regime_at_entry=MarketRegime.DIRECTIONAL,
        phase=TradePhase.PHASE_1_BOTH_LEGS
    )

    # 1. Profitable price update -> peak combined PnL should be set
    # CE goes 100 -> 120 (+20), PE goes 100 -> 110 (+10) -> PnL = +30 * 65 = +1950
    exit_res = manager.check_exits(trade, 120.0, 110.0, 50.0, False, config)
    assert exit_res is None
    assert trade.peak_combined_pnl == 1950.0

    # 2. Giveback check: PnL falls below peak * 0.90 (below 1755.0)
    # CE goes 120 -> 110, PE goes 110 -> 105 -> PnL = +15 * 65 = +975
    exit_res = manager.check_exits(trade, 110.0, 105.0, 50.0, False, config)
    assert exit_res == ExitReason.GIVEBACK
