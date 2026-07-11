import pytest
from config.settings import TradingConfig
from strategy.daily_circuit_breaker import DailyCircuitBreaker

def test_daily_circuit_breaker():
    config = TradingConfig(total_capital=30000.0, daily_loss_limit_pct=0.03) # 3% limit = Rs 900
    breaker = DailyCircuitBreaker()

    # PnL above limit
    assert not breaker.is_breaker_triggered(-500.0, config)
    # PnL exactly at limit
    assert breaker.is_breaker_triggered(-900.0, config)
    # PnL beyond limit
    assert breaker.is_breaker_triggered(-1200.0, config)
