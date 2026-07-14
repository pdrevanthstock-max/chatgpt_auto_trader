import threading
import logging
import math
from datetime import datetime
from numbers import Real
from typing import Dict, Any, Optional

logger = logging.getLogger("AutoTrader")

class MarketCache:
    """
    In-memory thread-safe cache of live market data.
    Single source of truth for all strategy and ranking modules.
    """
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._spot_price: float = 0.0
        self._spot_timestamp: Optional[datetime] = None
        
        self._atm_strike: int = 0
        
        # option_chain: { strike: { "CE": {bid, ask, last, volume, oi, timestamp}, "PE": {...} } }
        self._option_chain: Dict[int, Dict[str, Dict[str, Any]]] = {}
        
        # greeks: { strike: { "CE": {delta, gamma, vega, theta}, "PE": {...} } }
        self._greeks: Dict[int, Dict[str, Dict[str, float]]] = {}
        
        # security IDs mapping: { (strike, option_type): security_id }
        self._security_ids: Dict[tuple[int, str], int] = {}
        
        # iv info
        self._atm_iv: float = 0.15
        self._iv_percentile: float = 50.0  # 0 to 100
        
        # vwap
        self._vwap: float = 0.0
        self._vwap_timestamp: Optional[datetime] = None
        
        # health indicators
        self._last_update: Optional[datetime] = None
        self._api_latency_ms: int = 0

    def update_spot(self, price: float, ts: datetime) -> None:
        with self._lock:
            self._spot_price = price
            self._spot_timestamp = ts
            # Derive ATM (nearest 50 points)
            self._atm_strike = int(round(price / 50.0) * 50)
            self._last_update = datetime.now()

    def get_spot(self) -> tuple[float, Optional[datetime]]:
        with self._lock:
            return self._spot_price, self._spot_timestamp

    def get_atm_strike(self) -> int:
        with self._lock:
            return self._atm_strike

    def update_option(self, strike: int, option_type: str, data: Dict[str, Any]) -> None:
        quote = data.copy()
        if "last" not in quote:
            raise ValueError(
                f"Invalid option quote for {strike} {option_type}: "
                "last price is required."
            )

        price_fields = ("bid", "ask", "last", "open", "high", "low", "close")
        for field in price_fields:
            if field not in quote:
                continue
            value = quote[field]
            if (
                isinstance(value, bool)
                or not isinstance(value, Real)
                or not math.isfinite(float(value))
                or value <= 0.0
            ):
                raise ValueError(
                    f"Invalid option quote for {strike} {option_type}: "
                    f"{field} must be a finite positive number, got {value!r}."
                )

        if "bid" in quote and "ask" in quote and quote["ask"] < quote["bid"]:
            raise ValueError(
                f"Invalid option quote for {strike} {option_type}: "
                f"ask {quote['ask']!r} is below bid {quote['bid']!r}."
            )

        with self._lock:
            if strike not in self._option_chain:
                self._option_chain[strike] = {}
            
            # Ensure "open" is initialized to prevent calculation failures in velocity/divergence
            existing = self._option_chain[strike].get(option_type)
            if existing and existing.get("open", 0.0) > 0.0:
                quote["open"] = existing["open"]
            elif "open" not in quote:
                quote["open"] = quote.get("last", 0.0)

            self._option_chain[strike][option_type] = quote
            self._last_update = datetime.now()

    def get_option(self, strike: int, option_type: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._option_chain.get(strike, {}).get(option_type)

    def get_option_chain(self) -> Dict[int, Dict[str, Dict[str, Any]]]:
        with self._lock:
            # Return copy to prevent external modification
            return {k: {ik: iv.copy() for ik, iv in v.items()} for k, v in self._option_chain.items()}

    def update_greeks(self, strike: int, option_type: str, delta: float, gamma: float, vega: float, theta: float) -> None:
        with self._lock:
            if strike not in self._greeks:
                self._greeks[strike] = {}
            self._greeks[strike][option_type] = {
                "delta": delta,
                "gamma": gamma,
                "vega": vega,
                "theta": theta
            }

    def get_greeks(self, strike: int, option_type: str) -> Optional[Dict[str, float]]:
        with self._lock:
            return self._greeks.get(strike, {}).get(option_type)

    def update_iv(self, atm_iv: float, percentile: float) -> None:
        with self._lock:
            self._atm_iv = atm_iv
            self._iv_percentile = percentile
            self._last_update = datetime.now()

    def get_iv(self) -> tuple[float, float]:
        with self._lock:
            return self._atm_iv, self._iv_percentile

    def update_vwap(self, vwap: float, ts: datetime) -> None:
        with self._lock:
            self._vwap = vwap
            self._vwap_timestamp = ts
            self._last_update = datetime.now()

    def get_vwap(self) -> tuple[float, Optional[datetime]]:
        with self._lock:
            return self._vwap, self._vwap_timestamp

    def update_health(self, latency_ms: int) -> None:
        with self._lock:
            self._api_latency_ms = latency_ms

    def get_health(self) -> tuple[Optional[datetime], int]:
        with self._lock:
            return self._last_update, self._api_latency_ms

    def set_security_id(self, strike: int, option_type: str, security_id: int) -> None:
        with self._lock:
            self._security_ids[(strike, option_type)] = security_id

    def get_security_id(self, strike: int, option_type: str) -> Optional[int]:
        with self._lock:
            return self._security_ids.get((strike, option_type))

    def clear(self) -> None:
        with self._lock:
            self._option_chain.clear()
            self._greeks.clear()
            self._security_ids.clear()
            self._spot_price = 0.0
            self._spot_timestamp = None
            self._atm_strike = 0
            self._vwap = 0.0
            self._vwap_timestamp = None
            self._last_update = None
            self._api_latency_ms = 0

# Singleton global instance
market_cache = MarketCache()
