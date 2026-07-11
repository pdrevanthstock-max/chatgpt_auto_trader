import logging
from typing import List, Tuple, Any
from data.market_cache import market_cache
from core.models import CandidatePair

logger = logging.getLogger("AutoTrader")

class DivergenceScanner:
    """
    Computes per-candle percentage velocity for both legs of each candidate pair.
    """
    def scan_candidates(self, candidates: List[Tuple[Any, Any]]) -> List[CandidatePair]:
        chain = market_cache.get_option_chain()
        pairs = []

        for ce_strike, pe_strike in candidates:
            ce_data = chain.get(ce_strike, {}).get("CE")
            pe_data = chain.get(pe_strike, {}).get("PE")

            if not ce_data or not pe_data:
                continue

            ce_open = ce_data.get("open", 0.0)
            ce_close = ce_data.get("last", ce_data.get("close", 0.0))  # use last/close

            pe_open = pe_data.get("open", 0.0)
            pe_close = pe_data.get("last", pe_data.get("close", 0.0))

            # Protect against division by zero
            if ce_open <= 0.0 or pe_open <= 0.0:
                continue

            ce_velocity = ((ce_close - ce_open) / ce_open) * 100.0
            pe_velocity = ((pe_close - pe_open) / pe_open) * 100.0
            divergence = abs(ce_velocity - pe_velocity)
            
            winning_leg = "CE" if ce_velocity >= pe_velocity else "PE"

            pairs.append(CandidatePair(
                ce_strike=ce_strike,
                pe_strike=pe_strike,
                ce_velocity=round(ce_velocity, 4),
                pe_velocity=round(pe_velocity, 4),
                divergence=round(divergence, 4),
                winning_leg=winning_leg
            ))

        return pairs
