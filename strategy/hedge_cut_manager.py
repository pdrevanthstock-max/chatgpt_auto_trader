import logging
from core.models import Trade
from core.enums import TradePhase
from config.settings import TradingConfig

logger = logging.getLogger("AutoTrader")

class HedgeCutManager:
    """
    Decides when to cut the losing leg in Directional mode.
    Triggers Phase 1 -> Phase 2 transition when combined profit crosses the dynamic threshold.
    """
    def should_hedge_cut(
        self,
        trade: Trade,
        ce_price: float,
        pe_price: float,
        config: TradingConfig
    ) -> bool:
        # Only relevant during Phase 1 of a trade
        if trade.phase != TradePhase.PHASE_1_BOTH_LEGS:
            return False

        # Update prices
        trade.ce_current_price = ce_price
        trade.pe_current_price = pe_price

        current_combined_pnl = trade.combined_pnl

        # Calculate winning leg current value
        # Bullish (LONG_CE) -> CE is winning leg. Bearish (LONG_PE) -> PE is winning leg.
        winning_price = ce_price if trade.winning_leg == "CE" else pe_price
        winning_leg_value = winning_price * trade.quantity * trade.lot_size

        # Determine threshold
        if winning_leg_value < config.hedge_cut_value_breakpoint:
            threshold = config.hedge_cut_threshold_flat
        else:
            threshold = config.hedge_cut_threshold_pct * winning_leg_value

        # Check trigger condition
        if current_combined_pnl >= threshold:
            logger.info(
                f"HedgeCutManager: Combined profit ₹{current_combined_pnl:.2f} crossed threshold "
                f"₹{threshold:.2f} (Winning leg value: ₹{winning_leg_value:.2f}). Triggering HEDGE_CUT."
            )
            return True

        return False
