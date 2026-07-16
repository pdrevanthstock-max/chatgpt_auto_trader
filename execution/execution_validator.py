import logging
from datetime import datetime
from typing import Optional
from core.models import TradePlan, Trade
from config.settings import TradingConfig
from data.market_cache import MarketCache, market_cache
from core.execution_quality import combined_spread_limit, has_valid_book

logger = logging.getLogger("AutoTrader")

class ExecutionValidator:
    """
    Final pre-order gate. Approves or blocks order entry based on system constraints,
    circuit breakers, active positions, and live liquidity.
    """
    def __init__(self, cache: MarketCache | None = None) -> None:
        self.cache = cache or market_cache

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
        last_update, latency_ms = self.cache.get_health()
        if not last_update:
            return False, "MarketCache is empty or has not received updates."

        cache_age = (datetime.now() - last_update).total_seconds()
        if cache_age > config.health_check_cache_stale_sec:
            return False, f"MarketCache is stale: {cache_age:.1f}s age > limit {config.health_check_cache_stale_sec}s."

        if latency_ms > config.health_check_api_latency_ms:
            return False, f"API latency too high: {latency_ms}ms > limit {config.health_check_api_latency_ms}ms."

        # 4. Spread check (liquidity gate)
        chain = self.cache.get_option_chain()
        ce_data = chain.get(plan.scored_candidate.ce_strike, {}).get("CE")
        pe_data = chain.get(plan.scored_candidate.pe_strike, {}).get("PE")

        if not ce_data or not pe_data:
            return False, "Option contracts missing from MarketCache at validation time."

        now = datetime.now()
        for leg, quote in (("CE", ce_data), ("PE", pe_data)):
            quote_time = quote.get("timestamp")
            if not isinstance(quote_time, datetime):
                return False, f"{leg} selected contract has no valid quote timestamp."
            quote_age = (now - quote_time).total_seconds()
            if quote_age > config.health_check_cache_stale_sec:
                return False, (
                    f"{leg} selected contract is stale: {quote_age:.1f}s age > "
                    f"limit {config.health_check_cache_stale_sec}s."
                )

        spot, _ = self.cache.get_spot()
        if spot > 0.0:
            ce_is_otm = plan.scored_candidate.ce_strike > spot
            pe_is_otm = plan.scored_candidate.pe_strike < spot
            if ce_is_otm and pe_is_otm:
                return False, "Entry rejected: both OTM contracts expose the pair to dual premium decay."

        active_expiry = self.cache.get_active_expiry()
        if active_expiry is not None:
            days_to_expiry = (active_expiry - now.date()).days
            if days_to_expiry < 0:
                return False, "Entry rejected: selected option expiry has already passed."

        ce_bid = ce_data.get("bid", 0.0)
        ce_ask = ce_data.get("ask", 0.0)
        pe_bid = pe_data.get("bid", 0.0)
        pe_ask = pe_data.get("ask", 0.0)

        if not has_valid_book(ce_data) or not has_valid_book(pe_data):
            return False, "Missing, invalid, or inverted bid/ask quotes."

        if plan.quantity <= 0 or plan.lot_size <= 0:
            return False, "Entry quantity and lot size must both be positive."

        entry_outlay = (
            (ce_ask + pe_ask) * plan.quantity * plan.lot_size
        )
        available_capital = plan.risk_capital_at_entry or config.entry_equity(realized_pnl)
        deployable_capital = available_capital * config.max_capital_deployment_pct
        if entry_outlay > deployable_capital:
            return False, (
                f"Executable entry outlay ₹{entry_outlay:.2f} exceeds available "
                f"capital ₹{config.total_capital:.2f}."
            )

        ce_spread = ce_ask - ce_bid
        pe_spread = pe_ask - pe_bid
        combined_spread = ce_spread + pe_spread

        # Marketable directional entries use a strict spread. Sideways limit
        # entries may wait for price improvement but retain an emergency cap.
        combined_mid = ((ce_bid + ce_ask) / 2.0) + ((pe_bid + pe_ask) / 2.0)
        max_allowed_spread = combined_spread_limit(
            plan.regime,
            combined_mid=combined_mid,
            absolute_floor=config.health_check_spread_max,
            directional_pct=config.directional_max_spread_pct,
            sideways_pct=config.sideways_max_spread_pct,
        )

        if combined_spread > max_allowed_spread:
            return False, (
                f"{plan.regime.value} combined spread ₹{combined_spread:.2f} > "
                f"max allowed ₹{max_allowed_spread:.2f}."
            )

        return True, "Validation successful"
