from data.market_cache import market_cache
from strategy.pair_candidate_generator import PairCandidateGenerator
from strategy.pair_templates import PairTemplateGenerator
from core.enums import MarketRegime
from datetime import date


def test_normal_template_crosses_atm_and_four_itm_steps_without_otm_contracts():
    strikes = range(23_800, 24_401, 50)

    pairs = PairTemplateGenerator.atm_itm_cross(
        ce_strikes=strikes,
        pe_strikes=strikes,
        spot=24_128,
        strike_step=50,
        depth=4,
        include_atm=True,
    )

    assert len(pairs) == 25
    assert {ce for ce, _ in pairs} == {24_150, 24_100, 24_050, 24_000, 23_950}
    assert {pe for _, pe in pairs} == {24_150, 24_200, 24_250, 24_300, 24_350}
    assert all(ce <= 24_150 and pe >= 24_150 for ce, pe in pairs)


def test_sideways_expiry_template_excludes_every_atm_layout():
    strikes = range(23_800, 24_401, 50)

    pairs = PairTemplateGenerator.atm_itm_cross(
        ce_strikes=strikes,
        pe_strikes=strikes,
        spot=24_128,
        strike_step=50,
        depth=4,
        include_atm=False,
    )

    assert len(pairs) == 16
    assert all(ce != 24_150 and pe != 24_150 for ce, pe in pairs)


def test_live_candidate_generator_exposes_bounded_atm_itm_cross_template():
    market_cache.clear()
    market_cache.update_spot(24_128, __import__("datetime").datetime.now())
    for strike in range(23_800, 24_401, 50):
        for option_type in ("CE", "PE"):
            market_cache.update_option(strike, option_type, {"last": 100.0})

    candidates = PairCandidateGenerator(strike_step=50).generate_candidates()

    assert len(candidates) == 25
    assert (23_950, 24_350) in candidates


def test_live_candidate_generator_uses_sixteen_itm_pairs_on_sideways_expiry():
    market_cache.clear()
    market_cache.update_spot(24_128, __import__("datetime").datetime.now())
    market_cache.set_active_expiry(date.today())
    for strike in range(23_800, 24_401, 50):
        for option_type in ("CE", "PE"):
            market_cache.update_option(strike, option_type, {"last": 100.0})

    candidates = PairCandidateGenerator(strike_step=50).generate_candidates(
        MarketRegime.SIDEWAYS,
        date.today(),
    )

    assert len(candidates) == 16
    assert all(ce != 24_150 and pe != 24_150 for ce, pe in candidates)
