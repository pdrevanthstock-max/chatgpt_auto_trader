import math
import logging
from config.settings import TradingConfig

logger = logging.getLogger("AutoTrader")

class PositionSizer:
    """
    Computes option lot size dynamically based on current combined premium
    and allocated capital. Lot size is 65 (Nifty).
    """
    def calculate_lots(self, ce_price: float, pe_price: float, config: TradingConfig) -> int:
        if ce_price <= 0.0 or pe_price <= 0.0:
            return 0

        combined_premium = ce_price + pe_price
        lot_cost = combined_premium * config.nifty_lot_size

        if lot_cost <= 0.0:
            return 0

        lots = int(math.floor(config.total_capital / lot_cost))
        
        logger.info(
            f"PositionSizer: Capital ₹{config.total_capital:.2f}. "
            f"Combined premium ₹{combined_premium:.2f}. Lot cost ₹{lot_cost:.2f}. "
            f"Calculated lots: {lots}."
        )
        return lots
