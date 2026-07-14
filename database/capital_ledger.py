from __future__ import annotations

import math
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from config.settings import DATABASE_DIR


class CapitalTransactionType(str, Enum):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    TRADE_PNL = "TRADE_PNL"
    ALLOCATION_CHANGE = "ALLOCATION_CHANGE"
    BROKER_BALANCE_SYNC = "BROKER_BALANCE_SYNC"


@dataclass(frozen=True)
class CapitalTransaction:
    id: str
    timestamp: datetime
    mode: str
    transaction_type: CapitalTransactionType
    amount: float
    note: str
    reference_id: Optional[str] = None
    broker_balance: Optional[float] = None
    allocation_after: Optional[float] = None


class CapitalLedger:
    """Append-only cash-flow and allocation audit ledger."""

    _CASH_TYPES = {
        CapitalTransactionType.DEPOSIT.value,
        CapitalTransactionType.WITHDRAWAL.value,
    }

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = Path(db_path) if db_path else DATABASE_DIR / "capital_ledger.db"
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS capital_transactions (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT NOT NULL UNIQUE,
                    timestamp TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    transaction_type TEXT NOT NULL,
                    amount REAL NOT NULL,
                    note TEXT NOT NULL,
                    reference_id TEXT,
                    broker_balance REAL
                    ,allocation_after REAL
                )
                """
            )
            columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(capital_transactions)"
                ).fetchall()
            }
            if "allocation_after" not in columns:
                connection.execute(
                    "ALTER TABLE capital_transactions ADD COLUMN allocation_after REAL"
                )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS live_daily_stops (
                    trading_day TEXT PRIMARY KEY,
                    triggered_at TEXT NOT NULL,
                    realized_pnl REAL NOT NULL,
                    loss_limit REAL NOT NULL
                )
                """
            )

    @staticmethod
    def _require_finite(value: float, field: str) -> float:
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError(f"{field} must be finite.")
        return round(numeric, 2)

    @staticmethod
    def _require_adjustment_allowed(engine_running: bool, has_open_position: bool) -> None:
        if engine_running or has_open_position:
            raise ValueError(
                "Capital changes require the engine to be stopped and no open position."
            )

    def record(
        self,
        mode: str,
        transaction_type: CapitalTransactionType,
        amount: float,
        note: str,
        reference_id: Optional[str] = None,
        broker_balance: Optional[float] = None,
        allocation_after: Optional[float] = None,
    ) -> CapitalTransaction:
        normalized_mode = str(mode).upper()
        if normalized_mode not in {"PAPER", "LIVE"}:
            raise ValueError("Capital ledger mode must be PAPER or LIVE.")
        normalized_amount = self._require_finite(amount, "amount")
        if (
            normalized_amount == 0.0
            and transaction_type is not CapitalTransactionType.TRADE_PNL
        ):
            raise ValueError("Capital ledger amount cannot be zero.")
        normalized_note = str(note).strip()
        if not normalized_note:
            raise ValueError("Capital ledger note is required.")
        normalized_broker_balance = None
        if broker_balance is not None:
            normalized_broker_balance = self._require_finite(
                broker_balance, "broker_balance"
            )
        normalized_allocation_after = None
        if allocation_after is not None:
            normalized_allocation_after = self._require_finite(
                allocation_after, "allocation_after"
            )

        transaction = CapitalTransaction(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            mode=normalized_mode,
            transaction_type=transaction_type,
            amount=normalized_amount,
            note=normalized_note,
            reference_id=reference_id,
            broker_balance=normalized_broker_balance,
            allocation_after=normalized_allocation_after,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO capital_transactions
                    (id, timestamp, mode, transaction_type, amount, note,
                     reference_id, broker_balance, allocation_after)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transaction.id,
                    transaction.timestamp.isoformat(),
                    transaction.mode,
                    transaction.transaction_type.value,
                    transaction.amount,
                    transaction.note,
                    transaction.reference_id,
                    transaction.broker_balance,
                    transaction.allocation_after,
                ),
            )
        return transaction

    def list_transactions(self, mode: Optional[str] = None) -> list[CapitalTransaction]:
        query = "SELECT * FROM capital_transactions"
        parameters: tuple = ()
        if mode is not None:
            query += " WHERE mode = ?"
            parameters = (str(mode).upper(),)
        query += " ORDER BY sequence"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [
            CapitalTransaction(
                id=row["id"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                mode=row["mode"],
                transaction_type=CapitalTransactionType(row["transaction_type"]),
                amount=float(row["amount"]),
                note=row["note"],
                reference_id=row["reference_id"],
                broker_balance=(
                    float(row["broker_balance"])
                    if row["broker_balance"] is not None
                    else None
                ),
                allocation_after=(
                    float(row["allocation_after"])
                    if row["allocation_after"] is not None
                    else None
                ),
            )
            for row in rows
        ]

    def cash_adjustment_total(self, mode: str) -> float:
        placeholders = ",".join("?" for _ in self._CASH_TYPES)
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT COALESCE(SUM(amount), 0.0) AS total
                FROM capital_transactions
                WHERE mode = ? AND transaction_type IN ({placeholders})
                """,
                (str(mode).upper(), *sorted(self._CASH_TYPES)),
            ).fetchone()
        return round(float(row["total"]), 2)

    def paper_equity(self, base_capital: float, realized_net_pnl: float) -> float:
        base = self._require_finite(base_capital, "base_capital")
        realized = self._require_finite(realized_net_pnl, "realized_net_pnl")
        return max(
            0.0,
            round(base + realized + self.cash_adjustment_total("PAPER"), 2),
        )

    def record_trade_pnl(self, mode: str, trade_id: str, net_pnl: float) -> CapitalTransaction:
        normalized_mode = str(mode).upper()
        for transaction in self.list_transactions(normalized_mode):
            if (
                transaction.transaction_type is CapitalTransactionType.TRADE_PNL
                and transaction.reference_id == trade_id
            ):
                expected = self._require_finite(net_pnl, "net_pnl")
                if transaction.amount != expected:
                    raise ValueError(
                        f"Trade {trade_id} already has a different ledger P&L amount."
                    )
                return transaction
        return self.record(
            mode=normalized_mode,
            transaction_type=CapitalTransactionType.TRADE_PNL,
            amount=net_pnl,
            note=f"Net P&L for trade {trade_id}",
            reference_id=trade_id,
        )

    def adjust_paper_to_target(
        self,
        current_equity: float,
        target_equity: float,
        note: str,
        engine_running: bool,
        has_open_position: bool,
    ) -> CapitalTransaction:
        self._require_adjustment_allowed(engine_running, has_open_position)
        current = self._require_finite(current_equity, "current_equity")
        target = self._require_finite(target_equity, "target_equity")
        if target < 0.0:
            raise ValueError("PAPER target equity cannot be negative.")
        adjustment = round(target - current, 2)
        transaction_type = (
            CapitalTransactionType.DEPOSIT
            if adjustment > 0.0
            else CapitalTransactionType.WITHDRAWAL
        )
        return self.record("PAPER", transaction_type, adjustment, note)

    def set_live_allocation(
        self,
        previous_allocation: float,
        new_allocation: float,
        broker_available_funds: float,
        note: str,
        engine_running: bool,
        has_open_position: bool,
    ) -> CapitalTransaction:
        self._require_adjustment_allowed(engine_running, has_open_position)
        previous = self._require_finite(previous_allocation, "previous_allocation")
        new = self._require_finite(new_allocation, "new_allocation")
        broker_funds = self._require_finite(
            broker_available_funds, "broker_available_funds"
        )
        if new <= 0.0:
            raise ValueError("LIVE allocation must be positive.")
        if new > broker_funds:
            raise ValueError(
                "LIVE allocation cannot exceed broker-confirmed available funds."
            )
        return self.record(
            mode="LIVE",
            transaction_type=CapitalTransactionType.ALLOCATION_CHANGE,
            amount=round(new - previous, 2),
            note=note,
            broker_balance=broker_funds,
            allocation_after=new,
        )

    def latest_live_allocation(self) -> float:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT allocation_after
                FROM capital_transactions
                WHERE mode = 'LIVE' AND transaction_type = ?
                  AND allocation_after IS NOT NULL
                ORDER BY sequence DESC
                LIMIT 1
                """,
                (CapitalTransactionType.ALLOCATION_CHANGE.value,),
            ).fetchone()
        return round(float(row["allocation_after"]), 2) if row is not None else 0.0

    def latch_live_daily_stop(
        self,
        trading_day: date,
        realized_pnl: float,
        loss_limit: float,
    ) -> None:
        """Persist a same-day LIVE stop; allocation changes cannot clear this latch."""
        normalized_pnl = self._require_finite(realized_pnl, "realized_pnl")
        normalized_limit = self._require_finite(loss_limit, "loss_limit")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO live_daily_stops
                    (trading_day, triggered_at, realized_pnl, loss_limit)
                VALUES (?, ?, ?, ?)
                """,
                (
                    trading_day.isoformat(),
                    datetime.now().isoformat(),
                    normalized_pnl,
                    normalized_limit,
                ),
            )

    def is_live_daily_stop_active(self, trading_day: date) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM live_daily_stops WHERE trading_day = ?",
                (trading_day.isoformat(),),
            ).fetchone()
        return row is not None
