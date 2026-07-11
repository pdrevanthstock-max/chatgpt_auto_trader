import logging
from typing import List, Tuple, Any
from data.market_cache import market_cache

logger = logging.getLogger("AutoTrader")

class PairCandidateGenerator:
    """
    Builds the Cartesian product of all available CE and PE strikes.
    Works for both numeric strikes (live/paper) and relative strike labels (backtesting).
    """
    def generate_candidates(self) -> List[Tuple[Any, Any]]:
        chain = market_cache.get_option_chain()
        if not chain:
            return []

        # Extract strikes that have CE and PE loaded
        ce_strikes = [strike for strike, data in chain.items() if "CE" in data and data["CE"] is not None]
        pe_strikes = [strike for strike, data in chain.items() if "PE" in data and data["PE"] is not None]

        candidates = []
        for ce in ce_strikes:
            for pe in pe_strikes:
                candidates.append((ce, pe))

        return candidates
