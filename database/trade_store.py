"""
Trade Store
────────────
SQLite-backed storage for trade records.
Used by the history page and Excel export.

§12.1 fix: This .py file is tracked in git.
Only the .db data file is gitignored.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Dict
from pathlib import Path

from sqlalchemy import (
    create_engine, Column, Integer, Float, String, DateTime, Boolean,
    text,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from loguru import logger

from config.settings import DATABASE_DIR

Base = declarative_base()
DB_PATH = DATABASE_DIR / "autotrader.db"


class TradeRecord(Base):
    """SQLAlchemy model for a completed trade."""
    __tablename__ = "trades"

    id = Column(String, primary_key=True)
    direction = Column(String, nullable=False)
    strike = Column(Integer, default=0)

    # Entry
    entry_ce_price = Column(Float, nullable=False)
    entry_pe_price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    lot_size = Column(Integer, default=25)
    entry_time = Column(DateTime, nullable=False)
    capital_allocated = Column(Float, default=0.0)

    # Exit
    exit_ce_price = Column(Float)
    exit_pe_price = Column(Float)
    exit_time = Column(DateTime)
    exit_reason = Column(String)

    # Results
    combined_pnl = Column(Float, default=0.0)
    peak_pnl = Column(Float, default=0.0)

    # Metadata
    execution_mode = Column(String, default="BACKTEST")
    created_at = Column(DateTime, default=datetime.utcnow)


class TradeStore:
    """
    Persistent storage for trade records.
    Read/write interface for the database.
    """

    def __init__(self, db_path: Path = None):
        path = db_path or DB_PATH
        path.parent.mkdir(parents=True, exist_ok=True)

        self._engine = create_engine(
            f"sqlite:///{path}",
            echo=False,
            future=True,
        )
        Base.metadata.create_all(self._engine)
        self._Session = sessionmaker(bind=self._engine)

    def save_trade(self, trade) -> None:
        """Save a Trade model to the database."""
        record = TradeRecord(
            id=trade.id,
            direction=trade.direction.value,
            strike=trade.strike,
            entry_ce_price=trade.entry_ce_price,
            entry_pe_price=trade.entry_pe_price,
            quantity=trade.quantity,
            lot_size=trade.lot_size,
            entry_time=trade.entry_time,
            capital_allocated=trade.capital_allocated,
            exit_ce_price=trade.exit_ce_price,
            exit_pe_price=trade.exit_pe_price,
            exit_time=trade.exit_time,
            exit_reason=trade.exit_reason.value if trade.exit_reason else None,
            combined_pnl=trade.combined_pnl,
            peak_pnl=trade.peak_combined_pnl,
        )

        with self._Session() as session:
            # Upsert: merge handles both insert and update
            session.merge(record)
            session.commit()

    def save_trades(self, trades: list) -> None:
        """Batch save multiple trades."""
        for trade in trades:
            self.save_trade(trade)

    def get_all_trades(self) -> List[Dict]:
        """Get all trade records as dicts."""
        with self._Session() as session:
            records = session.query(TradeRecord).order_by(
                TradeRecord.entry_time
            ).all()
            return [self._to_dict(r) for r in records]

    def get_trades_by_date(self, date: datetime) -> List[Dict]:
        """Get trades for a specific date."""
        start = datetime.combine(date, datetime.min.time())
        end = datetime.combine(date, datetime.max.time())

        with self._Session() as session:
            records = session.query(TradeRecord).filter(
                TradeRecord.entry_time.between(start, end)
            ).order_by(TradeRecord.entry_time).all()
            return [self._to_dict(r) for r in records]

    def get_daily_summary(self) -> List[Dict]:
        """Get PnL grouped by date — for history page."""
        with self._Session() as session:
            results = session.execute(text("""
                SELECT
                    date(entry_time) as trade_date,
                    COUNT(*) as trade_count,
                    SUM(combined_pnl) as total_pnl,
                    SUM(CASE WHEN combined_pnl > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN combined_pnl < 0 THEN 1 ELSE 0 END) as losses
                FROM trades
                WHERE exit_time IS NOT NULL
                GROUP BY date(entry_time)
                ORDER BY trade_date DESC
            """)).fetchall()

            return [
                {
                    "date": row[0],
                    "trades": row[1],
                    "pnl": round(row[2] or 0, 2),
                    "wins": row[3],
                    "losses": row[4],
                }
                for row in results
            ]

    def clear_backtest_trades(self) -> None:
        """Remove all backtest-mode trades (preserves paper/live)."""
        with self._Session() as session:
            session.query(TradeRecord).filter(
                TradeRecord.execution_mode == "BACKTEST"
            ).delete()
            session.commit()
            logger.info("Cleared backtest trade records")

    @staticmethod
    def _to_dict(record: TradeRecord) -> Dict:
        return {
            "id": record.id,
            "direction": record.direction,
            "strike": record.strike,
            "entry_ce_price": record.entry_ce_price,
            "entry_pe_price": record.entry_pe_price,
            "quantity": record.quantity,
            "lot_size": record.lot_size,
            "entry_time": record.entry_time,
            "capital_allocated": record.capital_allocated,
            "exit_ce_price": record.exit_ce_price,
            "exit_pe_price": record.exit_pe_price,
            "exit_time": record.exit_time,
            "exit_reason": record.exit_reason,
            "combined_pnl": record.combined_pnl,
            "peak_pnl": record.peak_pnl,
            "execution_mode": record.execution_mode,
        }
