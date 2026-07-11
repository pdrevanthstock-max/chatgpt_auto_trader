import logging
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
        config: TradingConfig
    ) -> TradePlan:
        # Directional regime -> Market orders
        # Sideways regime -> Limit orders priced at candle close
        if regime == MarketRegime.DIRECTIONAL:
            order_type = OrderType.MARKET
            ce_limit = None
            pe_limit = None
        else:
            order_type = OrderType.LIMIT
            ce_limit = ce_price
            pe_limit = pe_price

        plan = TradePlan(
            scored_candidate=candidate,
            regime=regime,
            order_type=order_type,
            quantity=quantity,
            lot_size=config.nifty_lot_size,
            ce_limit_price=ce_limit,
            pe_limit_price=pe_limit
        )

        logger.info(
            f"Planned trade for {candidate.ce_strike}CE-{candidate.pe_strike}PE. "
            f"Regime: {regime.value}, OrderType: {order_type.value}, Qty: {quantity} lots."
        )
        return plan
