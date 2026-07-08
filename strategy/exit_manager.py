"""
Exit Manager
──────────────
Handles ALL exit logic for Directional mode.

Two INDEPENDENT exit triggers (§5 — must stay separated in code):
  1. Per-trade stop: 2% of capital allocated to that trade (§5.1)
  2. Trailing stop: 85% lock-in of peak combined PnL (user feedback)

Plus:
  3. EOD flatten: Force-close at 15:00 IST (§3, Option A confirmed)

Daily circuit breaker (§5.2) is handled separately in daily_circuit_breaker.py.
"""

from __future__ import annotations

from typing import Optional
from datetime import time as dtime

from loguru import logger

from core.models import Trade
from core.enums import ExitReason, TradeDirection
from config.settings import TradingConfig


class ExitManager:
    """
    Checks exit conditions on an open trade.
    Each check is independent — a trade can be exited by any trigger.
    """

    @staticmethod
    def check_per_trade_stop(
        trade: Trade,
        config: TradingConfig,
    ) -> Optional[ExitReason]:
        """
        §5.1: Exit if unrealized loss exceeds 2% of the capital
        allocated to THIS trade.

        Note: "capital allocated to that one contract" = trade.capital_allocated.
        The 2% is of that allocation, not of total capital.
        
        Combined PnL is used because both legs are actually bought (§4.5 confirmed).
        """
        combined_pnl = trade.combined_pnl
        loss_limit = trade.capital_allocated * config.per_trade_stop_pct

        if combined_pnl < 0 and abs(combined_pnl) >= loss_limit:
            logger.warning(
                f"PER-TRADE STOP: Combined PnL ₹{combined_pnl:.2f} "
                f"exceeds 2% limit of ₹{loss_limit:.2f}"
            )
            return ExitReason.PER_TRADE_STOP

        return None

    @staticmethod
    def update_trailing_stop(
        trade: Trade,
        config: TradingConfig,
    ) -> Trade:
        """
        §2.1 + User feedback: Trailing stop with 85% lock-in.

        User example: "if we get profits 100rs it should put stop loss at 85"
        → lock_factor = 0.85, so trailing_stop = peak_pnl × 0.85

        Logic:
          1. Track peak combined PnL
          2. trailing_stop_pnl = peak × lock_factor
          3. Trailing stop only moves UP, never down
          4. When combined PnL drops below trailing_stop_pnl → EXIT

        User: "the trailing stop loss should always need to be updated
               automatically based on the market"
        → This runs on EVERY scan cycle while position is open.
        """
        combined_pnl = trade.combined_pnl

        # Update peak if new high
        if combined_pnl > trade.peak_combined_pnl:
            trade.peak_combined_pnl = combined_pnl

            # Update trailing stop level
            new_trailing = combined_pnl * config.trail_lock_factor
            if new_trailing > trade.trailing_stop_pnl:
                trade.trailing_stop_pnl = new_trailing
                logger.debug(
                    f"Trailing stop updated: peak=₹{combined_pnl:.2f}, "
                    f"stop=₹{new_trailing:.2f}"
                )

        return trade

    @staticmethod
    def check_trailing_stop(
        trade: Trade,
        config: TradingConfig,
    ) -> Optional[ExitReason]:
        """
        Check if trailing stop has been hit.

        Only triggers if:
          1. There has been some profit (peak > 0)
          2. Current PnL has fallen below the trailing stop level

        User feedback: "if there is movement the market instead going upside
        if goes downside it can book profits... once we enter into market and
        it started going sideways it can book the profits"
        """
        # No trailing stop if we've never been in profit
        if trade.peak_combined_pnl <= 0:
            return None

        # No trailing stop level set yet
        if trade.trailing_stop_pnl <= 0:
            return None

        combined_pnl = trade.combined_pnl

        # Trailing stop hit: PnL dropped below locked level
        if combined_pnl <= trade.trailing_stop_pnl:
            logger.warning(
                f"TRAILING STOP: PnL ₹{combined_pnl:.2f} fell below "
                f"trailing stop ₹{trade.trailing_stop_pnl:.2f} "
                f"(peak was ₹{trade.peak_combined_pnl:.2f})"
            )
            return ExitReason.TRAILING_STOP

        return None

    @staticmethod
    def check_eod_flatten(
        current_time: dtime,
        config: TradingConfig,
    ) -> Optional[ExitReason]:
        """
        §3 (Option A confirmed): Force-flatten at 15:00 IST.
        No overnight carry for options (theta decay risk).
        """
        end_hour, end_minute = map(int, config.scan_end.split(":"))
        end_time = dtime(end_hour, end_minute)

        if current_time >= end_time:
            logger.info("EOD FLATTEN: Market close reached, forcing exit")
            return ExitReason.EOD_FLATTEN

        return None

    @classmethod
    def check_all_exits(
        cls,
        trade: Trade,
        current_time: dtime,
        config: TradingConfig,
    ) -> Optional[ExitReason]:
        """
        Run all exit checks in priority order.
        Returns the first triggered ExitReason, or None.

        Priority:
          1. EOD flatten (time-based, non-negotiable)
          2. Per-trade stop (capital protection)
          3. Trailing stop (profit protection)
        """
        # 1. EOD check
        reason = cls.check_eod_flatten(current_time, config)
        if reason:
            return reason

        # 2. Per-trade stop
        reason = cls.check_per_trade_stop(trade, config)
        if reason:
            return reason

        # 3. Update trailing and check
        cls.update_trailing_stop(trade, config)
        reason = cls.check_trailing_stop(trade, config)
        if reason:
            return reason

        return None
