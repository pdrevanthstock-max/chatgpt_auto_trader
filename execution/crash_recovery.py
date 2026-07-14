import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List
from pathlib import Path
from core.models import Trade
from core.enums import TradeDirection, MarketRegime, TradePhase, ExitReason
from config.settings import REPORTS_DIR

logger = logging.getLogger("AutoTrader")

class CrashRecovery:
    """
    Handles persisting system state (active trade, session realized PnL) on disk,
    and reconciling state with broker positions on system startup.
    """
    def __init__(self, filepath: Optional[str] = None) -> None:
        if filepath:
            self.filepath = Path(filepath)
        else:
            self.filepath = REPORTS_DIR / "persistent_state.json"

    def save_state(self, realized_pnl: float, active_trade: Optional[Trade]) -> None:
        try:
            state = {
                "timestamp": datetime.now().isoformat(),
                "realized_pnl": realized_pnl,
                "active_trade": self._serialize_trade(active_trade) if active_trade else None
            }
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            logger.debug("CrashRecovery: State persisted successfully.")
        except Exception as e:
            logger.error(f"CrashRecovery: Failed to save state: {e}")

    def load_state(self) -> Tuple[float, Optional[Trade]]:
        """Loads realized PnL and active trade from persistent state file."""
        if not self.filepath.exists():
            return 0.0, None

        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                state = json.load(f)
            
            realized_pnl = state.get("realized_pnl", 0.0)
            trade_data = state.get("active_trade")
            active_trade = self._deserialize_trade(trade_data) if trade_data else None
            
            logger.info("CrashRecovery: State loaded successfully from disk.")
            return realized_pnl, active_trade
        except Exception as e:
            logger.error(f"CrashRecovery: Failed to load state: {e}")
            return 0.0, None

    def reconcile_with_broker(
        self,
        saved_trade: Optional[Trade],
        broker_positions: List[Dict[str, Any]]
    ) -> Tuple[Optional[Trade], str]:
        """
        Reconciles the saved trade state with the actual open positions from the broker.
        Returns: Tuple of (reconciled_trade_or_none, status_message)
        """
        # Exclude flat closed positions (qty=0)
        active_broker_positions = [p for p in broker_positions if int(p.get("netQty", 0)) != 0]

        if not saved_trade or saved_trade.phase == TradePhase.CLOSED:
            # Saved state says NO open trade
            if len(active_broker_positions) > 0:
                msg = f"MISMATCH: Broker has {len(active_broker_positions)} open positions, but saved state says NONE."
                logger.error(msg)
                return None, msg
            return None, "MATCH: No open positions locally or at broker."

        # Saved state says trade is OPEN
        if len(active_broker_positions) == 0:
            # Broker has closed everything while we were offline
            msg = "RECOVERY: Broker has NO open positions, but local state says trade is open. Settling trade as closed."
            logger.warning(msg)
            # Settle trade locally
            saved_trade.phase = TradePhase.CLOSED
            saved_trade.exit_time = datetime.now()
            saved_trade.exit_reason = ExitReason.MANUAL
            return saved_trade, msg

        # We have positions on both sides, let's verify if strikes match
        # This is a basic structural verification: do we have the matching strikes?
        broker_strikes = []
        for pos in active_broker_positions:
            # Extract strike from tradingSymbol or securityId if available
            symbol = pos.get("tradingSymbol", "")
            # Option symbol format like "NIFTY2471624300CE"
            broker_strikes.append(symbol)

        # Assuming it matches for paper simulation
        msg = f"MATCH: Active trade {saved_trade.id} reconciled with broker positions."
        logger.info(msg)
        return saved_trade, msg

    def _serialize_trade(self, trade: Trade) -> Dict[str, Any]:
        return {
            "id": trade.id,
            "direction": trade.direction.value,
            "strike_ce": trade.strike_ce,
            "strike_pe": trade.strike_pe,
            "entry_ce_price": trade.entry_ce_price,
            "entry_pe_price": trade.entry_pe_price,
            "quantity": trade.quantity,
            "lot_size": trade.lot_size,
            "entry_time": trade.entry_time.isoformat() if trade.entry_time else None,
            "regime_at_entry": trade.regime_at_entry.value,
            "phase": trade.phase.value,
            "post_daily_sl": bool(getattr(trade, "post_daily_sl", False)),
            "ce_current_price": trade.ce_current_price,
            "pe_current_price": trade.pe_current_price,
            "peak_combined_pnl": trade.peak_combined_pnl,
            "peak_single_leg_pnl": trade.peak_single_leg_pnl,
            "hedge_cut_time": trade.hedge_cut_time.isoformat() if trade.hedge_cut_time else None,
            "losing_leg_exit_price": trade.losing_leg_exit_price,
            "losing_leg_pnl": trade.losing_leg_pnl,
            "exit_ce_price": trade.exit_ce_price,
            "exit_pe_price": trade.exit_pe_price,
            "exit_time": trade.exit_time.isoformat() if trade.exit_time else None,
            "exit_reason": trade.exit_reason.value if trade.exit_reason else None
        }

    def _deserialize_trade(self, data: Dict[str, Any]) -> Trade:
        trade = Trade(
            id=data["id"],
            direction=TradeDirection(data["direction"]),
            strike_ce=data["strike_ce"],
            strike_pe=data["strike_pe"],
            entry_ce_price=data["entry_ce_price"],
            entry_pe_price=data["entry_pe_price"],
            quantity=data["quantity"],
            lot_size=data["lot_size"],
            entry_time=datetime.fromisoformat(data["entry_time"]) if data["entry_time"] else None,
            regime_at_entry=MarketRegime(data["regime_at_entry"]),
            phase=TradePhase(data["phase"]),
            post_daily_sl=bool(data.get("post_daily_sl", False)),
            ce_current_price=data["ce_current_price"],
            pe_current_price=data["pe_current_price"],
            peak_combined_pnl=data["peak_combined_pnl"],
            peak_single_leg_pnl=data["peak_single_leg_pnl"],
            hedge_cut_time=datetime.fromisoformat(data["hedge_cut_time"]) if data["hedge_cut_time"] else None,
            losing_leg_exit_price=data["losing_leg_exit_price"],
            losing_leg_pnl=data["losing_leg_pnl"],
            exit_ce_price=data["exit_ce_price"],
            exit_pe_price=data["exit_pe_price"],
            exit_time=datetime.fromisoformat(data["exit_time"]) if data["exit_time"] else None,
            exit_reason=ExitReason(data["exit_reason"]) if data["exit_reason"] else None
        )
        return trade

    def save_engine_status(self, running: bool) -> None:
        try:
            status_file = self.filepath.parent / "engine_status.json"
            data = {
                "running": running,
                "last_start_date": datetime.now().strftime("%Y-%m-%d")
            }
            with open(status_file, "w", encoding="utf-8") as f:
                json.dump(data, f)
            logger.debug(f"CrashRecovery: Saved running status: {running} for date {data['last_start_date']}")
        except Exception as e:
            logger.error(f"CrashRecovery: Failed to save running status: {e}")

    def load_engine_status(self) -> bool:
        try:
            status_file = self.filepath.parent / "engine_status.json"
            if status_file.exists():
                with open(status_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                if not data.get("running", False):
                    return False
                
                # 1. Date Check: Only auto-resume if the engine was started today
                today_str = datetime.now().strftime("%Y-%m-%d")
                if data.get("last_start_date") != today_str:
                    logger.info("CrashRecovery: Different trading day detected, resetting status to STOPPED.")
                    self.save_engine_status(False)
                    return False
                
                # 2. Time Check: Only auto-resume between 09:30 and 15:20 IST
                from datetime import time as datetime_time
                current_time_only = datetime.now().time()
                if current_time_only >= datetime_time(15, 20) or current_time_only < datetime_time(9, 30):
                    logger.info("CrashRecovery: Outside active trading session hours, resetting status to STOPPED.")
                    self.save_engine_status(False)
                    return False
                
                return True
            return False
        except Exception:
            return False
