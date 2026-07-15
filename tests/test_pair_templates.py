from data.market_cache import market_cache
from strategy.pair_candidate_generator import PairCandidateGenerator
from strategy.pair_templates import PairTemplateGenerator


def test_executable_template_is_nearest_matched_atm_not_cartesian_matrix():
    assert PairTemplateGenerator.matched_atm([23_950, 24_000, 24_050], spot=24_012) == [(24_000, 24_000)]


def test_live_candidate_generator_exposes_only_explicit_matched_template():
    market_cache.clear()
    market_cache.update_spot(24_012, __import__("datetime").datetime.now())
    for strike in (23_950, 24_000, 24_050):
        for option_type in ("CE", "PE"):
            market_cache.update_option(strike, option_type, {"last": 100.0})

    assert PairCandidateGenerator().generate_candidates() == [(24_000, 24_000)]
