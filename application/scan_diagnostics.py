from __future__ import annotations

from datetime import datetime
from typing import Iterable, Mapping

from config.settings import TradingConfig
from core.enums import MarketRegime
from core.models import CandidatePair


def build_scan_diagnostics(
    *,
    scanned: Iterable[CandidatePair],
    survivors: Iterable[CandidatePair],
    ranker_decisions: Mapping[tuple[object, object], Mapping[str, object]],
    regime: MarketRegime,
    spot_trend: str,
    config: TradingConfig,
    index_symbol: str,
    spot_price: float = 0.0,
) -> list[dict[str, object]]:
    survivor_keys = {(row.ce_strike, row.pe_strike) for row in survivors}
    upper = (
        config.directional_divergence_band_max
        if regime == MarketRegime.DIRECTIONAL
        else config.divergence_band_max
    )
    rows: list[dict[str, object]] = []
    for candidate in scanned:
        key = (candidate.ce_strike, candidate.pe_strike)
        reason = "SIGNAL_PASSED"
        result = "PASS"
        details: dict[str, object] = {}
        if key not in survivor_keys:
            result = "FAIL"
            if candidate.ce_velocity <= 0.0 and candidate.pe_velocity <= 0.0:
                reason = "DUAL_DECAY"
            elif not (config.divergence_band_min <= candidate.divergence <= upper):
                reason = f"DIVERGENCE_OUTSIDE_{config.divergence_band_min:g}_TO_{upper:g}"
            elif (
                spot_price > 0.0
                and candidate.ce_strike > spot_price
                and candidate.pe_strike < spot_price
            ):
                reason = "BOTH_OTM_LAYOUT"
            elif regime == MarketRegime.DIRECTIONAL and (
                (spot_trend == "UP" and candidate.winning_leg != "CE")
                or (spot_trend == "DOWN" and candidate.winning_leg != "PE")
            ):
                reason = "DIRECTIONAL_WINNER_MISMATCH"
            else:
                reason = "ENTRY_SIGNAL_REJECTED"
        else:
            decision = dict(ranker_decisions.get(key, {}))
            if decision:
                result = str(decision.pop("result", "FAIL"))
                reason = str(decision.pop("reason", "RANKING_REJECTED"))
                details = decision
            else:
                result, reason = "FAIL", "RANKING_NOT_EVALUATED"
        rows.append(
            {
                "timestamp": datetime.now().isoformat(),
                "index": index_symbol,
                "regime": regime.value,
                "spot_trend": spot_trend,
                "ce_strike": candidate.ce_strike,
                "pe_strike": candidate.pe_strike,
                "ce_velocity": candidate.ce_velocity,
                "pe_velocity": candidate.pe_velocity,
                "divergence": candidate.divergence,
                "winning_leg": candidate.winning_leg,
                "result": result,
                "reason": reason,
                **details,
            }
        )
    rows.sort(
        key=lambda row: (
            row["result"] != "PASS",
            -float(row.get("projected_net", float("-inf"))),
            -float(row["divergence"]),
        )
    )
    return rows
