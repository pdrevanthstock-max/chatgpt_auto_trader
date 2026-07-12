import logging
from datetime import datetime
from typing import Dict, Any, Tuple, Optional
from config.settings import TradingConfig
from data.market_cache import market_cache

# Optional psutil import
try:
    import psutil
except ImportError:
    psutil = None

logger = logging.getLogger("AutoTrader")

class HealthMonitor:
    """
    Continuously monitors system parameters (API latency, bid-ask spread, cache freshness, CPU, memory).
    Acts as a gating check before executing new positions.
    """
    def check_health(self, config: TradingConfig, pair_strikes: Optional[Tuple[int, int]] = None) -> Tuple[bool, str]:
        """
        Performs all health checks.
        Returns: Tuple of (is_healthy_bool, status_message)
        """
        # 1. System CPU and Memory check
        cpu_usage = 0.0
        memory_usage = 0.0
        if psutil:
            try:
                cpu_usage = psutil.cpu_percent(interval=None)
                memory_usage = psutil.virtual_memory().percent
            except Exception as e:
                logger.error(f"HealthMonitor: Failed to query system stats: {e}")
        else:
            # Fallbacks
            cpu_usage = 10.0
            memory_usage = 45.0

        if cpu_usage > 70.0:
            return False, f"CPU usage too high: {cpu_usage:.1f}% > 70%"

        if memory_usage > 95.0:
            return False, f"Memory usage too high: {memory_usage:.1f}% > 95%"

        # In BACKTEST mode, skip live latency/spread checks
        if config.execution_mode == "BACKTEST":
            return True, f"Healthy (Backtest mode bypass, CPU: {cpu_usage:.1f}%, Mem: {memory_usage:.1f}%)"

        # 2. MarketCache freshness check
        last_update, latency_ms = market_cache.get_health()
        if not last_update:
            return False, "MarketCache has not received any updates."

        cache_age = (datetime.now() - last_update).total_seconds()
        if cache_age > config.health_check_cache_stale_sec:
            return False, f"MarketCache is stale: {cache_age:.1f}s old > limit {config.health_check_cache_stale_sec}s."

        # 3. API Latency check
        if latency_ms > config.health_check_api_latency_ms:
            return False, f"Broker API latency too high: {latency_ms}ms > limit {config.health_check_api_latency_ms}ms."

        # 4. Bid-Ask Spread check (if checking a specific pair for entry validation)
        if pair_strikes:
            ce_strike, pe_strike = pair_strikes
            chain = market_cache.get_option_chain()
            ce_data = chain.get(ce_strike, {}).get("CE")
            pe_data = chain.get(pe_strike, {}).get("PE")

            if not ce_data or not pe_data:
                return False, "Option chain data missing for target strikes."

            ce_bid = ce_data.get("bid", 0.0)
            ce_ask = ce_data.get("ask", 0.0)
            pe_bid = pe_data.get("bid", 0.0)
            pe_ask = pe_data.get("ask", 0.0)

            if ce_bid <= 0 or ce_ask <= 0 or pe_bid <= 0 or pe_ask <= 0:
                return False, "Missing bid/ask quotes for target strikes."

            ce_spread = ce_ask - ce_bid
            pe_spread = pe_ask - pe_bid
            combined_spread = ce_spread + pe_spread

            combined_mid = ((ce_bid + ce_ask) / 2.0) + ((pe_bid + pe_ask) / 2.0)
            max_allowed_spread = max(config.health_check_spread_max, combined_mid * 0.02)

            if combined_spread > max_allowed_spread:
                return False, f"Combined spread ₹{combined_spread:.2f} > max allowed ₹{max_allowed_spread:.2f}."

        return True, f"System Healthy (CPU: {cpu_usage:.1f}%, Mem: {memory_usage:.1f}%, Latency: {latency_ms}ms)"
