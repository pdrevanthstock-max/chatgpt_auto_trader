import logging
from config.settings import TradingConfig

logger = logging.getLogger("AutoTrader")

class DailyCircuitBreaker:
    """
    Checks if today's realized loss has breached the configured capital cap.
    """
    def is_breaker_triggered(self, realized_pnl: float, config: TradingConfig) -> bool:
        loss_limit = -abs(config.daily_loss_limit)
        
        if realized_pnl <= loss_limit:
            logger.warning(
                f"DailyCircuitBreaker: Realized loss of ₹{realized_pnl:.2f} "
                f"exceeds daily limit of ₹{loss_limit:.2f} (3%). Breaker triggered."
            )
            return True
            
        logger.debug(f"DailyCircuitBreaker: Realized PnL is ₹{realized_pnl:.2f}. Limit is ₹{loss_limit:.2f}.")
        return False
