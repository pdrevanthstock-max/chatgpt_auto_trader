import logging
from core.enums import MarketRegime, OrderType

logger = logging.getLogger("AutoTrader")

class OrderTypeSelector:
    """
    Decides between Market order (Directional regime) and Limit order (Sideways regime).
    """
    def select_order_type(self, regime: MarketRegime) -> OrderType:
        if regime == MarketRegime.DIRECTIONAL:
            logger.debug("OrderTypeSelector: DIRECTIONAL mode -> MARKET orders selected.")
            return OrderType.MARKET
        else:
            logger.debug("OrderTypeSelector: SIDEWAYS mode -> LIMIT orders selected.")
            return OrderType.LIMIT
