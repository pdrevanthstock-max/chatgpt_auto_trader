"""
Daily Circuit Breaker
──────────────────────
§5.2: Stop opening ANY new trades for the rest of the day once
cumulative (realized + unrealized) loss reaches 3% of total capital.

This is a PORTFOLIO-LEVEL breaker, separate from the per-trade 2% stop.
Must be tracked independently — requires summing PnL across ALL of
today's trades, not just checking the current open position.
"""

from __future__ import annotations

from loguru import logger

from core.models import DaySession
from config.settings import TradingConfig


class DailyCircuitBreaker:
    """
    Tracks cumulative daily PnL and blocks new entries when limit is hit.

    §5.2 implementation:
      realized_pnl = sum of PnL from all closed trades today
      unrealized_pnl = PnL of currently open position (if any)
      total = realized + unrealized
      limit = total_capital × daily_loss_limit_pct (default: 3% of ₹30,000 = ₹900)
    """

    @staticmethod
    def is_breaker_hit(
        session: DaySession,
        config: TradingConfig,
    ) -> bool:
        """
        Check if the daily circuit breaker has been triggered.

        Returns True if cumulative daily loss exceeds the limit.
        Once hit, no new trades should be opened for the rest of the day.
        """
        total_pnl = session.total_pnl  # realized + unrealized
        limit = config.total_capital * config.daily_loss_limit_pct

        if total_pnl < 0 and abs(total_pnl) >= limit:
            if not session.circuit_breaker_hit:
                logger.error(
                    f"CIRCUIT BREAKER HIT: Daily PnL ₹{total_pnl:.2f} "
                    f"exceeds {config.daily_loss_limit_pct * 100:.1f}% limit "
                    f"of ₹{limit:.2f}. No more trades today."
                )
                session.circuit_breaker_hit = True
            return True

        return False

    @staticmethod
    def can_open_new_trade(
        session: DaySession,
        config: TradingConfig,
    ) -> bool:
        """
        Convenience method: can we open a new trade?
        Inverse of is_breaker_hit, with additional check that
        there's no existing open position.
        """
        if session.circuit_breaker_hit:
            return False

        if DailyCircuitBreaker.is_breaker_hit(session, config):
            return False

        if session.open_trade is not None:
            return False  # Already have an open position

        return True
