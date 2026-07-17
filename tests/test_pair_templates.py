from data.market_cache import market_cache
from strategy.pair_candidate_generator import PairCandidateGenerator
from strategy.pair_templates import PairTemplateGenerator
from core.enums import MarketRegime
from datetime import date, datetime, time
from config.settings import TradingConfig


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


def test_otm_research_adds_exactly_four_pairs_without_changing_established_twenty_five():
    strikes = range(23_800, 24_501, 50)

    established = PairTemplateGenerator.bounded_universe(
        ce_strikes=strikes,
        pe_strikes=strikes,
        spot=24_128,
        strike_step=50,
        depth=4,
        include_atm=True,
        include_otm_research=False,
    )
    with_research = PairTemplateGenerator.bounded_universe(
        ce_strikes=strikes,
        pe_strikes=strikes,
        spot=24_128,
        strike_step=50,
        depth=4,
        include_atm=True,
        include_otm_research=True,
    )

    assert len(established) == 25
    assert with_research[:25] == established
    assert with_research[25:] == [
        (24_200, 24_100),
        (24_200, 24_050),
        (24_250, 24_100),
        (24_250, 24_050),
    ]


def test_candidate_generator_enables_otm_only_for_paper_directional_before_expiry_cutoff():
    market_cache.clear()
    market_cache.update_spot(24_128, datetime(2026, 7, 17, 11, 59))
    market_cache.set_active_expiry(date(2026, 7, 17))
    for strike in range(23_800, 24_501, 50):
        for option_type in ("CE", "PE"):
            market_cache.update_option(strike, option_type, {"last": 100.0})
    generator = PairCandidateGenerator(strike_step=50)
    paper = TradingConfig(execution_mode="PAPER", otm_research_enabled=True)

    enabled = generator.generate_candidates(
        MarketRegime.DIRECTIONAL,
        date(2026, 7, 17),
        config=paper,
        now=datetime.combine(date(2026, 7, 17), time(11, 59)),
    )
    live = generator.generate_candidates(
        MarketRegime.DIRECTIONAL,
        date(2026, 7, 17),
        config=TradingConfig(execution_mode="LIVE", otm_research_enabled=True),
        now=datetime.combine(date(2026, 7, 17), time(11, 59)),
    )
    sideways = generator.generate_candidates(
        MarketRegime.SIDEWAYS,
        date(2026, 7, 17),
        config=paper,
        now=datetime.combine(date(2026, 7, 17), time(11, 59)),
    )
    cutoff = generator.generate_candidates(
        MarketRegime.DIRECTIONAL,
        date(2026, 7, 17),
        config=paper,
        now=datetime.combine(date(2026, 7, 17), time(12, 0)),
    )

    assert len(enabled) == 29
    assert len(live) == 25
    assert len(sideways) == 16
    assert len(cutoff) == 25
