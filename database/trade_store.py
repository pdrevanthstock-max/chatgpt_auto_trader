import logging
from datetime import datetime
from typing import List, Optional
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from config.settings import DATABASE_DIR
from core.models import Trade
from core.enums import TradeDirection, MarketRegime, TradePhase, ExitReason

logger = logging.getLogger("AutoTrader")

Base = declarative_base()

class DBTrade(Base):
    """SQLAlchemy model for trade storage."""
    __tablename__ = "trades"

    id = Column(String(50), primary_key=True)
    direction = Column(String(50), nullable=False)
    strike_ce = Column(Integer, nullable=False)
    strike_pe = Column(Integer, nullable=False)
    entry_ce_price = Column(Float, nullable=False)
    entry_pe_price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    lot_size = Column(Integer, nullable=False)
    entry_time = Column(DateTime, nullable=True)
    regime_at_entry = Column(String(50), nullable=False)
    phase = Column(String(50), nullable=False)
    post_daily_sl = Column(Boolean, default=False, nullable=False)
    risk_capital_at_entry = Column(Float, default=0.0, nullable=False)
    hard_stop_loss = Column(Float, default=0.0, nullable=False)
    ce_open_units = Column(Integer, nullable=True)
    pe_open_units = Column(Integer, nullable=True)
    
    hedge_cut_time = Column(DateTime, nullable=True)
    losing_leg_exit_price = Column(Float, nullable=True)
    losing_leg_pnl = Column(Float, default=0.0)
    
    exit_ce_price = Column(Float, nullable=True)
    exit_pe_price = Column(Float, nullable=True)
    exit_time = Column(DateTime, nullable=True)
    exit_reason = Column(String(50), nullable=True)
    combined_pnl = Column(Float, default=0.0)
    gross_pnl = Column(Float, default=0.0)
    net_pnl = Column(Float, default=0.0)

class TradeStore:
    """Handles SQLite persistence for trades."""
    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path:
            self.db_url = f"sqlite:///{db_path}"
        else:
            self.db_url = f"sqlite:///{DATABASE_DIR / 'autotrader.db'}"

        self.engine = create_engine(self.db_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        
        # Dynamic migration check to add gross_pnl/net_pnl columns to existing database
        try:
            from sqlalchemy import inspect, text
            inspector = inspect(self.engine)
            if "trades" in inspector.get_table_names():
                columns = [c["name"] for c in inspector.get_columns("trades")]
                with self.engine.begin() as conn:
                    if "gross_pnl" not in columns:
                        conn.execute(text("ALTER TABLE trades ADD COLUMN gross_pnl FLOAT DEFAULT 0.0"))
                    if "net_pnl" not in columns:
                        conn.execute(text("ALTER TABLE trades ADD COLUMN net_pnl FLOAT DEFAULT 0.0"))
                    if "post_daily_sl" not in columns:
                        conn.execute(text("ALTER TABLE trades ADD COLUMN post_daily_sl BOOLEAN NOT NULL DEFAULT 0"))
                    if "risk_capital_at_entry" not in columns:
                        conn.execute(text("ALTER TABLE trades ADD COLUMN risk_capital_at_entry FLOAT NOT NULL DEFAULT 0.0"))
                    if "hard_stop_loss" not in columns:
                        conn.execute(text("ALTER TABLE trades ADD COLUMN hard_stop_loss FLOAT NOT NULL DEFAULT 0.0"))
                    if "ce_open_units" not in columns:
                        conn.execute(text("ALTER TABLE trades ADD COLUMN ce_open_units INTEGER"))
                    if "pe_open_units" not in columns:
                        conn.execute(text("ALTER TABLE trades ADD COLUMN pe_open_units INTEGER"))
            logger.info("TradeStore schema migration check successful.")
        except Exception as e:
            logger.warning(f"TradeStore migration check failed (non-blocking): {e}")

        self.Session = sessionmaker(bind=self.engine)
        logger.info(f"TradeStore initialized at {self.db_url}")

    def save_trade(self, trade: Trade) -> None:
        session = self.Session()
        try:
            db_trade = session.query(DBTrade).filter_by(id=trade.id).first()
            if not db_trade:
                db_trade = DBTrade(id=trade.id)
                session.add(db_trade)

            db_trade.direction = trade.direction.value
            db_trade.strike_ce = trade.strike_ce
            db_trade.strike_pe = trade.strike_pe
            db_trade.entry_ce_price = trade.entry_ce_price
            db_trade.entry_pe_price = trade.entry_pe_price
            db_trade.quantity = trade.quantity
            db_trade.lot_size = trade.lot_size
            db_trade.entry_time = trade.entry_time
            db_trade.regime_at_entry = trade.regime_at_entry.value
            db_trade.phase = trade.phase.value
            db_trade.post_daily_sl = bool(getattr(trade, "post_daily_sl", False))
            db_trade.risk_capital_at_entry = trade.risk_capital_at_entry
            db_trade.hard_stop_loss = trade.hard_stop_loss
            db_trade.ce_open_units = trade.ce_open_units
            db_trade.pe_open_units = trade.pe_open_units
            
            db_trade.hedge_cut_time = trade.hedge_cut_time
            db_trade.losing_leg_exit_price = trade.losing_leg_exit_price
            db_trade.losing_leg_pnl = trade.losing_leg_pnl
            
            db_trade.exit_ce_price = trade.exit_ce_price
            db_trade.exit_pe_price = trade.exit_pe_price
            db_trade.exit_time = trade.exit_time
            db_trade.exit_reason = trade.exit_reason.value if trade.exit_reason else None
            db_trade.combined_pnl = trade.combined_pnl
            db_trade.gross_pnl = trade.gross_pnl
            db_trade.net_pnl = trade.net_pnl

            session.commit()
            logger.debug(f"TradeStore: Saved trade {trade.id} to SQLite.")
        except Exception as e:
            session.rollback()
            logger.error(f"TradeStore: Failed to save trade {trade.id}: {e}")
        finally:
            session.close()

    def get_all_trades(self) -> List[Trade]:
        session = self.Session()
        try:
            db_trades = session.query(DBTrade).order_by(DBTrade.entry_time).all()
            trades = []
            for db_t in db_trades:
                trade = Trade(
                    id=db_t.id,
                    direction=TradeDirection(db_t.direction),
                    strike_ce=db_t.strike_ce,
                    strike_pe=db_t.strike_pe,
                    entry_ce_price=db_t.entry_ce_price,
                    entry_pe_price=db_t.entry_pe_price,
                    quantity=db_t.quantity,
                    lot_size=db_t.lot_size,
                    entry_time=db_t.entry_time,
                    regime_at_entry=MarketRegime(db_t.regime_at_entry),
                    phase=TradePhase(db_t.phase),
                    post_daily_sl=bool(getattr(db_t, "post_daily_sl", False)),
                    risk_capital_at_entry=float(getattr(db_t, "risk_capital_at_entry", 0.0) or 0.0),
                    hard_stop_loss=float(getattr(db_t, "hard_stop_loss", 0.0) or 0.0),
                    ce_open_units=getattr(db_t, "ce_open_units", None),
                    pe_open_units=getattr(db_t, "pe_open_units", None),
                    hedge_cut_time=db_t.hedge_cut_time,
                    losing_leg_exit_price=db_t.losing_leg_exit_price,
                    losing_leg_pnl=db_t.losing_leg_pnl,
                    exit_ce_price=db_t.exit_ce_price,
                    exit_pe_price=db_t.exit_pe_price,
                    exit_time=db_t.exit_time,
                    exit_reason=ExitReason(db_t.exit_reason) if db_t.exit_reason else None
                )
                trades.append(trade)
            return trades
        except Exception as e:
            logger.error(f"TradeStore: Failed to retrieve trades: {e}")
            return []
        finally:
            session.close()
