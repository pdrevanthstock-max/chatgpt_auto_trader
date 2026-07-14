import logging

from config.settings import TradingConfig

logger = logging.getLogger("AutoTrader")


class DailyCircuitBreaker:
    """Checks whether session loss has breached the configured capital cap."""

    def __init__(self) -> None:
        self._was_triggered = False

    def is_breaker_triggered(self, realized_pnl: float, config: TradingConfig) -> bool:
        loss_limit = -abs(config.daily_loss_limit)
        triggered = realized_pnl <= loss_limit

        if triggered and not self._was_triggered:
            logger.warning(
                f"DailyCircuitBreaker: Realized loss of Rs {realized_pnl:.2f} "
                f"exceeds daily limit of Rs {loss_limit:.2f} "
                f"({config.daily_loss_limit_pct:.1%}). Breaker triggered."
            )
        elif not triggered:
            logger.debug(
                f"DailyCircuitBreaker: Realized PnL is Rs {realized_pnl:.2f}. "
                f"Limit is Rs {loss_limit:.2f}."
            )

        self._was_triggered = triggered
        return triggered
