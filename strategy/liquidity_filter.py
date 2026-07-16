import logging
from typing import List, Any
from data.market_cache import MarketCache, market_cache
from config.settings import TradingConfig
from core.execution_quality import leg_spread_is_within_emergency_limit

logger = logging.getLogger("AutoTrader")

class LiquidityFilter:
    """
    Filters contracts that cannot be executed safely before candidate generation.

    Live volume and OI are intentionally not hard blockers. They remain ranking
    signals because their scale varies by index, strike, expiry and time of day.
    """
    def __init__(self, cache: MarketCache | None = None) -> None:
        self.cache = cache or market_cache

    def filter_strikes(self, strikes: List[Any], option_type: str, config: TradingConfig) -> List[Any]:
        filtered = []
        is_backtest = config.execution_mode == "BACKTEST"
        chain = self.cache.get_option_chain()

        for strike in strikes:
            opt_data = chain.get(strike, {}).get(option_type)
            if not opt_data:
                continue

            volume = opt_data.get("volume", 0)
            
            # Backtest mode applies volume-only gate (no OI/spreads historically)
            if is_backtest:
                # In backtesting, if the volume on the current candle is >= 5, it is considered liquid
                if volume >= 5:
                    filtered.append(strike)
            else:
                # Before the regime is known, apply only quote integrity and the
                # widest emergency spread cap. The final validator applies the
                # stricter DIRECTIONAL or SIDEWAYS limit to the selected basket.
                if leg_spread_is_within_emergency_limit(
                    opt_data,
                    maximum_pct=config.sideways_max_spread_pct,
                ):
                    filtered.append(strike)

        return filtered
