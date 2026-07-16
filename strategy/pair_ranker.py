import logging
from typing import List, Optional
from core.models import CandidatePair, ScoredCandidate
from data.market_cache import MarketCache, market_cache
from config.settings import TradingConfig
from strategy.position_sizer import PositionSizer
from strategy.profitability import ProfitabilityCalculator, ProfitabilityInput

logger = logging.getLogger("AutoTrader")

class PairRanker:
    """
    Ranks surviving candidate pairs by projected net profit after brokerage.
    Attaches a score confidence percentage to each.
    """
    def __init__(self, cache: MarketCache | None = None) -> None:
        self.cache = cache or market_cache
        self.last_decisions: dict[tuple[object, object], dict[str, object]] = {}

    def rank_candidates(
        self,
        candidates: List[CandidatePair],
        config: TradingConfig,
        momentum_multiplier: float = 1.0,
        lot_size: int | None = None,
        available_capital: float | None = None,
    ) -> Optional[ScoredCandidate]:
        if not candidates:
            self.last_decisions = {}
            return None

        chain = self.cache.get_option_chain()
        contract_lot_size = int(lot_size or config.nifty_lot_size)
        scored_list: List[ScoredCandidate] = []

        self.last_decisions = {}

        for candidate in candidates:
            ce_data = chain.get(candidate.ce_strike, {}).get("CE")
            pe_data = chain.get(candidate.pe_strike, {}).get("PE")

            if not ce_data or not pe_data:
                self.last_decisions[(candidate.ce_strike, candidate.pe_strike)] = {
                    "result": "FAIL", "reason": "MISSING_EXECUTABLE_QUOTE"
                }
                continue

            if config.execution_mode == "BACKTEST":
                ce_price = ce_data.get("last", ce_data.get("close", 0.0))
                pe_price = pe_data.get("last", pe_data.get("close", 0.0))
            else:
                # A long entry pays the ask; ranking on LTP can invent profit
                # that is unavailable at the executable price.
                ce_price = ce_data.get("ask", 0.0)
                pe_price = pe_data.get("ask", 0.0)
            
            # Premium similarity check (maximum 10% difference as requested by user)
            if ce_price <= 0.0 or pe_price <= 0.0:
                self.last_decisions[(candidate.ce_strike, candidate.pe_strike)] = {
                    "result": "FAIL", "reason": "NON_POSITIVE_EXECUTABLE_PRICE"
                }
                continue
            
            premium_ratio = max(ce_price, pe_price) / min(ce_price, pe_price)
            if premium_ratio > config.maximum_pair_premium_ratio:
                self.last_decisions[(candidate.ce_strike, candidate.pe_strike)] = {
                    "result": "FAIL", "reason": "PREMIUM_RATIO_EXCEEDED"
                }
                continue

            lots = PositionSizer().calculate_lots(
                ce_price,
                pe_price,
                config,
                lot_size=contract_lot_size,
                available_capital=available_capital,
            )
            if lots <= 0:
                self.last_decisions[(candidate.ce_strike, candidate.pe_strike)] = {
                    "result": "FAIL", "reason": "ZERO_SAFE_QUANTITY"
                }
                continue
            ce_bid = ce_data.get("bid", ce_price)
            pe_bid = pe_data.get("bid", pe_price)
            projected = ProfitabilityCalculator.calculate(ProfitabilityInput(
                entry_ce_ask=ce_price,
                entry_pe_ask=pe_price,
                projected_ce_bid=max(0.05, ce_bid * (1.0 + candidate.ce_velocity * momentum_multiplier / 100.0)),
                projected_pe_bid=max(0.05, pe_bid * (1.0 + candidate.pe_velocity * momentum_multiplier / 100.0)),
                lots=lots,
                lot_size=contract_lot_size,
                freeze_units=config.max_units_per_leg,
                slippage_per_unit_per_fill=config.projected_slippage_per_unit_per_fill,
                minimum_net_profit=config.minimum_projected_net_profit,
                minimum_return_pct=config.minimum_projected_return_pct,
            ))
            projected_net_profit = projected.projected_net_pnl
            if not projected.buffer_passed:
                self.last_decisions[(candidate.ce_strike, candidate.pe_strike)] = {
                    "result": "FAIL",
                    "reason": "PROJECTED_NET_BUFFER_FAILED",
                    "projected_gross": projected.gross_pnl,
                    "projected_costs": projected.transaction_costs.total,
                    "projected_slippage": projected.slippage,
                    "projected_net": projected.projected_net_pnl,
                    "lots": lots,
                    "units_per_leg": projected.units_per_leg,
                }
                continue

            # Calculate confidence score (deterministic heuristics)
            # A profitable, executable candidate starts at the minimum passing
            # confidence. Volume/OI improve ranking but their absence does not
            # act as a second hidden liquidity rejection.
            confidence = 70.0
            
            # Check spreads
            ce_bid = ce_data.get("bid", 0.0)
            ce_ask = ce_data.get("ask", 0.0)
            pe_bid = pe_data.get("bid", 0.0)
            pe_ask = pe_data.get("ask", 0.0)
            
            if ce_bid > 0 and ce_ask > 0 and pe_bid > 0 and pe_ask > 0:
                ce_spread = ce_ask - ce_bid
                pe_spread = pe_ask - pe_bid
                if ce_spread <= 0.50 and pe_spread <= 0.50:
                    confidence += 15.0
            else:
                # In backtesting, spreads are not available, default to positive contribution
                confidence += 10.0

            # Check volume agreement
            ce_vol = ce_data.get("volume", 0)
            pe_vol = pe_data.get("volume", 0)
            if config.execution_mode == "BACKTEST":
                if ce_vol >= 5 and pe_vol >= 5:
                    confidence += 10.0
            else:
                if ce_vol >= 500 and pe_vol >= 500:
                    confidence += 10.0

            # Check OI agreement
            ce_oi = ce_data.get("oi", 0)
            pe_oi = pe_data.get("oi", 0)
            if ce_oi >= 2000 and pe_oi >= 2000:
                confidence += 10.0
            elif config.execution_mode == "BACKTEST":
                confidence += 10.0  # OI not available in backtest

            # Cap confidence
            confidence = min(95.0, confidence)

            # Filter out low confidence candidates if needed (e.g. < 70% confidence)
            if confidence < 70.0:
                self.last_decisions[(candidate.ce_strike, candidate.pe_strike)] = {
                    "result": "FAIL", "reason": "LOW_CONFIDENCE", "confidence": confidence
                }
                continue

            scored_list.append(ScoredCandidate(
                ce_strike=candidate.ce_strike,
                pe_strike=candidate.pe_strike,
                ce_velocity=candidate.ce_velocity,
                pe_velocity=candidate.pe_velocity,
                divergence=candidate.divergence,
                winning_leg=candidate.winning_leg,
                projected_net_profit=round(projected_net_profit, 2),
                confidence=round(confidence, 1)
            ))
            self.last_decisions[(candidate.ce_strike, candidate.pe_strike)] = {
                "result": "PASS",
                "reason": "PROFITABILITY_BUFFER_PASSED",
                "projected_gross": projected.gross_pnl,
                "projected_costs": projected.transaction_costs.total,
                "projected_slippage": projected.slippage,
                "projected_net": projected.projected_net_pnl,
                "lots": lots,
                "units_per_leg": projected.units_per_leg,
                "confidence": confidence,
            }

        if not scored_list:
            return None

        # Sort by projected_net_profit descending
        scored_list.sort(key=lambda x: x.projected_net_profit, reverse=True)
        return scored_list[0]
