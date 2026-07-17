import pytest
from core.enums import MarketRegime
from core.models import CandidatePair
from data.market_cache import market_cache
from config.settings import TradingConfig
from strategy.pair_ranker import PairRanker

def test_pair_ranker_premium_similarity_filter():
    # Setup configuration
    config = TradingConfig(execution_mode="BACKTEST")
    ranker = PairRanker()

    # Clear and populate cache
    market_cache.clear()

    # Pair 1: balanced premiums (80 vs 85, difference is ~6%)
    market_cache.update_option(24000, "CE", {
        "last": 80.0,
        "volume": 1000,
        "oi": 5000,
    })
    market_cache.update_option(24000, "PE", {
        "last": 85.0,
        "volume": 1000,
        "oi": 5000,
    })

    # Pair 2: heavily skewed premiums (20 vs 250, difference is ~170%)
    market_cache.update_option(24100, "CE", {
        "last": 20.0,
        "volume": 1000,
        "oi": 5000,
    })
    market_cache.update_option(24100, "PE", {
        "last": 250.0,
        "volume": 1000,
        "oi": 5000,
    })

    # Create candidate pairs
    c1 = CandidatePair(24000, 24000, 2.0, 1.0, 1.5, "CE") # Should pass
    c2 = CandidatePair(24100, 24100, 2.0, 1.0, 1.5, "CE") # Should fail premium similarity check

    # Evaluate ranker
    top_candidate = ranker.rank_candidates([c1, c2], config)

    # Assertions
    assert top_candidate is not None
    assert top_candidate.ce_strike == 24000
    assert top_candidate.pe_strike == 24000
    assert top_candidate.projected_net_profit >= config.minimum_projected_net_profit
    assert ranker.last_decisions[(24000, 24000)]["lots"] > 1
    assert ranker.last_decisions[(24100, 24100)]["reason"] == "PREMIUM_RATIO_EXCEEDED"


def test_sideways_guarded_buffer_uses_stricter_economics_than_normal_zone():
    config = TradingConfig(
        minimum_projected_net_profit=100.0,
        minimum_projected_return_pct=0.25,
        sideways_buffer_minimum_projected_net_profit=200.0,
        sideways_buffer_minimum_projected_return_pct=0.5,
    )
    ranker = PairRanker()
    normal = CandidatePair(24_000, 24_000, 3.0, 1.0, 2.0, "CE")
    lower_buffer = CandidatePair(24_000, 24_000, 1.8, 1.0, 0.8, "CE")
    upper_buffer = CandidatePair(24_000, 24_000, 6.5, 1.0, 5.5, "CE")
    directional = CandidatePair(24_000, 24_000, 6.5, 1.0, 5.5, "CE")

    assert ranker.economic_thresholds(normal, MarketRegime.SIDEWAYS, config) == (100.0, 0.25)
    assert ranker.economic_thresholds(lower_buffer, MarketRegime.SIDEWAYS, config) == (200.0, 0.5)
    assert ranker.economic_thresholds(upper_buffer, MarketRegime.SIDEWAYS, config) == (200.0, 0.5)
    assert ranker.economic_thresholds(directional, MarketRegime.DIRECTIONAL, config) == (100.0, 0.25)


def test_otm_research_ranker_enforces_minimum_fifteen_rupee_ask():
    market_cache.clear()
    market_cache.update_spot(24_128, __import__("datetime").datetime.now())
    market_cache.update_option(24_200, "CE", {"last": 15.0, "bid": 14.5, "ask": 14.99})
    market_cache.update_option(24_100, "PE", {"last": 20.0, "bid": 19.5, "ask": 20.0})
    candidate = CandidatePair(24_200, 24_100, 4.0, 1.0, 3.0, "CE")
    ranker = PairRanker()

    result = ranker.rank_candidates(
        [candidate],
        TradingConfig(execution_mode="PAPER", otm_research_enabled=True),
        regime=MarketRegime.DIRECTIONAL,
    )

    assert result is None
    assert ranker.last_decisions[(24_200, 24_100)]["reason"] == "OTM_RESEARCH_MINIMUM_ASK"
