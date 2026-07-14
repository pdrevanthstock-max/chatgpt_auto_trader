import logging
from datetime import datetime, time
from typing import Dict, Tuple, Optional, Any
from core.models import Trade, ScoredCandidate
from core.transaction_costs import calculate_option_round_trip_costs
from core.enums import MarketRegime, TradePhase
from config.settings import TradingConfig
from data.market_cache import market_cache

logger = logging.getLogger("AutoTrader")

class RotationEngine:
    """
    Evaluates whether the system should rotate from the current open trade
    to a higher-ranked candidate pair.
    """
    def __init__(self) -> None:
        # Cooldown track: { pair_label: expire_datetime }
        self._cooldowns: Dict[str, datetime] = {}

    def set_cooldown(self, ce_strike: Any, pe_strike: Any, current_time: datetime, config: TradingConfig) -> None:
        pair_label = f"{ce_strike}-{pe_strike}"
        self._cooldowns[pair_label] = current_time

    def is_in_cooldown(self, ce_strike: Any, pe_strike: Any, current_time: datetime, config: TradingConfig) -> bool:
        pair_label = f"{ce_strike}-{pe_strike}"
        expire_time = self._cooldowns.get(pair_label)
        if not expire_time:
            return False

        cooldown_sec = config.rotation_cooldown_candles * config.candle_interval_minutes * 60
        elapsed = (current_time - expire_time).total_seconds()
        if elapsed < cooldown_sec:
            return True
        return False

    def should_rotate(
        self,
        active_trade: Trade,
        top_candidate: ScoredCandidate,
        current_time: datetime,
        current_regime: MarketRegime,
        config: TradingConfig
    ) -> Tuple[bool, str]:
        """
        Runs the 5-condition check to decide if we rotate from active_trade to top_candidate.
        Returns: Tuple of (should_rotate_bool, reason_string)
        """
        if not top_candidate:
            return False, "No top candidate available"

        # Cooldown check
        if self.is_in_cooldown(top_candidate.ce_strike, top_candidate.pe_strike, current_time, config):
            return False, "Candidate in cooldown"

        # Phase 2 Exception check
        if active_trade.phase == TradePhase.PHASE_2_SINGLE_LEG:
            if current_regime == MarketRegime.DIRECTIONAL:
                return False, "Rotation paused during Directional Phase 2"

        # Condition 3: Banked minimum profit floor (~Rs 103)
        if active_trade.combined_pnl < config.rotation_min_profit_floor:
            return False, f"PnL ₹{active_trade.combined_pnl:.2f} is below min floor ₹{config.rotation_min_profit_floor:.2f}"

        # Condition 5: Time remains (at least 60 seconds before 15:20 IST)
        eod_hour, eod_min = map(int, config.scan_end.split(":"))
        eod_dt = datetime.combine(current_time.date(), time(eod_hour, eod_min))
        time_remaining_sec = (eod_dt - current_time).total_seconds()
        if time_remaining_sec < 60.0:
            return False, f"Insufficient time remaining before square-off ({time_remaining_sec:.1f}s)"

        # Calculate current trade's current score & divergence for comparison
        chain = market_cache.get_option_chain()
        ce_data = chain.get(active_trade.strike_ce, {}).get("CE")
        pe_data = chain.get(active_trade.strike_pe, {}).get("PE")

        if not ce_data or not pe_data:
            return False, "Active trade contracts missing from cache"

        # Compute velocities for active trade
        ce_open = ce_data.get("open", 0.0)
        ce_close = ce_data.get("last", ce_data.get("close", 0.0))
        pe_open = pe_data.get("open", 0.0)
        pe_close = pe_data.get("last", pe_data.get("close", 0.0))

        if ce_open <= 0 or pe_open <= 0:
            return False, "Invalid active trade option prices"

        active_ce_vel = ((ce_close - ce_open) / ce_open) * 100.0
        active_pe_vel = ((pe_close - pe_open) / pe_open) * 100.0
        active_div = abs(active_ce_vel - active_pe_vel)

        # Estimate current score of active trade
        active_combined_premium = ce_close + pe_close
        expected_combined_change_pct = (active_ce_vel * ce_close + active_pe_vel * pe_close) / active_combined_premium
        expected_pnl = (expected_combined_change_pct / 100.0) * active_combined_premium * config.nifty_lot_size
        estimated_costs = calculate_option_round_trip_costs(
            entry_ce_price=ce_close,
            entry_pe_price=pe_close,
            exit_ce_price=ce_close,
            exit_pe_price=pe_close,
            lots=1,
            lot_size=config.nifty_lot_size,
        ).total
        active_score = expected_pnl - estimated_costs - 10.0

        # Condition 1: Score hysteresis (new score > old score + 0.30)
        if top_candidate.projected_net_profit <= active_score + 0.30:
            return False, f"Candidate score {top_candidate.projected_net_profit:.2f} <= current score {active_score:.2f} + 0.30"

        # Condition 2: Faster velocity
        if top_candidate.divergence <= active_div:
            return False, f"Candidate divergence {top_candidate.divergence:.2f}% <= current divergence {active_div:.2f}%"

        reason = (
            f"Rotate to {top_candidate.ce_strike}CE-{top_candidate.pe_strike}PE. "
            f"Higher score ({top_candidate.projected_net_profit:.2f} vs {active_score:.2f}) "
            f"and faster velocity ({top_candidate.divergence:.2f}% vs {active_div:.2f}%)."
        )
        return True, reason
