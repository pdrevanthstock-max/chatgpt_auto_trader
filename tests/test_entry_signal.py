import pytest
from core.models import CandidatePair
from core.enums import MarketRegime
from config.settings import TradingConfig
from strategy.entry_signal import EntrySignal

def test_entry_signal_band_and_consistency():
    config = TradingConfig(divergence_band_min=1.0, divergence_band_max=5.0)
    evaluator = EntrySignal()

    # Candidate 1: divergence = 2.0 (inside band), winning leg CE
    c1 = CandidatePair(24300, 24300, 3.0, 1.0, 2.0, "CE")
    # Candidate 2: divergence = 6.0 (guarded SIDEWAYS edge, inside DIRECTIONAL)
    c2 = CandidatePair(24300, 24400, 7.0, 1.0, 6.0, "CE")
    # Candidate 3: divergence = 2.0 (inside band), winning leg PE
    c3 = CandidatePair(24400, 24300, 1.0, 3.0, 2.0, "PE")

    candidates = [c1, c2, c3]

    # Test 1: Sideways mode (no directional consistency needed, only band)
    res_sideways = evaluator.evaluate_signals(candidates, MarketRegime.SIDEWAYS, "SIDEWAYS", config)
    assert len(res_sideways) == 3
    assert c1 in res_sideways
    assert c2 in res_sideways
    assert c3 in res_sideways

    # Test 2: Directional Bullish mode (CE must lead)
    res_bullish = evaluator.evaluate_signals(candidates, MarketRegime.DIRECTIONAL, "UP", config)
    assert len(res_bullish) == 2
    assert c1 in res_bullish
    assert c2 in res_bullish
    assert c3 not in res_bullish

    # Test 3: Directional Bearish mode (PE must lead)
    res_bearish = evaluator.evaluate_signals(candidates, MarketRegime.DIRECTIONAL, "DOWN", config)
    assert len(res_bearish) == 1
    assert c3 in res_bearish
    assert c1 not in res_bearish


@pytest.mark.parametrize(
    ("divergence", "expected"),
    [
        (0.74, False),
        (0.75, True),
        (0.99, True),
        (1.0, True),
        (5.0, True),
        (5.01, True),
        (6.0, True),
        (6.01, False),
    ],
)
def test_sideways_divergence_normal_and_guarded_buffer_boundaries(divergence, expected):
    candidate = CandidatePair(24_000, 24_000, divergence + 1.0, 1.0, divergence, "CE")

    survivors = EntrySignal().evaluate_signals(
        [candidate], MarketRegime.SIDEWAYS, "SIDEWAYS", TradingConfig()
    )

    assert (candidate in survivors) is expected


def test_eight_percent_divergence_remains_directional_only():
    candidate = CandidatePair(24_000, 24_000, 9.0, 1.0, 8.0, "CE")
    evaluator = EntrySignal()

    assert evaluator.evaluate_signals(
        [candidate], MarketRegime.SIDEWAYS, "SIDEWAYS", TradingConfig()
    ) == []
    assert evaluator.evaluate_signals(
        [candidate], MarketRegime.DIRECTIONAL, "UP", TradingConfig()
    ) == [candidate]


def test_otm_direction_gate_uses_the_selected_index_strike_step():
    candidate = CandidatePair(58_100, 57_900, 4.0, 1.0, 3.0, "CE")

    survivors = EntrySignal().evaluate_signals(
        [candidate],
        MarketRegime.DIRECTIONAL,
        "UP",
        TradingConfig(execution_mode="PAPER", otm_research_enabled=True),
        spot_price=58_025.0,
        strike_step=100,
    )

    assert survivors == [candidate]
