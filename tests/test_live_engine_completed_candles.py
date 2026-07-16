from pathlib import Path

from config.settings import TradingConfig


def test_live_engine_requires_completed_candles_and_real_regime_features():
    source = Path("ui/app.py").read_text(encoding="utf-8")
    runtime = Path("application/multi_index_runtime.py").read_text(encoding="utf-8")
    scanner = Path("application/index_scanner.py").read_text(encoding="utf-8")

    assert "MultiIndexRuntime" in source
    assert "MarketFeatureCalculator.calculate" in runtime
    assert "spot_candle_key(normalized)" in runtime
    assert "require_completed=require_completed" in scanner
    assert "self.atr_values.append(2.0)" not in source
    assert "self.vwap_values.append(spot_price)" not in source


def test_entry_scan_is_configured_for_60_seconds():
    source = Path("ui/app.py").read_text(encoding="utf-8")
    config = Path("config.json").read_text(encoding="utf-8")

    assert "self.multi_index_runtime.scan" in source
    assert '"scan_interval_seconds": 60' in config
    assert TradingConfig().scan_interval_seconds == 60
