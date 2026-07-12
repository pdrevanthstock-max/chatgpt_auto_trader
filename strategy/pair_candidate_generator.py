import logging
from typing import List, Tuple, Any
from data.market_cache import market_cache
from config.settings import TradingConfig

logger = logging.getLogger("AutoTrader")

class PairCandidateGenerator:
    """
    Builds the Cartesian product of available CE and PE strikes within the scan range.
    Works for both numeric strikes (live/paper) and relative strike labels (backtesting).
    """
    def generate_candidates(self) -> List[Tuple[Any, Any]]:
        chain = market_cache.get_option_chain()
        if not chain:
            return []

        config = TradingConfig.load()
        scan_range = config.pair_scan_range
        atm_strike = market_cache.get_atm_strike()

        # Sort numeric strikes to compute step size dynamically if needed
        numeric_strikes = sorted([s for s in chain.keys() if isinstance(s, (int, float))])
        if len(numeric_strikes) >= 2:
            step = numeric_strikes[1] - numeric_strikes[0]
            if step <= 0:
                step = 50.0
        else:
            step = 50.0

        def is_within_range(strike: Any) -> bool:
            if isinstance(strike, str):
                if strike == "ATM":
                    return True
                if strike.startswith("ITM") or strike.startswith("OTM"):
                    try:
                        offset = int(strike[3:])
                        return offset <= scan_range
                    except ValueError:
                        return False
                return False
            elif isinstance(strike, (int, float)) and isinstance(atm_strike, (int, float)):
                return abs(strike - atm_strike) <= (scan_range * step) + 0.1
            return True

        # Extract strikes that are within range and have CE and PE loaded
        ce_strikes = [
            strike for strike, data in chain.items()
            if "CE" in data and data["CE"] is not None and is_within_range(strike)
        ]
        pe_strikes = [
            strike for strike, data in chain.items()
            if "PE" in data and data["PE"] is not None and is_within_range(strike)
        ]

        candidates = []
        for ce in ce_strikes:
            for pe in pe_strikes:
                candidates.append((ce, pe))

        return candidates
