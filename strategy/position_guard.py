import logging
from typing import Optional
from core.models import Trade

logger = logging.getLogger("AutoTrader")

class PositionGuard:
    """
    Guards against overlapping positions.
    Returns True if a trade is currently open, False otherwise.
    """
    def is_position_open(self, active_trade: Optional[Trade]) -> bool:
        if active_trade is not None and active_trade.is_open:
            logger.debug(f"PositionGuard: Trade {active_trade.id} is active. Gate closed.")
            return True
        logger.debug("PositionGuard: No active trade. Gate open.")
        return False
