import pytest
from datetime import datetime
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
