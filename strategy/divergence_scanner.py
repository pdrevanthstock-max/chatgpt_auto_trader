import logging
from typing import List, Tuple, Any
from data.market_cache import market_cache
from core.models import CandidatePair
from data.candle_store import CompletedCandleStore, completed_candles, option_candle_key

logger = logging.getLogger("AutoTrader")

class DivergenceScanner:
    """
    Computes per-candle percentage velocity for both legs of each candidate pair.
    """
    def __init__(
        self,
        candle_store: CompletedCandleStore | None = None,
        *,
        index_symbol: str = "NIFTY",
        require_completed: bool = False,
    ) -> None:
        self.candle_store = candle_store or completed_candles
        self.index_symbol = index_symbol
        self.require_completed = require_completed

    def scan_candidates(self, candidates: List[Tuple[Any, Any]]) -> List[CandidatePair]:
        chain = market_cache.get_option_chain()
        pairs = []

        for ce_strike, pe_strike in candidates:
            ce_data = chain.get(ce_strike, {}).get("CE")
            pe_data = chain.get(pe_strike, {}).get("PE")

            if self.require_completed:
                ce_pair = self.candle_store.latest_pair(
                    option_candle_key(self.index_symbol, ce_strike, "CE")
                )
                pe_pair = self.candle_store.latest_pair(
                    option_candle_key(self.index_symbol, pe_strike, "PE")
                )
                if ce_pair is None or pe_pair is None:
                    continue
                if ce_pair[1].timestamp != pe_pair[1].timestamp:
                    continue
                ce_open, ce_close = ce_pair[0].close, ce_pair[1].close
                pe_open, pe_close = pe_pair[0].close, pe_pair[1].close
            else:
                if not ce_data or not pe_data:
                    continue
                ce_open = ce_data.get("open", 0.0)
                ce_close = ce_data.get("last", ce_data.get("close", 0.0))
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
