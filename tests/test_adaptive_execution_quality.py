from datetime import datetime

from config.settings import TradingConfig
from core.enums import MarketRegime, OrderType
from core.models import CandidatePair, ScoredCandidate, TradePlan
from data.market_cache import market_cache
from execution.execution_validator import ExecutionValidator
from strategy.liquidity_filter import LiquidityFilter
from strategy.pair_ranker import PairRanker


def _quote(bid: float, ask: float, *, volume: int = 0, oi: int = 0) -> dict:
    return {
        "bid": bid,
        "ask": ask,
        "last": (bid + ask) / 2.0,
        "open": (bid + ask) / 2.0,
        "volume": volume,
        "oi": oi,
        "timestamp": datetime.now(),
    }


def _plan(regime: MarketRegime) -> TradePlan:
    return TradePlan(
        scored_candidate=ScoredCandidate(
            ce_strike=24_300,
            pe_strike=24_300,
            ce_velocity=10.0,
            pe_velocity=8.0,
            divergence=2.0,
            winning_leg="CE",
            projected_net_profit=500.0,
            confidence=75.0,
        ),
        regime=regime,
        order_type=(
            OrderType.MARKET
            if regime == MarketRegime.DIRECTIONAL
            else OrderType.LIMIT
        ),
        quantity=1,
        lot_size=65,
        ce_limit_price=102.0 if regime == MarketRegime.SIDEWAYS else None,
        pe_limit_price=102.0 if regime == MarketRegime.SIDEWAYS else None,
    )


def test_low_volume_and_oi_do_not_block_an_executable_contract():
    market_cache.clear()
    market_cache.update_option(
        24_300,
        "CE",
        _quote(99.0, 101.0, volume=1, oi=1),
    )

    result = LiquidityFilter().filter_strikes(
        [24_300],
        "CE",
        TradingConfig(execution_mode="PAPER"),
    )

    assert result == [24_300]


def test_low_volume_and_oi_reduce_confidence_without_rejecting_profitable_pair():
    market_cache.clear()
    market_cache.update_option(
        24_300,
        "CE",
        _quote(79.0, 80.0, volume=1, oi=1),
    )
    market_cache.update_option(
        24_300,
        "PE",
        _quote(84.0, 85.0, volume=1, oi=1),
    )
    candidate = CandidatePair(24_300, 24_300, 20.0, 10.0, 10.0, "CE")

    selected = PairRanker().rank_candidates(
        [candidate],
        TradingConfig(
            execution_mode="PAPER",
            minimum_projected_net_profit=0.0,
            minimum_projected_return_pct=0.0,
        ),
    )

    assert selected is not None
    assert selected.confidence == 70.0


def test_sideways_limit_entry_allows_moderate_four_percent_combined_spread():
    market_cache.clear()
    market_cache.update_option(24_300, "CE", _quote(98.0, 102.0))
    market_cache.update_option(24_300, "PE", _quote(98.0, 102.0))

    valid, reason = ExecutionValidator().validate_entry(
        _plan(MarketRegime.SIDEWAYS),
        realized_pnl=0.0,
        active_trade=None,
        config=TradingConfig(execution_mode="PAPER"),
    )

    assert valid is True, reason


def test_directional_market_entry_rejects_same_four_percent_combined_spread():
    market_cache.clear()
    market_cache.update_option(24_300, "CE", _quote(98.0, 102.0))
    market_cache.update_option(24_300, "PE", _quote(98.0, 102.0))

    valid, reason = ExecutionValidator().validate_entry(
        _plan(MarketRegime.DIRECTIONAL),
        realized_pnl=0.0,
        active_trade=None,
        config=TradingConfig(execution_mode="PAPER"),
    )

    assert valid is False
    assert "DIRECTIONAL" in reason


def test_sideways_limit_entry_rejects_extreme_six_percent_combined_spread():
    market_cache.clear()
    market_cache.update_option(24_300, "CE", _quote(97.0, 103.0))
    market_cache.update_option(24_300, "PE", _quote(97.0, 103.0))

    valid, reason = ExecutionValidator().validate_entry(
        _plan(MarketRegime.SIDEWAYS),
        realized_pnl=0.0,
        active_trade=None,
        config=TradingConfig(execution_mode="PAPER"),
    )

    assert valid is False
    assert "SIDEWAYS" in reason
