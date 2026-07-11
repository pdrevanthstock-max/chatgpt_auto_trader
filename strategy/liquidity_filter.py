import logging
from typing import List, Any
from data.market_cache import market_cache
from config.settings import TradingConfig

logger = logging.getLogger("AutoTrader")

class LiquidityFilter:
    """
    Filters individual strikes for liquidity BEFORE candidate generation.
    Checks volume, OI, and bid-ask spreads.
    """
    def filter_strikes(self, strikes: List[Any], option_type: str, config: TradingConfig) -> List[Any]:
        filtered = []
        is_backtest = config.execution_mode == "BACKTEST"
        chain = market_cache.get_option_chain()

        for strike in strikes:
            opt_data = chain.get(strike, {}).get(option_type)
            if not opt_data:
                continue

            volume = opt_data.get("volume", 0)
            oi = opt_data.get("oi", 0)
            
            # Backtest mode applies volume-only gate (no OI/spreads historically)
            if is_backtest:
                # In backtesting, if the volume on the current candle is >= 5, it is considered liquid
                if volume >= 5:
                    filtered.append(strike)
            else:
                # Live / Paper mode check
                bid = opt_data.get("bid", 0.0)
                ask = opt_data.get("ask", 0.0)
                spread = ask - bid
                mid = (bid + ask) / 2.0
                
                # Minimum bid-ask spread <= Rs 0.50 or 2% of mid-price
                max_allowed_spread = max(0.50, mid * 0.02)
                
                if volume >= 100 and oi >= 1000 and spread <= max_allowed_spread:
                    filtered.append(strike)

        return filtered
