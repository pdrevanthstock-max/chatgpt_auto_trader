import os
import json
import logging
from datetime import datetime
from typing import Optional
from config.settings import REPORTS_DIR
from core.models import Trade, TradePlan

logger = logging.getLogger("AutoTrader")

class DecisionMemory:
    """
    Durable audit trail that logs every entry, exit, rotation, and hedge-cut decision.
    Writes to reports/decision_memory.jsonl in JSON Lines format.
    """
    def __init__(self, filepath: Optional[str] = None) -> None:
        if filepath:
            self.filepath = filepath
        else:
            self.filepath = str(REPORTS_DIR / "decision_memory.jsonl")

    def _append_log(self, record: dict) -> None:
        try:
            record["timestamp"] = datetime.now().isoformat()
            with open(self.filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Failed to write to decision memory: {e}")

    def log_entry(self, trade_id: str, plan: TradePlan) -> None:
        record = {
            "event": "ENTRY",
            "trade_id": trade_id,
            "display_trade_id": f"{trade_id}-SL" if plan.post_daily_sl else trade_id,
            "post_daily_sl": plan.post_daily_sl,
            "pair": f"{plan.scored_candidate.ce_strike}CE-{plan.scored_candidate.pe_strike}PE",
            "score": plan.scored_candidate.projected_net_profit,
            "confidence": plan.scored_candidate.confidence,
            "regime": plan.regime.value,
            "order_type": plan.order_type.value,
            "quantity": plan.quantity,
            "reasons_selected": [
                "highest_projected_profit",
                f"divergence_{plan.scored_candidate.divergence:.2f}%",
                "liquidity_verified"
            ]
        }
        self._append_log(record)
        logger.info(f"DecisionMemory logged ENTRY for trade {trade_id}")

    def log_exit(self, trade_id: str, trade: Trade, reason: str) -> None:
        record = {
            "event": "EXIT",
            "trade_id": trade_id,
            "display_trade_id": getattr(trade, "display_id", trade_id),
            "post_daily_sl": bool(getattr(trade, "post_daily_sl", False)),
            "reason": reason,
            "ce_entry": trade.entry_ce_price,
            "pe_entry": trade.entry_pe_price,
            "ce_exit": trade.exit_ce_price,
            "pe_exit": trade.exit_pe_price,
            "pnl": trade.combined_pnl,
            "duration_sec": (trade.exit_time - trade.entry_time).total_seconds() if trade.exit_time and trade.entry_time else 0
        }
        self._append_log(record)
        logger.info(f"DecisionMemory logged EXIT for trade {trade_id} (Reason: {reason})")

    def log_hedge_cut(self, trade_id: str, losing_leg: str, fill_price: float, losing_leg_pnl: float) -> None:
        record = {
            "event": "HEDGE_CUT",
            "trade_id": trade_id,
            "losing_leg": losing_leg,
            "exit_price": fill_price,
            "losing_leg_pnl": losing_leg_pnl,
            "phase_transition": "PHASE_1_BOTH_LEGS -> PHASE_2_SINGLE_LEG"
        }
        self._append_log(record)
        logger.info(f"DecisionMemory logged HEDGE_CUT for trade {trade_id} (Leg: {losing_leg})")

    def log_rotation(self, old_trade_id: str, old_pnl: float, new_plan: TradePlan, reason: str) -> None:
        record = {
            "event": "ROTATION",
            "old_trade_id": old_trade_id,
            "old_pnl": old_pnl,
            "new_pair": f"{new_plan.scored_candidate.ce_strike}CE-{new_plan.scored_candidate.pe_strike}PE",
            "new_score": new_plan.scored_candidate.projected_net_profit,
            "reason": reason
        }
        self._append_log(record)
        logger.info(f"DecisionMemory logged ROTATION from {old_trade_id} to new pair (Reason: {reason})")

    def log_error(self, message: str, context: dict) -> None:
        record = {
            "event": "ERROR",
            "message": message,
            "context": context
        }
        self._append_log(record)
        logger.error(f"DecisionMemory logged ERROR: {message}")
