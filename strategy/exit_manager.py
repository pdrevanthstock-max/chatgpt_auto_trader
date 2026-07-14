import logging
from typing import Optional
from core.models import Trade
from core.transaction_costs import calculate_option_round_trip_costs
from core.enums import ExitReason, MarketRegime, TradePhase
from config.settings import TradingConfig

logger = logging.getLogger("AutoTrader")

class ExitManager:
    """
    Manages exits for combined positions (Phase 1 — both legs open).
    Tracks peak profit and checks for 10% giveback and dynamic IV-scaled profit targets.
    """
    def check_exits(
        self,
        trade: Trade,
        ce_price: float,
        pe_price: float,
        iv_percentile: float,
        is_preclose: bool,
        config: TradingConfig
    ) -> Optional[ExitReason]:
        if trade.phase != TradePhase.PHASE_1_BOTH_LEGS:
            return None

        # Update prices
        trade.ce_current_price = ce_price
        trade.pe_current_price = pe_price

        current_pnl = trade.combined_pnl
        
        # Track peak profit (only track if PnL is positive to avoid immediate triggering)
        if current_pnl > 0.0:
            trade.peak_combined_pnl = max(trade.peak_combined_pnl, current_pnl)

        # 1. 10% Peak-Profit Giveback Rule
        # Fired in all regimes during Phase 1
        if trade.peak_combined_pnl > 0.0:
            # If current PnL drops below 90% of the peak profit
            giveback_threshold = trade.peak_combined_pnl * (1.0 - config.giveback_pct)
            if current_pnl < giveback_threshold:
                logger.warning(
                    f"ExitManager (GIVEBACK): Current combined PnL ₹{current_pnl:.2f} "
                    f"fell below 90% of peak ₹{trade.peak_combined_pnl:.2f} (threshold: ₹{giveback_threshold:.2f})."
                )
                return ExitReason.GIVEBACK

        # 2. Dynamic Profit Target Rule (Sideways regime only)
        # In sideways mode, we check for a dynamic target hit
        if trade.regime_at_entry == MarketRegime.SIDEWAYS:
            # Calculate scaling factor based on IV percentile
            if iv_percentile < config.iv_percentile_low:
                scaling_factor = 0.04
            elif iv_percentile > config.iv_percentile_high:
                scaling_factor = 0.06
            else:
                scaling_factor = 0.05

            combined_entry_premium = (trade.entry_ce_price + trade.entry_pe_price) * trade.quantity * trade.lot_size
            estimated_costs = calculate_option_round_trip_costs(
                entry_ce_price=trade.entry_ce_price,
                entry_pe_price=trade.entry_pe_price,
                exit_ce_price=trade.entry_ce_price,
                exit_pe_price=trade.entry_pe_price,
                lots=trade.quantity,
                lot_size=trade.lot_size,
            ).total
            profit_target = estimated_costs + (combined_entry_premium * scaling_factor) + 8.0

            # Scale up during preclose window (15:00 - 15:20) by 1.5x
            if is_preclose:
                profit_target *= 1.5

            if current_pnl >= profit_target:
                logger.info(
                    f"ExitManager (TARGET_HIT): Combined PnL ₹{current_pnl:.2f} reached "
                    f"dynamic target of ₹{profit_target:.2f}."
                )
                trade.target_pnl = profit_target
                return ExitReason.TARGET_HIT

        return None
