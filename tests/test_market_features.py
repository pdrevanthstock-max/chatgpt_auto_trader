from datetime import datetime, timedelta

from core.models import Candle
from strategy.market_features import MarketFeatureCalculator


def test_real_ohlc_vwap_and_atr_features_are_derived_from_completed_candles():
    start = datetime(2026, 7, 15, 10, 0)
    candles = [
        Candle(start, 100, 105, 99, 104, volume=10, vwap=103.0),
        Candle(start + timedelta(minutes=1), 104, 108, 102, 107, volume=30, vwap=106.0),
    ]

    result = MarketFeatureCalculator.calculate(candles)

    assert result.closes == (104.0, 107.0)
    assert result.highs == (105.0, 108.0)
    assert result.lows == (99.0, 102.0)
    assert result.vwap_values == (103.0, 106.0)
    assert result.atr_values == (6.0, 6.0)
