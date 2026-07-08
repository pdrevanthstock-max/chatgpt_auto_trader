"""
Position Sizer
───────────────
§6: Lot quantity derived from capital allocation, not hardcoded.
    "Never enter 2 lots on one side and 1 on the other."

Since BOTH legs are bought (confirmed), capital must cover 2 positions:
  total_cost = (ce_price + pe_price) × quantity × lot_size
  quantity = floor(capital / ((ce_price + pe_price) × lot_size))
"""

from __future__ import annotations

from loguru import logger

from config.settings import TradingConfig


class PositionSizer:
    """
    Calculates lot quantity from capital and current prices.
    Ensures quantity is identical for both legs (§4.6).
    """

    @staticmethod
    def calculate_quantity(
        ce_price: float,
        pe_price: float,
        config: TradingConfig,
    ) -> int:
        """
        Determine how many lots to buy, given:
          - Total capital allocated to this bot (§6: ₹30,000)
          - Current CE and PE prices
          - Nifty lot size (25)
          - Both legs are bought

        Returns the lot quantity (same for both legs).
        Minimum is 1 lot if capital permits.

        Capital allocated per trade = total_capital
        (since we're only in one trade at a time for v1)
        """
        lot_size = config.nifty_lot_size

        if ce_price <= 0 or pe_price <= 0:
            logger.warning(
                f"Invalid prices for sizing: CE={ce_price}, PE={pe_price}"
            )
            return 0

        # Cost of 1 lot of BOTH legs
        cost_per_lot = (ce_price + pe_price) * lot_size

        if cost_per_lot <= 0:
            return 0

        # How many lots can we afford?
        max_lots = int(config.total_capital / cost_per_lot)

        if max_lots < 1:
            logger.warning(
                f"Insufficient capital: need ₹{cost_per_lot:.2f} per lot, "
                f"have ₹{config.total_capital:.2f}"
            )
            return 0

        # For v1: limit to 1 lot to keep risk contained
        # Can be made configurable later
        quantity = min(max_lots, 1)

        logger.info(
            f"Position size: {quantity} lot(s) × {lot_size} = "
            f"{quantity * lot_size} contracts per leg. "
            f"Total cost: ₹{cost_per_lot * quantity:.2f}"
        )

        return quantity

    @staticmethod
    def calculate_capital_per_trade(
        ce_price: float,
        pe_price: float,
        quantity: int,
        config: TradingConfig,
    ) -> float:
        """
        Calculate the capital allocated to this specific trade.
        Used for §5.1 per-trade stop calculation (2% of THIS amount).
        """
        lot_size = config.nifty_lot_size
        return (ce_price + pe_price) * quantity * lot_size
