import logging
from datetime import datetime
from typing import Optional
from core.models import TradePlan, Trade
from core.enums import TradeDirection, ExitReason, TradePhase
from data.market_cache import market_cache
from core.exceptions import PartialFillError

logger = logging.getLogger("AutoTrader")

class PaperExecutor:
    """
    Simulates paper execution of entry, exit, rotation, and hedge-cut orders
    using prices retrieved from MarketCache.
    """
    def execute_entry(self, plan: TradePlan, current_time: datetime) -> Trade:
        chain = market_cache.get_option_chain()
        ce_data = chain.get(plan.scored_candidate.ce_strike, {}).get("CE")
        pe_data = chain.get(plan.scored_candidate.pe_strike, {}).get("PE")

        if not ce_data or not pe_data:
            raise PartialFillError("Option data missing from cache at entry execution.")

        # Determine entry prices based on order type (LIMIT vs MARKET)
        if plan.ce_limit_price is not None:
            ce_price = plan.ce_limit_price
        else:
            # Market order uses last price
            ce_price = ce_data.get("last", 0.0)

        if plan.pe_limit_price is not None:
            pe_price = plan.pe_limit_price
        else:
            pe_price = pe_data.get("last", 0.0)

        # Build Trade Direction
        # Bullish (winning leg CE) -> buy CE + buy PE
        # Bearish (winning leg PE) -> buy PE + buy CE
        direction = TradeDirection.LONG_CE if plan.scored_candidate.winning_leg == "CE" else TradeDirection.LONG_PE

        trade = Trade(
            direction=direction,
            strike_ce=plan.scored_candidate.ce_strike,
            strike_pe=plan.scored_candidate.pe_strike,
            entry_ce_price=ce_price,
            entry_pe_price=pe_price,
            quantity=plan.quantity,
            lot_size=plan.lot_size,
            entry_time=current_time,
            regime_at_entry=plan.regime,
            phase=TradePhase.PHASE_1_BOTH_LEGS,
            ce_current_price=ce_price,
            pe_current_price=pe_price
        )

        logger.info(
            f"PaperExecutor [ENTRY FILLED]: {trade.id} | {plan.scored_candidate.ce_strike}CE @ ₹{ce_price:.2f} "
            f"and {plan.scored_candidate.pe_strike}PE @ ₹{pe_price:.2f}. Qty: {plan.quantity} lots."
        )
        return trade

    def execute_exit_both(self, trade: Trade, current_time: datetime, reason: ExitReason) -> None:
        chain = market_cache.get_option_chain()
        ce_data = chain.get(trade.strike_ce, {}).get("CE")
        pe_data = chain.get(trade.strike_pe, {}).get("PE")

        if not ce_data or not pe_data:
            # Fallback to current stored prices if cache is empty
            ce_exit = trade.ce_current_price
            pe_exit = trade.pe_current_price
        else:
            ce_exit = ce_data.get("last", trade.ce_current_price)
            pe_exit = pe_data.get("last", trade.pe_current_price)

        trade.exit_ce_price = ce_exit
        trade.exit_pe_price = pe_exit
        trade.exit_time = current_time
        trade.exit_reason = reason
        trade.phase = TradePhase.CLOSED

        logger.info(
            f"PaperExecutor [EXIT BOTH FILLED]: {trade.id} | CE exit @ ₹{ce_exit:.2f}, PE exit @ ₹{pe_exit:.2f}. "
            f"PnL: ₹{trade.combined_pnl:.2f}. Reason: {reason.value}."
        )

    def execute_hedge_cut(self, trade: Trade, current_time: datetime) -> None:
        chain = market_cache.get_option_chain()
        
        # Losing leg is identified by the losing_leg property of Trade
        losing_leg = trade.losing_leg
        losing_strike = trade.strike_pe if losing_leg == "PE" else trade.strike_ce
        leg_data = chain.get(losing_strike, {}).get(losing_leg)

        if not leg_data:
            losing_exit = trade.pe_current_price if losing_leg == "PE" else trade.ce_current_price
        else:
            losing_exit = leg_data.get("last", 0.0)

        # Book the loss on the losing leg
        entry_price = trade.entry_pe_price if losing_leg == "PE" else trade.entry_ce_price
        losing_leg_pnl = (losing_exit - entry_price) * trade.quantity * trade.lot_size

        trade.hedge_cut_time = current_time
        trade.losing_leg_exit_price = losing_exit
        trade.losing_leg_pnl = round(losing_leg_pnl, 2)
        
        # Mark prices in trade
        if losing_leg == "PE":
            trade.exit_pe_price = losing_exit
            trade.pe_current_price = losing_exit
        else:
            trade.exit_ce_price = losing_exit
            trade.ce_current_price = losing_exit

        trade.phase = TradePhase.PHASE_2_SINGLE_LEG

        logger.info(
            f"PaperExecutor [HEDGE CUT FILLED]: {trade.id} | Losing leg {losing_leg} cut @ ₹{losing_exit:.2f}. "
            f"Realized loss: ₹{losing_leg_pnl:.2f}. Winning leg continues open."
        )

    def execute_single_leg_exit(self, trade: Trade, current_time: datetime, reason: ExitReason) -> None:
        chain = market_cache.get_option_chain()
        winning_leg = trade.winning_leg
        winning_strike = trade.strike_ce if winning_leg == "CE" else trade.strike_pe
        leg_data = chain.get(winning_strike, {}).get(winning_leg)

        if not leg_data:
            winning_exit = trade.ce_current_price if winning_leg == "CE" else trade.pe_current_price
        else:
            winning_exit = leg_data.get("last", 0.0)

        if winning_leg == "CE":
            trade.exit_ce_price = winning_exit
            trade.ce_current_price = winning_exit
        else:
            trade.exit_pe_price = winning_exit
            trade.pe_current_price = winning_exit

        trade.exit_time = current_time
        trade.exit_reason = reason
        trade.phase = TradePhase.CLOSED

        logger.info(
            f"PaperExecutor [SINGLE LEG EXIT FILLED]: {trade.id} | Winning leg {winning_leg} exit @ ₹{winning_exit:.2f}. "
            f"Final Trade PnL: ₹{trade.combined_pnl:.2f}. Reason: {reason.value}."
        )
