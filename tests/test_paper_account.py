from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from application.paper_account import PaperAccountService
from config.settings import TradingConfig
from core.enums import MarketRegime, TradeDirection, TradePhase
from core.models import Trade
from database.capital_ledger import CapitalLedger
from database.trade_store import TradeStore


IST = ZoneInfo("Asia/Kolkata")


def _closed_trade(trade_id: str, closed_at: datetime, net_points: float) -> Trade:
    return Trade(
        id=trade_id,
        execution_mode="PAPER",
        index_symbol="NIFTY",
        direction=TradeDirection.LONG_CE,
        strike_ce=24_000,
        strike_pe=24_200,
        entry_ce_price=100.0,
        entry_pe_price=100.0,
        quantity=1,
        lot_size=65,
        entry_time=closed_at - timedelta(minutes=5),
        regime_at_entry=MarketRegime.SIDEWAYS,
        phase=TradePhase.CLOSED,
        exit_ce_price=100.0 + net_points,
        exit_pe_price=100.0,
        exit_time=closed_at,
    )


def test_account_keeps_legacy_loss_when_refill_deposits_are_present(tmp_path):
    ledger = CapitalLedger(str(tmp_path / "capital.db"))
    ledger.adjust_paper_to_target(
        current_equity=8_634.65,
        target_equity=45_000.0,
        note="Restore PAPER test equity",
        engine_running=False,
        has_open_position=False,
    )
    service = PaperAccountService(
        config=TradingConfig(total_capital=45_000.0),
        capital_ledger=ledger,
        trade_store=TradeStore(str(tmp_path / "trades.db")),
        now_provider=lambda: datetime(2026, 7, 21, 12, 0, tzinfo=IST),
    )

    snapshot = service.snapshot(lifetime_realized_pnl=-37_987.09)

    assert snapshot.available_equity == 43_378.26
    assert snapshot.lifetime_realized_pnl == -37_987.09
    assert snapshot.cash_adjustments == 36_365.35


def test_account_reports_today_and_month_without_changing_lifetime_equity(tmp_path):
    now = datetime(2026, 7, 21, 12, 0, tzinfo=IST)
    store = TradeStore(str(tmp_path / "trades.db"))
    today = _closed_trade("today", now - timedelta(minutes=10), 2.0)
    earlier = _closed_trade("earlier", now - timedelta(days=4), -1.0)
    store.save_trade(today)
    store.save_trade(earlier)
    service = PaperAccountService(
        config=TradingConfig(total_capital=45_000.0),
        capital_ledger=CapitalLedger(str(tmp_path / "capital.db")),
        trade_store=store,
        now_provider=lambda: now,
    )

    snapshot = service.snapshot(lifetime_realized_pnl=-500.0)

    assert snapshot.today_realized_pnl == today.net_pnl
    assert snapshot.month_realized_pnl == round(today.net_pnl + earlier.net_pnl, 2)
    assert snapshot.available_equity == 44_500.0


def test_durable_legacy_loss_prevents_zero_recovery_from_inflating_equity(tmp_path):
    now = datetime(2026, 7, 21, 12, 0, tzinfo=IST)
    store = TradeStore(str(tmp_path / "trades.db"))
    legacy = _closed_trade("legacy-loss", now - timedelta(days=7), -10.0)
    legacy.execution_mode = "UNKNOWN"
    store.save_trade(legacy)
    service = PaperAccountService(
        config=TradingConfig(total_capital=45_000.0),
        capital_ledger=CapitalLedger(str(tmp_path / "capital.db")),
        trade_store=store,
        now_provider=lambda: now,
    )

    snapshot = service.snapshot(lifetime_realized_pnl=0.0)

    assert snapshot.lifetime_realized_pnl == round(legacy.net_pnl, 2)
    assert snapshot.available_equity == round(45_000.0 + legacy.net_pnl, 2)
