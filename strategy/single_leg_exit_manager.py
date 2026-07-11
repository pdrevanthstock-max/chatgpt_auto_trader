import logging
from typing import Optional
from core.models import Trade
from core.enums import ExitReason, TradePhase
from config.settings import TradingConfig

logger = logging.getLogger("AutoTrader")

class SingleLegExitManager:
    """
    Manages trailing exit for the single remaining winning option leg (Phase 2).
    Applies the 10% peak giveback rule scoped only to the winning leg's own PnL.
    """
    def check_single_leg_exit(
        self,
        trade: Trade,
        ce_price: float,
        pe_price: float,
        config: TradingConfig
    ) -> Optional[ExitReason]:
        if trade.phase != TradePhase.PHASE_2_SINGLE_LEG:
            return None

        # Update current prices
        trade.ce_current_price = ce_price
        trade.pe_current_price = pe_price

        # Calculate winning leg PnL
        # PnL = (current_price - entry_price) * qty * lot_size
        winning_current = ce_price if trade.winning_leg == "CE" else pe_price
        winning_entry = trade.entry_ce_price if trade.winning_leg == "CE" else trade.entry_pe_price
        
        winning_leg_pnl = (winning_current - winning_entry) * trade.quantity * trade.lot_size

        if winning_leg_pnl > 0.0:
            trade.peak_single_leg_pnl = max(trade.peak_single_leg_pnl, winning_leg_pnl)

        # 10% giveback trailing stop check
        if trade.peak_single_leg_pnl > 0.0:
            threshold = trade.peak_single_leg_pnl * (1.0 - config.giveback_pct)
            if winning_leg_pnl < threshold:
                logger.warning(
                    f"SingleLegExitManager (GIVEBACK): Winning leg PnL ₹{winning_leg_pnl:.2f} "
                    f"fell below 90% of peak ₹{trade.peak_single_leg_pnl:.2f} (threshold: ₹{threshold:.2f})."
                )
                return ExitReason.GIVEBACK

        return None
