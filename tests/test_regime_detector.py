import pytest
from core.enums import MarketRegime
from strategy.regime_detector import RegimeDetector

def test_regime_detector_sideways_default():
    detector = RegimeDetector()
    
    # Empty lookback -> SIDEWAYS
    regime, trend = detector.detect_regime([], [], [], [], [], 24300)
    assert regime == MarketRegime.SIDEWAYS
    assert trend == "SIDEWAYS"

def test_regime_detector_directional_bullish():
    detector = RegimeDetector()
    
    # 10 candles lookback
    spot_closes = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0]
    spot_highs = [100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5, 107.5, 108.5, 109.5]
    spot_lows = [99.5, 100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5, 107.5, 108.5]
    vwap_values = [98.0] * 10  # Closes consistently above VWAP
    atr_values = [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 2.0]  # ATR expanding
    
    # Use atm_strike = 1000 so that range 10.0 >= 0.003 * 1000 (3.0) -> not tight range
    regime, trend = detector.detect_regime(
        spot_closes=spot_closes,
        spot_highs=spot_highs,
        spot_lows=spot_lows,
        vwap_values=vwap_values,
        atr_values=atr_values,
        atm_strike=1000
    )
    
    assert regime == MarketRegime.DIRECTIONAL
    assert trend == "UP"
