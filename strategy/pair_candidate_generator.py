import logging
from datetime import date
from typing import List, Tuple, Any
from data.market_cache import MarketCache, market_cache
from core.enums import MarketRegime
from strategy.pair_templates import PairTemplateGenerator

logger = logging.getLogger("AutoTrader")

class PairCandidateGenerator:
    """
    Builds an explicit matched-ATM executable template. The wider chain remains
    available for diagnostics, but is never exposed as a CE × PE execution matrix.
    """
    def __init__(
        self,
        cache: MarketCache | None = None,
        *,
        strike_step: int | None = None,
        depth: int = 4,
    ) -> None:
        self.cache = cache or market_cache
        self.strike_step = int(strike_step or self.cache.strike_step)
        self.depth = depth

    def generate_candidates(
        self,
        regime: MarketRegime | None = None,
        trading_day: date | None = None,
    ) -> List[Tuple[Any, Any]]:
        chain = self.cache.get_option_chain()
        if not chain:
            return []

        ce_strikes = [
            strike for strike, data in chain.items()
            if isinstance(strike, (int, float)) and data.get("CE") is not None
        ]
        pe_strikes = [
            strike for strike, data in chain.items()
            if isinstance(strike, (int, float)) and data.get("PE") is not None
        ]
        spot, _ = self.cache.get_spot()
        expiry = self.cache.get_active_expiry()
        day = trading_day or date.today()
        include_atm = not (
            expiry == day and regime == MarketRegime.SIDEWAYS
        )
        return PairTemplateGenerator.atm_itm_cross(
            ce_strikes=ce_strikes,
            pe_strikes=pe_strikes,
            spot=float(spot or 0.0),
            strike_step=self.strike_step,
            depth=self.depth,
            include_atm=include_atm,
        )
