import logging
from typing import List
from core.models import CandidatePair
from core.enums import MarketRegime
from config.settings import TradingConfig
from strategy.otm_research_guard import OtmResearchGuard

logger = logging.getLogger("AutoTrader")

class EntrySignal:
    """
    Evaluates the two entry conditions (divergence band & directional consistency)
    on each candidate pair.
    """
    def evaluate_signals(
        self,
        candidates: List[CandidatePair],
        regime: MarketRegime,
        spot_trend: str,  # "UP", "DOWN", "SIDEWAYS"
        config: TradingConfig,
        spot_price: float = 0.0,
        strike_step: int = 50,
    ) -> List[CandidatePair]:
        survivors = []
        min_band = (
            config.divergence_band_min
            if regime == MarketRegime.DIRECTIONAL
            else config.sideways_divergence_buffer_min
        )
        max_band = (
            config.directional_divergence_band_max
            if regime == MarketRegime.DIRECTIONAL
            else config.sideways_divergence_buffer_max
        )

        for candidate in candidates:
            # A less-negative option is not a winning leg. Buying both legs while
            # both premiums decay has negative edge, especially near expiry.
            if candidate.ce_velocity <= 0.0 and candidate.pe_velocity <= 0.0:
                continue
            if (
                spot_price > 0.0
                and candidate.ce_strike > spot_price
                and candidate.pe_strike < spot_price
            ):
                if not (
                    config.otm_research_enabled
                    and config.execution_mode == "PAPER"
                    and regime == MarketRegime.DIRECTIONAL
                    and OtmResearchGuard.bounded_strikes(
                        spot_price=spot_price,
                        ce_strike=candidate.ce_strike,
                        pe_strike=candidate.pe_strike,
                        strike_step=strike_step,
                    )
                    and OtmResearchGuard.direction_aligned(
                        spot_trend=spot_trend,
                        winning_leg=candidate.winning_leg,
                    )
                ):
                    continue

            # Condition 1: Divergence band check
            if not (min_band <= candidate.divergence <= max_band):
                continue

            # Condition 2: Directional consistency check
            # Spot trending UP -> CE must lead (ce_velocity >= pe_velocity)
            # Spot trending DOWN -> PE must lead (pe_velocity >= ce_velocity)
            # Spot SIDEWAYS -> no directional bias required, passes automatically
            if regime == MarketRegime.DIRECTIONAL:
                if spot_trend == "UP" and candidate.winning_leg != "CE":
                    continue
                elif spot_trend == "DOWN" and candidate.winning_leg != "PE":
                    continue
                elif spot_trend == "SIDEWAYS":
                    # If regime is directional but spot trend is sideways (e.g. regime transition), require no bias
                    pass

            survivors.append(candidate)

        return survivors
