from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from core.enums import MarketRegime
from strategy.otm_research_guard import OtmResearchGuard, OtmResearchInputs


def valid_inputs(**changes) -> OtmResearchInputs:
    base = OtmResearchInputs(
        execution_mode="PAPER",
        regime=MarketRegime.DIRECTIONAL,
        spot_trend="UP",
        winning_leg="CE",
        spot_price=24_128.0,
        ce_strike=24_200,
        pe_strike=24_100,
        strike_step=50,
        ce_ask=40.0,
        pe_ask=35.0,
        ce_velocity=4.0,
        pe_velocity=1.0,
        now=datetime(2026, 7, 17, 11, 59),
        expiry=date(2026, 7, 17),
        projected_net=250.0,
        projected_return_pct=0.6,
        quotes_fresh=True,
        candles_synchronized=True,
        capital_passed=True,
        price_integrity_passed=True,
        final_validation_passed=True,
    )
    return replace(base, **changes)


def test_valid_bounded_otm_research_candidate_passes():
    decision = OtmResearchGuard.evaluate(valid_inputs())

    assert decision.allowed is True
    assert decision.reason == "OTM_RESEARCH_APPROVED"
    assert decision.pair_class == "OTM_RESEARCH"


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"execution_mode": "LIVE"}, "OTM_RESEARCH_PAPER_ONLY"),
        ({"regime": MarketRegime.SIDEWAYS}, "OTM_RESEARCH_DIRECTIONAL_ONLY"),
        ({"spot_trend": "DOWN"}, "OTM_RESEARCH_DIRECTION_MISMATCH"),
        ({"winning_leg": "PE"}, "OTM_RESEARCH_DIRECTION_MISMATCH"),
        ({"ce_ask": 14.99}, "OTM_RESEARCH_MINIMUM_ASK"),
        ({"pe_ask": 14.99}, "OTM_RESEARCH_MINIMUM_ASK"),
        ({"ce_strike": 24_300}, "OTM_RESEARCH_DEPTH_EXCEEDED"),
        ({"ce_velocity": -1.0, "pe_velocity": -2.0}, "DUAL_DECAY"),
        ({"ce_ask": 100.0, "pe_ask": 39.99}, "PREMIUM_RATIO_EXCEEDED"),
        ({"projected_net": 99.99}, "PROJECTED_NET_BUFFER_FAILED"),
        ({"projected_return_pct": 0.2499}, "PROJECTED_NET_BUFFER_FAILED"),
        ({"quotes_fresh": False}, "STALE_EXECUTABLE_QUOTE"),
        ({"candles_synchronized": False}, "ASYNCHRONOUS_COMPLETED_CANDLES"),
        ({"capital_passed": False}, "INSUFFICIENT_CAPITAL"),
        ({"price_integrity_passed": False}, "PRICE_INTEGRITY_FAILED"),
        ({"final_validation_passed": False}, "FINAL_VALIDATION_FAILED"),
    ],
)
def test_otm_research_guard_rejects_each_safety_failure(changes, reason):
    assert OtmResearchGuard.evaluate(valid_inputs(**changes)).reason == reason


def test_expiry_day_cutoff_allows_1159_and_rejects_1200():
    before = OtmResearchGuard.evaluate(valid_inputs(now=datetime(2026, 7, 17, 11, 59)))
    at_cutoff = OtmResearchGuard.evaluate(valid_inputs(now=datetime(2026, 7, 17, 12, 0)))

    assert before.allowed is True
    assert at_cutoff.allowed is False
    assert at_cutoff.reason == "EXPIRY_OTM_CUTOFF"


def test_non_expiry_day_is_not_subject_to_noon_cutoff():
    decision = OtmResearchGuard.evaluate(
        valid_inputs(now=datetime(2026, 7, 16, 14, 0), expiry=date(2026, 7, 17))
    )

    assert decision.allowed is True


def test_expiry_cutoff_converts_aware_timestamps_to_ist():
    decision = OtmResearchGuard.evaluate(
        valid_inputs(now=datetime(2026, 7, 17, 6, 30, tzinfo=timezone.utc))
    )

    assert decision.allowed is False
    assert decision.reason == "EXPIRY_OTM_CUTOFF"
