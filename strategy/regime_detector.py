import logging
from typing import List, Tuple
from core.enums import MarketRegime

logger = logging.getLogger("AutoTrader")

class RegimeDetector:
    """
    Classifies the current market regime as Directional or Sideways
    based on spot prices, VWAP, and ATR.
    """
    def detect_regime(
        self,
        spot_closes: List[float],
        spot_highs: List[float],
        spot_lows: List[float],
        vwap_values: List[float],
        atr_values: List[float],
        atm_strike: int
    ) -> Tuple[MarketRegime, str]:
        """
        Runs continuous regime classification.
        Returns: Tuple of (MarketRegime, spot_trend_string)
        where spot_trend_string is "UP", "DOWN", or "SIDEWAYS".
        """
        # We need at least 10 candles for lookback, and preferably 20 for ATR MA
        if len(spot_closes) < 10 or len(vwap_values) < 10 or len(atr_values) < 10 or atm_strike <= 0:
            return MarketRegime.SIDEWAYS, "SIDEWAYS"

        lookback = 10
        recent_closes = spot_closes[-lookback:]
        recent_highs = spot_highs[-lookback:]
        recent_lows = spot_lows[-lookback:]
        recent_vwap = vwap_values[-lookback:]

        # 1. Spot side of VWAP
        above_vwap_count = sum(1 for c, v in zip(recent_closes, recent_vwap) if c > v)
        consistently_above = above_vwap_count >= 8
        consistently_below = above_vwap_count <= 2

        # 2. Trend structure (higher highs/lows or lower highs/lows)
        # Compare current candle to a few candles ago to identify trend structure
        bullish_structure = (recent_highs[-1] > recent_highs[-5]) and (recent_lows[-1] > recent_lows[-5])
        bearish_structure = (recent_highs[-1] < recent_highs[-5]) and (recent_lows[-1] < recent_lows[-5])

        # 3. ATR trend (expanding or contracting)
        current_atr = atr_values[-1]
        atr_ma = sum(atr_values) / len(atr_values)  # Average of entire passed list (usually 10-20 length)
        atr_expanding = current_atr > atr_ma

        # 4. Tight range check (high - low < 0.3% of ATM strike over 10 candles)
        day_range = max(recent_highs) - min(recent_lows)
        tight_range = day_range < (0.003 * atm_strike)

        # Classification logic
        if consistently_above and bullish_structure and atr_expanding and not tight_range:
            return MarketRegime.DIRECTIONAL, "UP"
        elif consistently_below and bearish_structure and atr_expanding and not tight_range:
            return MarketRegime.DIRECTIONAL, "DOWN"
        else:
            return MarketRegime.SIDEWAYS, "SIDEWAYS"
