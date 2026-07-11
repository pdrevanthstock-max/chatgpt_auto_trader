import logging
import threading
import time
from datetime import datetime
from data.market_cache import market_cache

logger = logging.getLogger("AutoTrader")

class LiveFeed:
    """
    Structural stub for Dhan Live WebSocket Feed.
    Updates market_cache in real-time.
    Currently mocked for safety/testing as per design decisions.
    """
    def __init__(self) -> None:
        self._running = False
        self._thread = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("Live WebSocket Feed connection established (MOCKED)")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        logger.info("Live WebSocket Feed connection stopped")

    def _run(self) -> None:
        # Mock ticks to populate cache if in PAPER/LIVE mode
        spot = 24300.0
        while self._running:
            try:
                # Simulate small spot movements
                import random
                spot += random.uniform(-2, 2)
                now = datetime.now()
                market_cache.update_spot(spot, now)
                
                # Derive ATM
                atm = market_cache.get_atm_strike()
                
                # Populate mock options around ATM
                for strike in range(atm - 250, atm + 300, 50):
                    ce_mid = max(5.0, 150.0 - (strike - spot) * 0.5)
                    pe_mid = max(5.0, 150.0 + (strike - spot) * 0.5)
                    
                    market_cache.update_option(strike, "CE", {
                        "bid": round(ce_mid - 0.25, 2),
                        "ask": round(ce_mid + 0.25, 2),
                        "last": round(ce_mid, 2),
                        "volume": 500,
                        "oi": 2000,
                        "timestamp": now
                    })
                    market_cache.update_option(strike, "PE", {
                        "bid": round(pe_mid - 0.25, 2),
                        "ask": round(pe_mid + 0.25, 2),
                        "last": round(pe_mid, 2),
                        "volume": 600,
                        "oi": 3000,
                        "timestamp": now
                    })
                
                # Update health monitor metrics
                market_cache.update_health(latency_ms=10)
                
                time.sleep(1)
            except Exception as e:
                logger.error(f"Error in LiveFeed mock loop: {e}")
                time.sleep(5)
