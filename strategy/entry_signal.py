import logging
from typing import List
from core.models import CandidatePair
from core.enums import MarketRegime
from config.settings import TradingConfig

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
    ) -> List[CandidatePair]:
        survivors = []
        min_band = config.divergence_band_min
        max_band = (
            config.directional_divergence_band_max
            if regime == MarketRegime.DIRECTIONAL
            else config.divergence_band_max
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
