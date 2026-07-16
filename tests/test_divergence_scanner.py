import pytest
from datetime import datetime, timedelta
from data.candle_store import CompletedCandleStore
from data.market_cache import market_cache
from strategy.divergence_scanner import DivergenceScanner

def test_divergence_scanner_velocity_calc():
    market_cache.clear()
    
    # Setup mock options in cache
    # Strike 24300 CE: open 100.0, close/last 105.0 -> +5% velocity
    market_cache.update_option(24300, "CE", {
        "open": 100.0, "last": 105.0, "volume": 100, "oi": 1000
    })
    # Strike 24400 PE: open 200.0, close/last 190.0 -> -5% velocity
    market_cache.update_option(24400, "PE", {
        "open": 200.0, "last": 190.0, "volume": 100, "oi": 1000
    })
    
    scanner = DivergenceScanner()
    candidates = [(24300, 24400)]
    pairs = scanner.scan_candidates(candidates)
    
    assert len(pairs) == 1
    pair = pairs[0]
    assert pair.ce_velocity == 5.0
    assert pair.pe_velocity == -5.0
    assert pair.divergence == 10.0
    assert pair.winning_leg == "CE"


def test_strict_live_scanner_uses_latest_completed_candle_open_to_close_velocity():
    store = CompletedCandleStore()
    start = datetime(2026, 7, 15, 10, 0, 5)
    for key, previous_close, latest_open, latest_close in [
        ("NIFTY:24200:CE", 90.0, 100.0, 110.0),
        ("NIFTY:24200:PE", 95.0, 100.0, 105.0),
    ]:
        store.add_tick(key, start, previous_close)
        store.add_tick(key, start + timedelta(minutes=1), latest_open)
        store.add_tick(key, start + timedelta(minutes=1, seconds=30), latest_close)
        store.add_tick(key, start + timedelta(minutes=2), latest_close)

    result = DivergenceScanner(
        candle_store=store, require_completed=True
    ).scan_candidates([(24200, 24200)])

    assert result[0].ce_velocity == 10.0
    assert result[0].pe_velocity == 5.0
    assert result[0].divergence == 5.0
