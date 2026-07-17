from application.scan_diagnostics import ScanFunnel, build_scan_diagnostics
from config.settings import TradingConfig
from core.enums import MarketRegime
from core.models import CandidatePair


def test_scan_diagnostics_explains_dual_decay_band_direction_and_profitability():
    dual_decay = CandidatePair(24000, 24000, -1.0, -2.0, 1.0, "CE")
    outside = CandidatePair(24050, 24050, 8.0, 1.0, 7.0, "CE")
    profitable = CandidatePair(24100, 24100, 3.0, 1.0, 2.0, "CE")

    rows = build_scan_diagnostics(
        scanned=[dual_decay, outside, profitable],
        survivors=[profitable],
        ranker_decisions={(24100, 24100): {"result": "FAIL", "reason": "PROJECTED_NET_BUFFER_FAILED", "projected_net": -20.0}},
        regime=MarketRegime.SIDEWAYS,
        spot_trend="SIDEWAYS",
        config=TradingConfig(),
        index_symbol="NIFTY",
    )

    by_strike = {row["ce_strike"]: row for row in rows}
    assert by_strike[24000]["reason"] == "DUAL_DECAY"
    assert by_strike[24050]["reason"] == "DIVERGENCE_OUTSIDE_0.75_TO_6"
    assert by_strike[24100]["reason"] == "PROJECTED_NET_BUFFER_FAILED"
    assert by_strike[24100]["projected_net"] == -20.0


def test_scan_diagnostics_exposes_cycle_pair_moneyness_and_funnel_fields():
    established = CandidatePair(24000, 24000, 3.0, 1.0, 2.0, "CE")
    otm = CandidatePair(24100, 23900, 3.0, 1.0, 2.0, "CE")
    funnel = ScanFunnel(
        generated_count=29,
        quotable_count=27,
        signal_count=2,
        economic_count=1,
        final_count=1,
        prefilter_rejection_reasons={"MISSING_QUOTE": 2},
    )

    rows = build_scan_diagnostics(
        scanned=[established, otm],
        survivors=[established, otm],
        ranker_decisions={
            (24000, 24000): {"result": "PASS", "reason": "PROFITABILITY_BUFFER_PASSED"},
            (24100, 23900): {"result": "FAIL", "reason": "PREMIUM_RATIO_EXCEEDED"},
        },
        regime=MarketRegime.DIRECTIONAL,
        spot_trend="UP",
        config=TradingConfig(),
        index_symbol="NIFTY",
        spot_price=24020.0,
        atm_strike=24000,
        strike_step=50,
        cycle_id="2026-07-17T09:31:00+05:30",
        funnel=funnel,
    )

    by_pair = {(row["ce_strike"], row["pe_strike"]): row for row in rows}
    assert by_pair[(24000, 24000)]["pair_class"] == "ATM_ITM"
    assert by_pair[(24100, 23900)]["pair_class"] == "OTM_RESEARCH"
    assert by_pair[(24100, 23900)]["moneyness"] == "CE_OTM2/PE_OTM2"
    for row in rows:
        assert row["cycle_id"] == "2026-07-17T09:31:00+05:30"
        assert row["spot"] == 24020.0
        assert row["atm"] == 24000
        assert row["generated_count"] == 29
        assert row["quotable_count"] == 27
        assert row["signal_count"] == 2
        assert row["economic_count"] == 1
        assert row["final_count"] == 1
        assert row["prefilter_rejection_reasons"] == {"MISSING_QUOTE": 2}


def test_scan_diagnostics_classifies_both_otm_from_spot_without_atm_metadata():
    otm = CandidatePair(24100, 23900, 3.0, 1.0, 2.0, "CE")

    rows = build_scan_diagnostics(
        scanned=[otm],
        survivors=[],
        ranker_decisions={},
        regime=MarketRegime.DIRECTIONAL,
        spot_trend="UP",
        config=TradingConfig(),
        index_symbol="NIFTY",
        spot_price=24020.0,
    )

    assert rows[0]["pair_class"] == "OTM_RESEARCH"
