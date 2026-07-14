import pytest
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
    assert top_candidate.projected_net_profit == 29.42
