from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Mapping

from config.settings import TradingConfig
from core.enums import MarketRegime
from core.models import CandidatePair


@dataclass(frozen=True)
class ScanFunnel:
    generated_count: int | None = None
    quotable_count: int | None = None
    signal_count: int | None = None
    economic_count: int | None = None
    final_count: int | None = None
    prefilter_rejection_reasons: Mapping[str, int] = field(default_factory=dict)

    def as_fields(self) -> dict[str, object]:
        return {
            "generated_count": self.generated_count,
            "quotable_count": self.quotable_count,
            "signal_count": self.signal_count,
            "economic_count": self.economic_count,
            "final_count": self.final_count,
            "prefilter_rejection_reasons": dict(self.prefilter_rejection_reasons),
        }


def _moneyness(strike: object, option_type: str, atm: int, step: int) -> str:
    numeric_strike = float(strike)
    if numeric_strike == atm:
        return f"{option_type}_ATM"
    distance = max(1, int(round(abs(numeric_strike - atm) / step)))
    is_itm = (
        option_type == "CE" and numeric_strike < atm
    ) or (
        option_type == "PE" and numeric_strike > atm
    )
    return f"{option_type}_{'ITM' if is_itm else 'OTM'}{distance}"


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
    atm_strike: int | None = None,
    strike_step: int | None = None,
    cycle_id: str | None = None,
    funnel: ScanFunnel | None = None,
) -> list[dict[str, object]]:
    scanned_rows = list(scanned)
    survivor_rows = list(survivors)
    survivor_keys = {(row.ce_strike, row.pe_strike) for row in survivor_rows}
    lower = (
        config.divergence_band_min
        if regime == MarketRegime.DIRECTIONAL
        else config.sideways_divergence_buffer_min
    )
    upper = (
        config.directional_divergence_band_max
        if regime == MarketRegime.DIRECTIONAL
        else config.sideways_divergence_buffer_max
    )
    captured_at = datetime.now().isoformat()
    resolved_cycle_id = cycle_id or captured_at
    known_funnel = funnel or ScanFunnel(
        quotable_count=len(scanned_rows),
        signal_count=len(survivor_rows),
        economic_count=sum(
            1 for decision in ranker_decisions.values()
            if str(decision.get("result", "")).upper() == "PASS"
        ),
    )
    resolved_atm = int(atm_strike or 0)
    resolved_step = int(strike_step or 0)
    rows: list[dict[str, object]] = []
    for candidate in scanned_rows:
        key = (candidate.ce_strike, candidate.pe_strike)
        reason = "SIGNAL_PASSED"
        result = "PASS"
        details: dict[str, object] = {}
        if key not in survivor_keys:
            result = "FAIL"
            if candidate.ce_velocity <= 0.0 and candidate.pe_velocity <= 0.0:
                reason = "DUAL_DECAY"
            elif not (lower <= candidate.divergence <= upper):
                reason = f"DIVERGENCE_OUTSIDE_{lower:g}_TO_{upper:g}"
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
        ce_moneyness = None
        pe_moneyness = None
        pair_class = (
            "OTM_RESEARCH"
            if spot_price > 0.0
            and candidate.ce_strike > spot_price
            and candidate.pe_strike < spot_price
            else "ATM_ITM"
        )
        if resolved_atm > 0 and resolved_step > 0:
            ce_moneyness = _moneyness(candidate.ce_strike, "CE", resolved_atm, resolved_step)
            pe_moneyness = _moneyness(candidate.pe_strike, "PE", resolved_atm, resolved_step)
            if "_OTM" in ce_moneyness and "_OTM" in pe_moneyness:
                pair_class = "OTM_RESEARCH"
        rows.append(
            {
                "timestamp": captured_at,
                "cycle_id": resolved_cycle_id,
                "index": index_symbol,
                "pair_class": pair_class,
                "spot": float(spot_price),
                "atm": resolved_atm or None,
                "ce_moneyness": ce_moneyness,
                "pe_moneyness": pe_moneyness,
                "moneyness": (
                    f"{ce_moneyness}/{pe_moneyness}"
                    if ce_moneyness and pe_moneyness else None
                ),
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
                **known_funnel.as_fields(),
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
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows
