import logging
import asyncio
import time
from datetime import datetime
from typing import Optional, Dict, Any
from core.models import TradePlan, Trade
from core.enums import TradeDirection, ExitReason, TradePhase
from data.dhan_client import DhanClient
from data.market_cache import market_cache
from core.exceptions import DataFetchError, PartialFillError, PartialOrderFillError
from core.transaction_costs import calculate_option_round_trip_costs
from execution.capital_firewall import LiveCapitalFirewall

logger = logging.getLogger("AutoTrader")

class BrokerExecutor:
    """
    Handles live execution of entry/exit/rotation/hedge-cut orders via Dhan API.
    Uses asyncio.gather to execute orders in parallel with safety timeouts and partial-fill rollback.
    """
    FILL_TIMEOUT_SECONDS = 5.0
    FILL_POLL_SECONDS = 0.25

    def __init__(self, allocation_limit: float, reserve_pct: float = 0.10) -> None:
        self.client = DhanClient(orders_enabled=True)
        self.capital_firewall = LiveCapitalFirewall(
            allocation_limit=allocation_limit,
            reserve_pct=reserve_pct,
        )

    def _authorize_entry_budget(self, plan: TradePlan) -> None:
        if not hasattr(self, "capital_firewall") or self.capital_firewall is None:
            raise PartialFillError("LIVE capital firewall is unavailable; entry blocked.")
        chain = market_cache.get_option_chain()
        ce_quote = chain.get(plan.scored_candidate.ce_strike, {}).get("CE")
        pe_quote = chain.get(plan.scored_candidate.pe_strike, {}).get("PE")
        if not ce_quote or not pe_quote:
            raise PartialFillError("LIVE allocation check requires both executable quotes.")
        ce_ask = float(ce_quote.get("ask", 0.0) or 0.0)
        pe_ask = float(pe_quote.get("ask", 0.0) or 0.0)
        if ce_ask <= 0.0 or pe_ask <= 0.0:
            raise PartialFillError("LIVE allocation check requires positive asks.")
        units = plan.quantity * plan.lot_size
        costs = calculate_option_round_trip_costs(
            entry_ce_price=ce_ask,
            entry_pe_price=pe_ask,
            exit_ce_price=ce_ask,
            exit_pe_price=pe_ask,
            lots=plan.quantity,
            lot_size=plan.lot_size,
        ).total
        required_funds = ((ce_ask + pe_ask) * units) + costs
        try:
            fund_limits = self.client.get_fund_limits()
            self.capital_firewall.authorize_entry(
                required_funds=required_funds,
                broker_available_funds=fund_limits.get("available_balance"),
            )
        except Exception as error:
            raise PartialFillError(f"LIVE capital firewall blocked entry: {error}") from error

    async def _await_full_fill(self, order_id: str, expected_qty: int) -> float:
        deadline = time.monotonic() + self.FILL_TIMEOUT_SECONDS
        terminal_failures = {"REJECTED", "CANCELLED", "EXPIRED"}
        last_order: Dict[str, Any] = {}
        while time.monotonic() <= deadline:
            order = await asyncio.to_thread(self.client.get_order_by_id, order_id)
            last_order = order
            status = str(order.get("orderStatus", order.get("order_status", ""))).upper()
            filled_qty = int(order.get("filledQty", order.get("filled_qty", 0)) or 0)
            if status == "TRADED" and filled_qty == expected_qty:
                price = float(order.get("averageTradedPrice", order.get("average_traded_price", 0.0)) or 0.0)
                if price <= 0.0:
                    raise PartialFillError(f"Order {order_id} has no valid average fill price.")
                return price
            if status in terminal_failures:
                if filled_qty > 0:
                    raise PartialOrderFillError(
                        f"Order {order_id} ended {status} after partially filling "
                        f"{filled_qty}/{expected_qty} units.",
                        filled_qty=filled_qty,
                        average_price=float(
                            order.get(
                                "averageTradedPrice",
                                order.get("average_traded_price", 0.0),
                            )
                            or 0.0
                        ),
                    )
                raise PartialFillError(
                    f"Order {order_id} ended {status} with {filled_qty}/{expected_qty} units filled."
                )
            await asyncio.sleep(self.FILL_POLL_SECONDS)

        filled_qty = int(
            last_order.get("filledQty", last_order.get("filled_qty", 0)) or 0
        )
        remaining_qty = max(0, expected_qty - filled_qty)
        if remaining_qty > 0:
            try:
                await asyncio.to_thread(self.client.cancel_order, order_id)
            except Exception as cancel_error:
                raise PartialFillError(
                    f"Order {order_id} timed out and cancellation was not confirmed: "
                    f"{cancel_error}. Manual broker reconciliation is required."
                ) from cancel_error
        if filled_qty > 0:
            raise PartialOrderFillError(
                f"Order {order_id} remainder was cancelled after filling "
                f"{filled_qty}/{expected_qty} units.",
                filled_qty=filled_qty,
                average_price=float(
                    last_order.get(
                        "averageTradedPrice",
                        last_order.get("average_traded_price", 0.0),
                    )
                    or 0.0
                ),
            )
        raise PartialFillError(
            f"Order {order_id} fill timed out; unfilled remainder was cancelled."
        )

    async def _contain_mixed_entry_placements(
        self,
        results: list,
        plan: TradePlan,
    ) -> None:
        """Cancel unfilled quantities and unwind any fills when only one leg was accepted."""
        containment_failures = []
        legs = (
            ("CE", plan.scored_candidate.ce_strike, "CALL"),
            ("PE", plan.scored_candidate.pe_strike, "PUT"),
        )
        for result, (_, strike, option_type) in zip(results, legs):
            if isinstance(result, Exception) or not result:
                continue
            try:
                order = await asyncio.to_thread(self.client.get_order_by_id, result)
                filled_qty = int(order.get("filledQty", order.get("filled_qty", 0)) or 0)
                remaining_qty = int(
                    order.get(
                        "remainingQuantity",
                        max(0, (plan.quantity * plan.lot_size) - filled_qty),
                    )
                    or 0
                )
                if remaining_qty > 0:
                    await asyncio.to_thread(self.client.cancel_order, result)
                if filled_qty > 0:
                    unwind_details = self._build_order_details(
                        strike,
                        option_type,
                        filled_qty,
                        "SELL",
                    )
                    unwind_order_id = await asyncio.to_thread(
                        self.client.place_order, unwind_details
                    )
                    await self._await_full_fill(unwind_order_id, filled_qty)
            except Exception as containment_error:
                containment_failures.append(containment_error)
        if containment_failures:
            raise PartialFillError(
                "Mixed entry placement could not be fully contained; manual broker "
                "reconciliation is required."
            )

    async def execute_entry(self, plan: TradePlan, current_time: datetime) -> Trade:
        self._authorize_entry_budget(plan)
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
            # Parallel order placement; retain every broker order ID before deciding
            # whether containment is necessary.
            loop = asyncio.get_event_loop()
            
            # Simulated parallel call for stub safety, or real client call if credentials are active
            ce_task = loop.run_in_executor(None, self.client.place_order, ce_details)
            pe_task = loop.run_in_executor(None, self.client.place_order, pe_details)

            # Do not abandon placement threads on an application timeout: doing so can
            # lose an accepted broker order ID and leave an untracked live position.
            results = await asyncio.gather(ce_task, pe_task, return_exceptions=True)
            
            # Check results
            ce_order_id = results[0]
            pe_order_id = results[1]

            if isinstance(ce_order_id, Exception) or isinstance(pe_order_id, Exception) or not ce_order_id or not pe_order_id:
                await self._contain_mixed_entry_placements(results, plan)
                raise PartialFillError(
                    "One entry placement failed; every accepted order was contained."
                )

            confirmations = await asyncio.gather(
                self._await_full_fill(ce_order_id, plan.quantity * plan.lot_size),
                self._await_full_fill(pe_order_id, plan.quantity * plan.lot_size),
                return_exceptions=True,
            )
            ce_result, pe_result = confirmations
            failures = [result for result in confirmations if isinstance(result, Exception)]
            if failures:
                unwind_failures = []
                for leg, result in (("CE", ce_result), ("PE", pe_result)):
                    if isinstance(result, PartialOrderFillError):
                        unwind_qty = result.filled_qty
                    elif isinstance(result, Exception):
                        continue
                    else:
                        unwind_qty = plan.quantity * plan.lot_size
                    strike = (
                        plan.scored_candidate.ce_strike
                        if leg == "CE"
                        else plan.scored_candidate.pe_strike
                    )
                    unwind_details = self._build_order_details(
                        strike,
                        "CALL" if leg == "CE" else "PUT",
                        unwind_qty,
                        "SELL",
                    )
                    try:
                        unwind_order_id = await asyncio.to_thread(
                            self.client.place_order, unwind_details
                        )
                        await self._await_full_fill(
                            unwind_order_id, unwind_qty
                        )
                    except Exception as unwind_error:
                        unwind_failures.append(unwind_error)
                if unwind_failures:
                    raise PartialFillError(
                        "Entry basket incomplete and automatic unwind was not fully confirmed; "
                        "manual broker reconciliation is required."
                    )
                raise PartialFillError(
                    "Entry basket incomplete; every confirmed leg was automatically unwound."
                )

            ce_price = float(ce_result)
            pe_price = float(pe_result)

            direction = TradeDirection.LONG_CE if plan.scored_candidate.winning_leg == "CE" else TradeDirection.LONG_PE

            trade = Trade(
                execution_mode="LIVE",
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
                post_daily_sl=plan.post_daily_sl,
                risk_capital_at_entry=plan.risk_capital_at_entry,
                hard_stop_loss=plan.hard_stop_loss,
                ce_open_units=plan.quantity * plan.lot_size,
                pe_open_units=plan.quantity * plan.lot_size,
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
        full_units = trade.quantity * trade.lot_size
        ce_units = full_units if trade.ce_open_units is None else trade.ce_open_units
        pe_units = full_units if trade.pe_open_units is None else trade.pe_open_units
        if ce_units <= 0 and pe_units <= 0:
            raise PartialFillError("Trade has no recorded open units to exit.")

        loop = asyncio.get_event_loop()
        placements = []
        legs = []
        if ce_units > 0:
            ce_details = self._build_order_details(trade.strike_ce, "CALL", ce_units, "SELL")
            placements.append(loop.run_in_executor(None, self.client.place_order, ce_details))
            legs.append(("CE", ce_units))
        if pe_units > 0:
            pe_details = self._build_order_details(trade.strike_pe, "PUT", pe_units, "SELL")
            placements.append(loop.run_in_executor(None, self.client.place_order, pe_details))
            legs.append(("PE", pe_units))

        order_ids = await asyncio.gather(*placements, return_exceptions=True)
        confirmations = []
        for order_id, (_, qty) in zip(order_ids, legs):
            if isinstance(order_id, Exception) or not order_id:
                confirmations.append(
                    PartialFillError(f"Exit order placement failed: {order_id}")
                )
            else:
                try:
                    confirmations.append(await self._await_full_fill(order_id, qty))
                except Exception as confirmation_error:
                    confirmations.append(confirmation_error)
        failures = []
        for (leg, requested_qty), result in zip(legs, confirmations):
            if isinstance(result, Exception):
                failures.append(result)
                if isinstance(result, PartialOrderFillError):
                    still_open = max(0, requested_qty - result.filled_qty)
                    if leg == "CE":
                        trade.exit_ce_price = result.average_price
                        trade.ce_current_price = result.average_price
                        trade.ce_open_units = still_open
                    else:
                        trade.exit_pe_price = result.average_price
                        trade.pe_current_price = result.average_price
                        trade.pe_open_units = still_open
                continue
            if leg == "CE":
                trade.exit_ce_price = result
                trade.ce_current_price = result
                trade.ce_open_units = 0
            else:
                trade.exit_pe_price = result
                trade.pe_current_price = result
                trade.pe_open_units = 0

        remaining_ce = full_units if trade.ce_open_units is None else trade.ce_open_units
        remaining_pe = full_units if trade.pe_open_units is None else trade.pe_open_units
        if failures or remaining_ce > 0 or remaining_pe > 0:
            trade.phase = TradePhase.PARTIAL_EXIT
            raise PartialFillError(
                f"Exit incomplete; remaining CE={remaining_ce}, PE={remaining_pe} units."
            )

        trade.exit_time = current_time
        trade.exit_reason = reason
        trade.phase = TradePhase.CLOSED

        logger.info(f"Live Execution: Exit both legs complete. PnL: ₹{trade.combined_pnl:.2f}")

    async def execute_hedge_cut(self, trade: Trade, current_time: datetime) -> None:
        losing_leg = trade.losing_leg
        losing_strike = trade.strike_pe if losing_leg == "PE" else trade.strike_ce
        
        full_units = trade.quantity * trade.lot_size
        units = (
            full_units if (trade.ce_open_units if losing_leg == "CE" else trade.pe_open_units) is None
            else (trade.ce_open_units if losing_leg == "CE" else trade.pe_open_units)
        )
        if units <= 0:
            raise PartialFillError(f"{losing_leg} has no open units to hedge-cut.")
        details = self._build_order_details(losing_strike, "CALL" if losing_leg == "CE" else "PUT", units, "SELL")

        loop = asyncio.get_event_loop()
        order_id = await loop.run_in_executor(None, self.client.place_order, details)
        try:
            losing_exit = await self._await_full_fill(order_id, units)
        except PartialOrderFillError as partial:
            if losing_leg == "PE":
                trade.exit_pe_price = partial.average_price
                trade.pe_current_price = partial.average_price
                trade.pe_open_units = max(0, units - partial.filled_qty)
            else:
                trade.exit_ce_price = partial.average_price
                trade.ce_current_price = partial.average_price
                trade.ce_open_units = max(0, units - partial.filled_qty)
            trade.phase = TradePhase.PARTIAL_EXIT
            raise

        entry_price = trade.entry_pe_price if losing_leg == "PE" else trade.entry_ce_price
        losing_leg_pnl = (losing_exit - entry_price) * trade.quantity * trade.lot_size

        trade.hedge_cut_time = current_time
        trade.losing_leg_exit_price = losing_exit
        trade.losing_leg_pnl = round(losing_leg_pnl, 2)

        if losing_leg == "PE":
            trade.exit_pe_price = losing_exit
            trade.pe_current_price = losing_exit
            trade.pe_open_units = 0
        else:
            trade.exit_ce_price = losing_exit
            trade.ce_current_price = losing_exit
            trade.ce_open_units = 0

        trade.phase = TradePhase.PHASE_2_SINGLE_LEG
        logger.info(f"Live Execution: Hedge cut completed for leg {losing_leg}")

    async def execute_single_leg_exit(self, trade: Trade, current_time: datetime, reason: ExitReason) -> None:
        winning_leg = trade.winning_leg
        winning_strike = trade.strike_ce if winning_leg == "CE" else trade.strike_pe

        full_units = trade.quantity * trade.lot_size
        units = (
            full_units if (trade.ce_open_units if winning_leg == "CE" else trade.pe_open_units) is None
            else (trade.ce_open_units if winning_leg == "CE" else trade.pe_open_units)
        )
        if units <= 0:
            raise PartialFillError(f"{winning_leg} has no open units to exit.")
        details = self._build_order_details(winning_strike, "CALL" if winning_leg == "CE" else "PUT", units, "SELL")

        loop = asyncio.get_event_loop()
        order_id = await loop.run_in_executor(None, self.client.place_order, details)
        try:
            winning_exit = await self._await_full_fill(order_id, units)
        except PartialOrderFillError as partial:
            if winning_leg == "CE":
                trade.exit_ce_price = partial.average_price
                trade.ce_current_price = partial.average_price
                trade.ce_open_units = max(0, units - partial.filled_qty)
            else:
                trade.exit_pe_price = partial.average_price
                trade.pe_current_price = partial.average_price
                trade.pe_open_units = max(0, units - partial.filled_qty)
            trade.phase = TradePhase.PARTIAL_EXIT
            raise

        if winning_leg == "CE":
            trade.exit_ce_price = winning_exit
            trade.ce_current_price = winning_exit
            trade.ce_open_units = 0
        else:
            trade.exit_pe_price = winning_exit
            trade.pe_current_price = winning_exit
            trade.pe_open_units = 0

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
        # Retrieve security ID from MarketCache
        sec_id = market_cache.get_security_id(int(strike), "CE" if option_type in ("CALL", "CE") else "PE")
        if not sec_id:
            raise ValueError(f"BrokerExecutor: Security ID mapping missing in MarketCache for {strike} {option_type}.")

        payload = {
            "security_id": str(sec_id),
            "exchange_segment": "NSE_FNO",
            "transaction_type": "BUY" if direction == "BUY" else "SELL",
            "quantity": int(qty),
            "order_type": "LIMIT" if limit_price is not None else "MARKET",
            "product_type": "MARGIN",
            "price": float(limit_price or 0.0)
        }
        return payload
