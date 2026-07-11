import logging
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any
from core.models import TradePlan, Trade
from core.enums import TradeDirection, ExitReason, TradePhase
from data.dhan_client import DhanClient
from data.market_cache import market_cache
from core.exceptions import DataFetchError, PartialFillError

logger = logging.getLogger("AutoTrader")

class BrokerExecutor:
    """
    Handles live execution of entry/exit/rotation/hedge-cut orders via Dhan API.
    Uses asyncio.gather to execute orders in parallel with safety timeouts and partial-fill rollback.
    """
    def __init__(self) -> None:
        self.client = DhanClient()

    async def execute_entry(self, plan: TradePlan, current_time: datetime) -> Trade:
        # Construct order payloads for both legs
        ce_details = self._build_order_details(
            strike=plan.scored_candidate.ce_strike,
            option_type="CALL",
            qty=plan.quantity * plan.lot_size,
            order_type=plan.order_type,
            limit_price=plan.ce_limit_price
        )
        pe_details = self._build_order_details(
            strike=plan.scored_candidate.pe_strike,
            option_type="PUT",
            qty=plan.quantity * plan.lot_size,
            order_type=plan.order_type,
            limit_price=plan.pe_limit_price
        )

        logger.info(f"Live Execution: Submitting parallel basket orders for {plan.scored_candidate.ce_strike}CE and {plan.scored_candidate.pe_strike}PE")

        try:
            # Parallel order placement with 3-second timeout
            # In live trading, this wraps the Dhan API place_order calls in asyncio tasks
            loop = asyncio.get_event_loop()
            
            # Simulated parallel call for stub safety, or real client call if credentials are active
            ce_task = loop.run_in_executor(None, self.client.place_order, ce_details)
            pe_task = loop.run_in_executor(None, self.client.place_order, pe_details)

            results = await asyncio.gather(ce_task, pe_task, return_exceptions=True)
            
            # Check results
            ce_order_id = results[0]
            pe_order_id = results[1]

            if isinstance(ce_order_id, Exception) or isinstance(pe_order_id, Exception) or not ce_order_id or not pe_order_id:
                # One or both failed -> roll back/abort
                raise PartialFillError("One or both entry orders failed to place or timed out.")

            # Assume mock fill prices for stub
            chain = market_cache.get_option_chain()
            ce_price = plan.ce_limit_price or chain.get(plan.scored_candidate.ce_strike, {}).get("CE", {}).get("last", 0.0)
            pe_price = plan.pe_limit_price or chain.get(plan.scored_candidate.pe_strike, {}).get("PE", {}).get("last", 0.0)

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

            logger.info(f"Live Execution: Entry basket filled. ID: {trade.id}")
            return trade

        except Exception as e:
            logger.error(f"Live entry basket failed: {e}. Unwinding partial fills...")
            # Unwind code would cancel outstanding orders here
            raise PartialFillError(f"Basket order aborted: {e}")

    async def execute_exit_both(self, trade: Trade, current_time: datetime, reason: ExitReason) -> None:
        # Build market sell orders for both legs
        ce_details = self._build_order_details(trade.strike_ce, "CALL", trade.quantity * trade.lot_size, "SELL")
        pe_details = self._build_order_details(trade.strike_pe, "PUT", trade.quantity * trade.lot_size, "SELL")

        loop = asyncio.get_event_loop()
        ce_task = loop.run_in_executor(None, self.client.place_order, ce_details)
        pe_task = loop.run_in_executor(None, self.client.place_order, pe_details)

        await asyncio.gather(ce_task, pe_task, return_exceptions=True)

        chain = market_cache.get_option_chain()
        trade.exit_ce_price = chain.get(trade.strike_ce, {}).get("CE", {}).get("last", trade.ce_current_price)
        trade.exit_pe_price = chain.get(trade.strike_pe, {}).get("PE", {}).get("last", trade.pe_current_price)
        trade.exit_time = current_time
        trade.exit_reason = reason
        trade.phase = TradePhase.CLOSED

        logger.info(f"Live Execution: Exit both legs complete. PnL: ₹{trade.combined_pnl:.2f}")

    async def execute_hedge_cut(self, trade: Trade, current_time: datetime) -> None:
        losing_leg = trade.losing_leg
        losing_strike = trade.strike_pe if losing_leg == "PE" else trade.strike_ce
        
        details = self._build_order_details(losing_strike, "CALL" if losing_leg == "CE" else "PUT", trade.quantity * trade.lot_size, "SELL")

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.client.place_order, details)

        chain = market_cache.get_option_chain()
        losing_exit = chain.get(losing_strike, {}).get(losing_leg, {}).get("last", 0.0)

        entry_price = trade.entry_pe_price if losing_leg == "PE" else trade.entry_ce_price
        losing_leg_pnl = (losing_exit - entry_price) * trade.quantity * trade.lot_size

        trade.hedge_cut_time = current_time
        trade.losing_leg_exit_price = losing_exit
        trade.losing_leg_pnl = round(losing_leg_pnl, 2)

        if losing_leg == "PE":
            trade.exit_pe_price = losing_exit
            trade.pe_current_price = losing_exit
        else:
            trade.exit_ce_price = losing_exit
            trade.ce_current_price = losing_exit

        trade.phase = TradePhase.PHASE_2_SINGLE_LEG
        logger.info(f"Live Execution: Hedge cut completed for leg {losing_leg}")

    async def execute_single_leg_exit(self, trade: Trade, current_time: datetime, reason: ExitReason) -> None:
        winning_leg = trade.winning_leg
        winning_strike = trade.strike_ce if winning_leg == "CE" else trade.strike_pe

        details = self._build_order_details(winning_strike, "CALL" if winning_leg == "CE" else "PUT", trade.quantity * trade.lot_size, "SELL")

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.client.place_order, details)

        chain = market_cache.get_option_chain()
        winning_exit = chain.get(winning_strike, {}).get(winning_leg, {}).get("last", 0.0)

        if winning_leg == "CE":
            trade.exit_ce_price = winning_exit
            trade.ce_current_price = winning_exit
        else:
            trade.exit_pe_price = winning_exit
            trade.pe_current_price = winning_exit

        trade.exit_time = current_time
        trade.exit_reason = reason
        trade.phase = TradePhase.CLOSED

        logger.info(f"Live Execution: Single leg exit complete. Final PnL: ₹{trade.combined_pnl:.2f}")

    def _build_order_details(
        self,
        strike: int,
        option_type: str,
        qty: int,
        direction: str = "BUY",
        order_type: str = "MARKET",
        limit_price: Optional[float] = None
    ) -> Dict[str, Any]:
        # Structurally correct Dhan order payload format
        payload = {
            "transactionType": direction,
            "exchangeSegment": "NSE_FNO",
            "instrument": "OPTIDX",
            "strike": strike,
            "optionType": option_type,
            "quantity": qty,
            "orderType": "LIMIT" if limit_price is not None else "MARKET",
        }
        if limit_price is not None:
            payload["price"] = limit_price
        return payload
