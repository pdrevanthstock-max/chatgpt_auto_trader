import logging
from datetime import datetime
from core.models import TradePlan, Trade, PairedCandle
from core.enums import TradeDirection, ExitReason, TradePhase, OrderType
from core.exceptions import PartialFillError

logger = logging.getLogger("AutoTrader")

class SimulatedFill:
    """
    Simulates entry and exit order fills for backtesting,
    including limit order price checks against high/low ranges.
    """
    def fill_entry(self, plan: TradePlan, candle: PairedCandle) -> Trade:
        # Check limit price touches in backtest
        if plan.order_type == OrderType.LIMIT:
            ce_ok = candle.ce_low <= plan.ce_limit_price <= candle.ce_high
            pe_ok = candle.pe_low <= plan.pe_limit_price <= candle.pe_high
            
            if not ce_ok or not pe_ok:
                raise PartialFillError("Limit prices did not touch the candle high/low range.")
                
            ce_price = plan.ce_limit_price
            pe_price = plan.pe_limit_price
        else:
            # Market order fills at the open price of the N+1 candle
            # (which is the current candle in the replay loop)
            ce_price = candle.ce_open
            pe_price = candle.pe_open

        direction = TradeDirection.LONG_CE if plan.scored_candidate.winning_leg == "CE" else TradeDirection.LONG_PE

        trade = Trade(
            direction=direction,
            strike_ce=plan.scored_candidate.ce_strike,
            strike_pe=plan.scored_candidate.pe_strike,
            entry_ce_price=ce_price,
            entry_pe_price=pe_price,
            quantity=plan.quantity,
            lot_size=plan.lot_size,
            entry_time=candle.timestamp,
            regime_at_entry=plan.regime,
            phase=TradePhase.PHASE_1_BOTH_LEGS,
            ce_current_price=ce_price,
            pe_current_price=pe_price
        )
        return trade

    def fill_exit_both(self, trade: Trade, candle: PairedCandle, reason: ExitReason) -> None:
        # Exit fills at the current candle close (or open if EOD square-off)
        ce_exit = candle.ce_close
        pe_exit = candle.pe_close

        trade.exit_ce_price = ce_exit
        trade.exit_pe_price = pe_exit
        trade.exit_time = candle.timestamp
        trade.exit_reason = reason
        trade.phase = TradePhase.CLOSED

    def fill_hedge_cut(self, trade: Trade, candle: PairedCandle) -> None:
        losing_leg = trade.losing_leg
        losing_exit = candle.pe_close if losing_leg == "PE" else candle.ce_close
        entry_price = trade.entry_pe_price if losing_leg == "PE" else trade.entry_ce_price
        
        losing_leg_pnl = (losing_exit - entry_price) * trade.quantity * trade.lot_size

        trade.hedge_cut_time = candle.timestamp
        trade.losing_leg_exit_price = losing_exit
        trade.losing_leg_pnl = round(losing_leg_pnl, 2)

        if losing_leg == "PE":
            trade.exit_pe_price = losing_exit
            trade.pe_current_price = losing_exit
        else:
            trade.exit_ce_price = losing_exit
            trade.ce_current_price = losing_exit

        trade.phase = TradePhase.PHASE_2_SINGLE_LEG

    def fill_single_leg_exit(self, trade: Trade, candle: PairedCandle, reason: ExitReason) -> None:
        winning_leg = trade.winning_leg
        winning_exit = candle.ce_close if winning_leg == "CE" else candle.pe_close

        if winning_leg == "CE":
            trade.exit_ce_price = winning_exit
            trade.ce_current_price = winning_exit
        else:
            trade.exit_pe_price = winning_exit
            trade.pe_current_price = winning_exit

        trade.exit_time = candle.timestamp
        trade.exit_reason = reason
        trade.phase = TradePhase.CLOSED
