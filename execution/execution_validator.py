import logging
from datetime import datetime
from typing import Optional
from core.models import TradePlan, Trade
from config.settings import TradingConfig
from data.market_cache import market_cache

logger = logging.getLogger("AutoTrader")

class ExecutionValidator:
    """
    Final pre-order gate. Approves or blocks order entry based on system constraints,
    circuit breakers, active positions, and live liquidity.
    """
    def validate_entry(
        self,
        plan: TradePlan,
        realized_pnl: float,
        active_trade: Optional[Trade],
        config: TradingConfig
    ) -> tuple[bool, str]:
        # 1. Daily loss cap already breached
        daily_limit = -abs(config.daily_loss_limit)
        if config.execution_mode != "PAPER" and realized_pnl <= daily_limit:
            return False, f"Daily circuit breaker breached: realized PnL ₹{realized_pnl:.2f} <= ₹{daily_limit:.2f}"

        # 2. Position guard check (no double entries)
        if active_trade is not None and active_trade.is_open:
            return False, f"Trade {active_trade.id} is already active. Overlapping entry blocked."

        # In BACKTEST mode, bypass the live market spread, latency, and cache staleness checks
        if config.execution_mode == "BACKTEST":
            return True, "Validation successful (Backtest mode bypass)"

        # 3. Cache freshness & Broker connectivity
        last_update, latency_ms = market_cache.get_health()
        if not last_update:
            return False, "MarketCache is empty or has not received updates."

        cache_age = (datetime.now() - last_update).total_seconds()
        if cache_age > config.health_check_cache_stale_sec:
            return False, f"MarketCache is stale: {cache_age:.1f}s age > limit {config.health_check_cache_stale_sec}s."

        if latency_ms > config.health_check_api_latency_ms:
            return False, f"API latency too high: {latency_ms}ms > limit {config.health_check_api_latency_ms}ms."

        # 4. Spread check (liquidity gate)
        chain = market_cache.get_option_chain()
        ce_data = chain.get(plan.scored_candidate.ce_strike, {}).get("CE")
        pe_data = chain.get(plan.scored_candidate.pe_strike, {}).get("PE")

        if not ce_data or not pe_data:
            return False, "Option contracts missing from MarketCache at validation time."

        ce_bid = ce_data.get("bid", 0.0)
        ce_ask = ce_data.get("ask", 0.0)
        pe_bid = pe_data.get("bid", 0.0)
        pe_ask = pe_data.get("ask", 0.0)

        if ce_bid <= 0.0 or ce_ask <= 0.0 or pe_bid <= 0.0 or pe_ask <= 0.0:
            return False, "Missing bid/ask quotes for spread check."

        if plan.quantity <= 0 or plan.lot_size <= 0:
            return False, "Entry quantity and lot size must both be positive."

        entry_outlay = (
            (ce_ask + pe_ask) * plan.quantity * plan.lot_size
        )
        if entry_outlay > config.total_capital:
            return False, (
                f"Executable entry outlay ₹{entry_outlay:.2f} exceeds available "
                f"capital ₹{config.total_capital:.2f}."
            )

        ce_spread = ce_ask - ce_bid
        pe_spread = pe_ask - pe_bid
        combined_spread = ce_spread + pe_spread

        # Combined spread < Rs 1.50 or 2% of combined mid price
        combined_mid = ((ce_bid + ce_ask) / 2.0) + ((pe_bid + pe_ask) / 2.0)
        max_allowed_spread = max(config.health_check_spread_max, combined_mid * 0.02)

        if combined_spread > max_allowed_spread:
            return False, f"Combined spread ₹{combined_spread:.2f} > max allowed ₹{max_allowed_spread:.2f}."

        return True, "Validation successful"
