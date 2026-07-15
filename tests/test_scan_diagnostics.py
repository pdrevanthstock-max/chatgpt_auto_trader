from application.scan_diagnostics import build_scan_diagnostics
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
    assert by_strike[24050]["reason"] == "DIVERGENCE_OUTSIDE_1_TO_5"
    assert by_strike[24100]["reason"] == "PROJECTED_NET_BUFFER_FAILED"
    assert by_strike[24100]["projected_net"] == -20.0
