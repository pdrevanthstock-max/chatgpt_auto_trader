from datetime import date, datetime, timedelta

import pytest

from config.settings import TradingConfig
from core.enums import MarketRegime, OrderType
from core.models import ScoredCandidate, TradePlan
from data.market_cache import market_cache
from execution.execution_validator import ExecutionValidator


def _plan(quantity: int = 1) -> TradePlan:
    candidate = ScoredCandidate(
        ce_strike=24300,
        pe_strike=24300,
        ce_velocity=2.0,
        pe_velocity=1.0,
        divergence=1.0,
        winning_leg="CE",
        projected_net_profit=500.0,
        confidence=0.8,
    )
    return TradePlan(
        scored_candidate=candidate,
        regime=MarketRegime.DIRECTIONAL,
        order_type=OrderType.MARKET,
        quantity=quantity,
    )


def _valid_quote(timestamp: datetime) -> dict:
    return {
        "bid": 100.0,
        "ask": 101.0,
        "last": 100.5,
        "open": 99.0,
        "volume": 1000,
        "oi": 2000,
        "timestamp": timestamp,
    }


def test_validator_blocks_cache_older_than_configured_limit():
    market_cache.clear()
    now = datetime.now()
    market_cache.update_option(24300, "CE", _valid_quote(now))
    market_cache.update_option(24300, "PE", _valid_quote(now))

    with market_cache._lock:
        market_cache._last_update = datetime.now() - timedelta(seconds=11)

    valid, reason = ExecutionValidator().validate_entry(
        _plan(),
        realized_pnl=0.0,
        active_trade=None,
        config=TradingConfig(
            execution_mode="PAPER",
            health_check_cache_stale_sec=10,
        ),
    )

    assert valid is False
    assert "MarketCache is stale" in reason


def test_clear_resets_cache_health_state():
    market_cache.clear()
    market_cache.update_option(24300, "CE", _valid_quote(datetime.now()))
    market_cache.update_health(latency_ms=250)

    market_cache.clear()

    assert market_cache.get_health() == (None, 0)


def test_validator_checks_selected_contract_timestamps_not_only_global_cache():
    market_cache.clear()
    stale = datetime.now() - timedelta(seconds=30)
    market_cache.update_option(24300, "CE", _valid_quote(stale))
    market_cache.update_option(24300, "PE", _valid_quote(stale))
    market_cache.update_option(24400, "CE", _valid_quote(datetime.now()))

    valid, reason = ExecutionValidator().validate_entry(
        _plan(),
        realized_pnl=0.0,
        active_trade=None,
        config=TradingConfig(execution_mode="PAPER", health_check_cache_stale_sec=10),
    )

    assert valid is False
    assert "selected contract" in reason


def test_validator_rejects_pair_when_both_contracts_are_otm():
    market_cache.clear()
    now = datetime.now()
    market_cache.update_spot(24_000.0, now)
    market_cache.update_option(24_350, "CE", _valid_quote(now))
    market_cache.update_option(23_750, "PE", _valid_quote(now))
    plan = _plan()
    plan.scored_candidate = ScoredCandidate(
        ce_strike=24_350,
        pe_strike=23_750,
        ce_velocity=2.0,
        pe_velocity=1.0,
        divergence=1.0,
        winning_leg="CE",
        projected_net_profit=500.0,
        confidence=80.0,
    )

    valid, reason = ExecutionValidator().validate_entry(
        plan, 0.0, None, TradingConfig(execution_mode="PAPER")
    )

    assert valid is False
    assert "both OTM" in reason


def test_validator_rejects_sideways_entry_near_expiry():
    market_cache.clear()
    now = datetime.now()
    market_cache.update_spot(24_300.0, now)
    market_cache.set_active_expiry(date.today())
    market_cache.update_option(24_300, "CE", _valid_quote(now))
    market_cache.update_option(24_300, "PE", _valid_quote(now))
    plan = _plan()
    plan.regime = MarketRegime.SIDEWAYS

    valid, reason = ExecutionValidator().validate_entry(
        plan, 0.0, None, TradingConfig(execution_mode="PAPER")
    )

    assert valid is False
    assert "expiry guard" in reason


def test_validator_blocks_dynamic_quantity_when_asks_exceed_available_capital():
    market_cache.clear()
    now = datetime.now()
    market_cache.update_option(
        24300,
        "CE",
        {"bid": 1.90, "ask": 2.00, "last": 1.95, "open": 1.95, "timestamp": now},
    )
    market_cache.update_option(
        24300,
        "PE",
        {"bid": 1.90, "ask": 2.00, "last": 1.95, "open": 1.95, "timestamp": now},
    )

    valid, reason = ExecutionValidator().validate_entry(
        _plan(quantity=179),
        realized_pnl=0.0,
        active_trade=None,
        config=TradingConfig(execution_mode="PAPER", total_capital=45_000.0),
    )

    assert valid is False
    assert "exceeds available capital" in reason


@pytest.mark.parametrize(
    "quote",
    [
        {"last": 0.0},
        {"last": -1.0},
        {"last": float("nan")},
        {"last": float("inf")},
        {"bid": 100.0, "ask": 101.0},
        {"bid": "100", "ask": 101.0, "last": 100.5},
        {"bid": 102.0, "ask": 101.0, "last": 101.5},
    ],
)
def test_update_option_rejects_invalid_or_inverted_prices(quote):
    market_cache.clear()

    with pytest.raises(ValueError, match="Invalid option quote"):
        market_cache.update_option(24300, "CE", quote)

    assert market_cache.get_option(24300, "CE") is None
