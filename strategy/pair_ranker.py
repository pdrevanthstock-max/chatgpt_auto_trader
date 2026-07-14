import logging
from typing import List, Optional
from core.models import CandidatePair, ScoredCandidate
from core.transaction_costs import calculate_option_round_trip_costs
from data.market_cache import market_cache
from config.settings import TradingConfig

logger = logging.getLogger("AutoTrader")

class PairRanker:
    """
    Ranks surviving candidate pairs by projected net profit after brokerage.
    Attaches a score confidence percentage to each.
    """
    def rank_candidates(
        self,
        candidates: List[CandidatePair],
        config: TradingConfig,
        momentum_multiplier: float = 1.0
    ) -> Optional[ScoredCandidate]:
        if not candidates:
            return None

        chain = market_cache.get_option_chain()
        scored_list: List[ScoredCandidate] = []

        slippage_cost = 10.0  # Rs 5 per leg average, 2 legs = Rs 10

        for candidate in candidates:
            ce_data = chain.get(candidate.ce_strike, {}).get("CE")
            pe_data = chain.get(candidate.pe_strike, {}).get("PE")

            if not ce_data or not pe_data:
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
                continue
            
            avg_price = (ce_price + pe_price) / 2.0
            price_diff_pct = abs(ce_price - pe_price) / avg_price
            if price_diff_pct > 0.10:
                continue

            combined_premium = ce_price + pe_price

            # Estimate combined expected move
            expected_ce_move = candidate.ce_velocity * momentum_multiplier
            expected_pe_move = candidate.pe_velocity * momentum_multiplier
            
            # Combine the relative change (expressed as % change of individual contract premiums)
            # PnL = (ce_change_rupees + pe_change_rupees)
            expected_combined_change_pct = (expected_ce_move * ce_price + expected_pe_move * pe_price) / combined_premium
            expected_combined_pnl_rupees = (expected_combined_change_pct / 100.0) * combined_premium * config.nifty_lot_size

            estimated_costs = calculate_option_round_trip_costs(
                entry_ce_price=ce_price,
                entry_pe_price=pe_price,
                exit_ce_price=ce_price,
                exit_pe_price=pe_price,
                lots=1,
                lot_size=config.nifty_lot_size,
            ).total
            projected_net_profit = expected_combined_pnl_rupees - estimated_costs - slippage_cost
            if projected_net_profit <= 0.0:
                continue

            # Calculate confidence score (deterministic heuristics)
            confidence = 60.0  # Base confidence
            
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

        if not scored_list:
            return None

        # Sort by projected_net_profit descending
        scored_list.sort(key=lambda x: x.projected_net_profit, reverse=True)
        return scored_list[0]
