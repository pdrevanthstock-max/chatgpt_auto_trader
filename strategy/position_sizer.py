import math
import logging
from config.settings import TradingConfig

logger = logging.getLogger("AutoTrader")

class PositionSizer:
    """
    Computes option lot size dynamically based on current combined premium
    and allocated capital. Lot size is 65 (Nifty).
    """
    def calculate_lots(
        self,
        ce_price: float,
        pe_price: float,
        config: TradingConfig,
        available_capital: float | None = None,
        lot_size: int | None = None,
    ) -> int:
        if ce_price <= 0.0 or pe_price <= 0.0:
            return 0

        combined_premium = ce_price + pe_price
        contract_lot_size = int(lot_size or config.nifty_lot_size)
        if contract_lot_size <= 0:
            return 0
        lot_cost = combined_premium * contract_lot_size

        if lot_cost <= 0.0:
            return 0

        capital = config.total_capital if available_capital is None else max(0.0, available_capital)
        deployable_capital = capital * config.max_capital_deployment_pct
        capital_lots = int(math.floor(deployable_capital / lot_cost))
        unit_ceiling_lots = int(math.floor(config.max_units_per_leg / contract_lot_size))
        lots = min(capital_lots, unit_ceiling_lots)
        
        logger.info(
            f"PositionSizer: Capital ₹{config.total_capital:.2f}. "
            f"Combined premium ₹{combined_premium:.2f}. Lot cost ₹{lot_cost:.2f}. "
            f"Capital lots: {capital_lots}; unit-ceiling lots: {unit_ceiling_lots}; "
            f"calculated lots: {lots}."
        )
        return lots
