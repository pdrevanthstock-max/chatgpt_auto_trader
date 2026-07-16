import pytest

from config.settings import TradingConfig
from core.enums import MarketRegime, OrderType
from core.models import ScoredCandidate
from strategy.trade_planner import TradePlanner


def _candidate() -> ScoredCandidate:
    return ScoredCandidate(
        ce_strike=24_300,
        pe_strike=24_300,
        ce_velocity=2.0,
        pe_velocity=1.0,
        divergence=1.0,
        winning_leg="CE",
        projected_net_profit=500.0,
        confidence=80.0,
    )


def test_sideways_plan_places_each_buy_limit_at_top_of_book_midpoint():
    plan = TradePlanner().plan_trade(
        candidate=_candidate(),
        regime=MarketRegime.SIDEWAYS,
        quantity=1,
        ce_price=102.0,
        pe_price=202.0,
        ce_bid=99.0,
        pe_bid=198.0,
        config=TradingConfig(execution_mode="PAPER"),
    )

    assert plan.order_type == OrderType.LIMIT
    assert plan.ce_limit_price == 100.50
    assert plan.pe_limit_price == 200.00


def test_sideways_plan_fails_closed_without_valid_bids():
    with pytest.raises(ValueError, match="SIDEWAYS limit pricing"):
        TradePlanner().plan_trade(
            candidate=_candidate(),
            regime=MarketRegime.SIDEWAYS,
            quantity=1,
            ce_price=102.0,
            pe_price=202.0,
            ce_bid=0.0,
            pe_bid=198.0,
            config=TradingConfig(execution_mode="PAPER"),
        )


def test_directional_plan_remains_marketable_without_limit_prices():
    plan = TradePlanner().plan_trade(
        candidate=_candidate(),
        regime=MarketRegime.DIRECTIONAL,
        quantity=1,
        ce_price=102.0,
        pe_price=202.0,
        config=TradingConfig(execution_mode="PAPER"),
    )

    assert plan.order_type == OrderType.MARKET
    assert plan.ce_limit_price is None
    assert plan.pe_limit_price is None
