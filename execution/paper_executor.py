import logging
import math
import time
from datetime import datetime
from numbers import Real
from collections.abc import Callable, Mapping
from core.models import TradePlan, Trade
from core.enums import TradeDirection, ExitReason, TradePhase, OrderType
from data.market_cache import market_cache
from core.exceptions import PartialFillError
from execution.paper_limit_fill import AtomicPaperLimitFill

logger = logging.getLogger("AutoTrader")

class PaperExecutor:
    """
    Simulates paper execution of entry, exit, rotation, and hedge-cut orders
    using prices retrieved from MarketCache.
    """
    def __init__(
        self,
        *,
        chain_provider: Callable[[], Mapping[object, object]] | None = None,
        limit_fill_timeout_seconds: float = 15.0,
        limit_fill_poll_seconds: float = 1.0,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._chain_provider = chain_provider or market_cache.get_option_chain
        self._limit_fill = AtomicPaperLimitFill(
            chain_provider=self._chain_provider,
            timeout_seconds=limit_fill_timeout_seconds,
            poll_seconds=limit_fill_poll_seconds,
            monotonic=monotonic,
            sleep=sleep,
        )

    @staticmethod
    def _executable_price(data: dict | None, field: str, context: str) -> float:
        if not data:
            raise PartialFillError(f"{context} is unavailable: option quote is missing.")

        value = data.get(field)
        if (
            isinstance(value, bool)
            or not isinstance(value, Real)
            or not math.isfinite(float(value))
            or value <= 0.0
        ):
            raise PartialFillError(
                f"{context} is unavailable: {field} must be a finite positive price."
            )
        return float(value)

    def _buy_fill_price(
        self,
        data: dict | None,
        limit_price: float | None,
        leg: str,
    ) -> float:
        ask = self._executable_price(data, "ask", f"{leg} entry ask")
        if limit_price is None:
            return ask

        if (
            isinstance(limit_price, bool)
            or not isinstance(limit_price, Real)
            or not math.isfinite(float(limit_price))
            or limit_price <= 0.0
        ):
            raise PartialFillError(
                f"{leg} buy limit must be a finite positive price."
            )
        if ask > limit_price:
            raise PartialFillError(
                f"{leg} buy limit {limit_price:.2f} is below executable ask {ask:.2f}."
            )
        return ask

    @staticmethod
    def _validated_limit(limit_price: float | None, leg: str) -> float:
        if (
            isinstance(limit_price, bool)
            or not isinstance(limit_price, Real)
            or not math.isfinite(float(limit_price))
            or float(limit_price) <= 0.0
        ):
            raise PartialFillError(
                f"{leg} buy limit must be a finite positive price."
            )
        return float(limit_price)

    def execute_entry(self, plan: TradePlan, current_time: datetime) -> Trade:
        # PAPER market buys cross the spread at the executable ask. A limit
        # entry waits for both asks to reach their limits in one snapshot;
        # timeout creates no Trade and therefore no partial basket.
        if plan.order_type == OrderType.LIMIT:
            if plan.ce_limit_price is None or plan.pe_limit_price is None:
                raise PartialFillError(
                    "PAPER limit entry requires positive limit prices for both legs."
                )
            ce_limit = self._validated_limit(plan.ce_limit_price, "CE")
            pe_limit = self._validated_limit(plan.pe_limit_price, "PE")
            ce_price, pe_price = self._limit_fill.wait(
                ce_strike=plan.scored_candidate.ce_strike,
                pe_strike=plan.scored_candidate.pe_strike,
                ce_limit=ce_limit,
                pe_limit=pe_limit,
            )
        elif plan.order_type == OrderType.MARKET:
            chain = self._chain_provider()
            ce_data = chain.get(plan.scored_candidate.ce_strike, {}).get("CE")
            pe_data = chain.get(plan.scored_candidate.pe_strike, {}).get("PE")
            ce_price = self._buy_fill_price(ce_data, None, "CE")
            pe_price = self._buy_fill_price(pe_data, None, "PE")
        else:
            raise PartialFillError(f"Unsupported PAPER order type: {plan.order_type!r}.")

        # Build Trade Direction
        # Bullish (winning leg CE) -> buy CE + buy PE
        # Bearish (winning leg PE) -> buy PE + buy CE
        direction = TradeDirection.LONG_CE if plan.scored_candidate.winning_leg == "CE" else TradeDirection.LONG_PE

        trade = Trade(
            execution_mode="PAPER",
            index_symbol=plan.index_symbol,
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

        logger.info(
            f"PaperExecutor [ENTRY FILLED]: {trade.display_id} | {plan.scored_candidate.ce_strike}CE @ ₹{ce_price:.2f} "
            f"and {plan.scored_candidate.pe_strike}PE @ ₹{pe_price:.2f}. "
            f"Size: {trade.quantity:,} lots / {trade.units_per_leg:,} units per leg."
        )
        return trade

    def execute_exit_both(self, trade: Trade, current_time: datetime, reason: ExitReason) -> None:
        chain = self._chain_provider()
        ce_data = chain.get(trade.strike_ce, {}).get("CE")
        pe_data = chain.get(trade.strike_pe, {}).get("PE")

        ce_exit = self._executable_price(ce_data, "bid", "CE exit bid")
        pe_exit = self._executable_price(pe_data, "bid", "PE exit bid")

        trade.exit_ce_price = ce_exit
        trade.exit_pe_price = pe_exit
        trade.exit_time = current_time
        trade.exit_reason = reason
        trade.ce_open_units = 0
        trade.pe_open_units = 0
        trade.phase = TradePhase.CLOSED

        logger.info(
            f"PaperExecutor [EXIT BOTH FILLED]: {trade.display_id} | CE exit @ ₹{ce_exit:.2f}, PE exit @ ₹{pe_exit:.2f}. "
            f"PnL: ₹{trade.combined_pnl:.2f}. Reason: {reason.value}."
        )

    def execute_hedge_cut(self, trade: Trade, current_time: datetime) -> None:
        chain = self._chain_provider()
        
        # Losing leg is identified by the losing_leg property of Trade
        losing_leg = trade.losing_leg
        losing_strike = trade.strike_pe if losing_leg == "PE" else trade.strike_ce
        leg_data = chain.get(losing_strike, {}).get(losing_leg)

        losing_exit = self._executable_price(
            leg_data,
            "bid",
            f"{losing_leg} hedge-cut bid",
        )

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
            trade.pe_open_units = 0
        else:
            trade.exit_ce_price = losing_exit
            trade.ce_current_price = losing_exit
            trade.ce_open_units = 0

        trade.phase = TradePhase.PHASE_2_SINGLE_LEG

        logger.info(
            f"PaperExecutor [HEDGE CUT FILLED]: {trade.display_id} | Losing leg {losing_leg} cut @ ₹{losing_exit:.2f}. "
            f"Realized loss: ₹{losing_leg_pnl:.2f}. Winning leg continues open."
        )

    def execute_single_leg_exit(self, trade: Trade, current_time: datetime, reason: ExitReason) -> None:
        chain = self._chain_provider()
        winning_leg = trade.winning_leg
        winning_strike = trade.strike_ce if winning_leg == "CE" else trade.strike_pe
        leg_data = chain.get(winning_strike, {}).get(winning_leg)

        winning_exit = self._executable_price(
            leg_data,
            "bid",
            f"{winning_leg} single-leg exit bid",
        )

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

        logger.info(
            f"PaperExecutor [SINGLE LEG EXIT FILLED]: {trade.display_id} | Winning leg {winning_leg} exit @ ₹{winning_exit:.2f}. "
            f"Final Trade PnL: ₹{trade.combined_pnl:.2f}. Reason: {reason.value}."
        )
