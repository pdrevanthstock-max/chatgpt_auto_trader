"""
Simulated Fill
───────────────
For backtest mode: simulates order fills without real broker interaction.
v1: instant fill at close price (no slippage model).

Future enhancement: add configurable slippage (fixed-tick or percentage).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from loguru import logger

from core.models import Trade, EntrySignal
from core.enums import TradeDirection, ExitReason
from config.settings import TradingConfig
from strategy.position_sizer import PositionSizer


class SimulatedFill:
    """
    Creates Trade objects from entry signals using simulated fills.
    Both legs are bought simultaneously (2-contract basket).
    """

    @staticmethod
    def fill_entry(
        signal: EntrySignal,
        config: TradingConfig,
    ) -> Optional[Trade]:
        """
        Simulate filling a 2-contract basket entry.

        §4.5 confirmed: both CE and PE are actually bought.
        §4.6: quantity is identical on both legs.

        Returns a Trade object, or None if sizing fails.
        """
        # Calculate position size from capital
        quantity = PositionSizer.calculate_quantity(
            ce_price=signal.ce_price,
            pe_price=signal.pe_price,
            config=config,
        )

        if quantity <= 0:
            logger.warning(
                f"Cannot fill entry: insufficient capital for "
                f"CE={signal.ce_price}, PE={signal.pe_price}"
            )
            return None

        # Calculate capital allocated to this trade (for §5.1 stop)
        capital_allocated = PositionSizer.calculate_capital_per_trade(
            ce_price=signal.ce_price,
            pe_price=signal.pe_price,
            quantity=quantity,
            config=config,
        )

        trade = Trade(
            direction=signal.direction,
            entry_ce_price=signal.ce_price,
            entry_pe_price=signal.pe_price,
            quantity=quantity,
            lot_size=config.nifty_lot_size,
            entry_time=signal.timestamp,
            strike=signal.strike,
            capital_allocated=capital_allocated,
            current_ce_price=signal.ce_price,
            current_pe_price=signal.pe_price,
            peak_combined_pnl=0.0,
            trailing_stop_pnl=0.0,
        )

        logger.info(
            f"ENTRY FILLED: {signal.direction.value} | "
            f"CE=₹{signal.ce_price:.2f} PE=₹{signal.pe_price:.2f} | "
            f"Qty={quantity} lots | "
            f"Capital=₹{capital_allocated:.2f} | "
            f"Divergence={signal.divergence:.2f}%"
        )

        return trade

    @staticmethod
    def fill_exit(
        trade: Trade,
        ce_price: float,
        pe_price: float,
        exit_time: datetime,
        reason: ExitReason,
    ) -> Trade:
        """
        Simulate filling an exit on both legs.
        Updates the trade with exit prices and reason.
        """
        trade.exit_ce_price = ce_price
        trade.exit_pe_price = pe_price
        trade.exit_time = exit_time
        trade.exit_reason = reason

        pnl = trade.combined_pnl

        logger.info(
            f"EXIT FILLED: {reason.value} | "
            f"CE exit=₹{ce_price:.2f} PE exit=₹{pe_price:.2f} | "
            f"PnL=₹{pnl:.2f}"
        )

        return trade
