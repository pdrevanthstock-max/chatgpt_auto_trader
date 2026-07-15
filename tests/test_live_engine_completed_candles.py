from pathlib import Path

from config.settings import TradingConfig


def test_live_engine_requires_completed_candles_and_real_regime_features():
    source = Path("ui/app.py").read_text(encoding="utf-8")

    assert "DivergenceScanner(require_completed=True)" in source
    assert "MarketFeatureCalculator.calculate" in source
    assert 'completed_candles.latest(spot_candle_key("NIFTY")' in source
    assert "self.atr_values.append(2.0)" not in source
    assert "self.vwap_values.append(spot_price)" not in source


def test_entry_scan_is_once_per_completed_candle_and_configured_for_60_seconds():
    source = Path("ui/app.py").read_text(encoding="utf-8")
    config = Path("config.json").read_text(encoding="utf-8")

    assert "_last_entry_candle_at" in source
    assert "latest_spot_candle.timestamp == self._last_entry_candle_at" in source
    assert '"scan_interval_seconds": 60' in config
    assert TradingConfig().scan_interval_seconds == 60
