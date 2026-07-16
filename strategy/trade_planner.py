import logging
import math
from numbers import Real
from core.models import ScoredCandidate, TradePlan
from core.enums import MarketRegime, OrderType
from config.settings import TradingConfig

logger = logging.getLogger("AutoTrader")

class TradePlanner:
    """
    Assembles a ranked candidate pair, the current market regime, and position size
    into a structured TradePlan.
    """
    def plan_trade(
        self,
        candidate: ScoredCandidate,
        regime: MarketRegime,
        quantity: int,
        ce_price: float,
        pe_price: float,
        config: TradingConfig,
        ce_bid: float | None = None,
        pe_bid: float | None = None,
        lot_size: int | None = None,
        index_symbol: str = "NIFTY",
    ) -> TradePlan:
        # Directional regime -> Market orders
        # Sideways regime -> Limit orders priced at candle close
        if regime == MarketRegime.DIRECTIONAL:
            order_type = OrderType.MARKET
            ce_limit = None
            pe_limit = None
        else:
            order_type = OrderType.LIMIT
            values = (ce_bid, ce_price, pe_bid, pe_price)
            if any(
                isinstance(value, bool)
                or not isinstance(value, Real)
                or not math.isfinite(float(value))
                or float(value) <= 0.0
                for value in values
            ) or float(ce_price) < float(ce_bid) or float(pe_price) < float(pe_bid):
                raise ValueError(
                    "SIDEWAYS limit pricing requires positive, non-inverted CE/PE bids and asks."
                )
            ce_limit = round((float(ce_bid) + float(ce_price)) / 2.0, 2)
            pe_limit = round((float(pe_bid) + float(pe_price)) / 2.0, 2)

        plan = TradePlan(
            scored_candidate=candidate,
            regime=regime,
            order_type=order_type,
            quantity=quantity,
            lot_size=int(lot_size or config.nifty_lot_size),
            ce_limit_price=ce_limit,
            pe_limit_price=pe_limit,
            index_symbol=str(index_symbol).upper(),
        )

        logger.info(
            f"Planned trade for {candidate.ce_strike}CE-{candidate.pe_strike}PE. "
            f"Regime: {regime.value}, OrderType: {order_type.value}, Qty: {quantity} lots."
        )
        return plan
