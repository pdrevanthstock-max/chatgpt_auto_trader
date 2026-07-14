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


def test_daily_circuit_breaker_logs_only_on_state_transition(caplog):
    config = TradingConfig(total_capital=45_000.0, daily_loss_limit_pct=0.03)
    breaker = DailyCircuitBreaker()

    with caplog.at_level("WARNING", logger="AutoTrader"):
        assert breaker.is_breaker_triggered(-2_000.0, config)
        assert breaker.is_breaker_triggered(-2_100.0, config)
        assert breaker.is_breaker_triggered(-2_200.0, config)

    messages = [r.message for r in caplog.records if "Breaker triggered" in r.message]
    assert len(messages) == 1

    assert not breaker.is_breaker_triggered(0.0, config)
    assert breaker.is_breaker_triggered(-2_000.0, config)
