from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from application.performance_service import PerformancePeriod, PerformanceService
from core.enums import MarketRegime, TradeDirection, TradePhase
from core.models import Trade
from database.trade_store import TradeStore


IST = ZoneInfo("Asia/Kolkata")


def closed_trade(*, when: datetime, pnl: float, mode: str = "PAPER"):
    return SimpleNamespace(exit_time=when, net_pnl=pnl, execution_mode=mode)


def test_today_excludes_yesterdays_loss_and_keeps_active_pnl_separate():
    now = datetime(2026, 7, 15, 11, 0, tzinfo=IST)
    trades = [
        closed_trade(when=now - timedelta(days=1), pnl=-36_365.35),
        closed_trade(when=now - timedelta(minutes=10), pnl=250.0),
    ]
    result = PerformanceService.calculate(
        trades, "PAPER", PerformancePeriod.TODAY, now, active_pnl=-50.0
    )
    assert result.realized_pnl == 250.0
    assert result.active_pnl == -50.0
    assert result.total_pnl == 200.0
    assert result.daily_risk_pnl == 200.0


def test_mode_filter_never_combines_paper_and_live():
    now = datetime(2026, 7, 15, 11, 0, tzinfo=IST)
    trades = [
        closed_trade(when=now, pnl=300.0, mode="PAPER"),
        closed_trade(when=now, pnl=-900.0, mode="LIVE"),
        closed_trade(when=now, pnl=5_000.0, mode="UNKNOWN"),
    ]
    paper = PerformanceService.calculate(
        trades, "PAPER", PerformancePeriod.TODAY, now, active_pnl=0.0
    )
    live = PerformanceService.calculate(
        trades, "LIVE", PerformancePeriod.TODAY, now, active_pnl=0.0
    )
    assert paper.realized_pnl == 300.0
    assert live.realized_pnl == -900.0


def test_period_boundaries_use_ist_calendar():
    now = datetime(2026, 7, 15, 11, 0, tzinfo=IST)
    trades = [
        closed_trade(when=datetime(2026, 7, 15, 9, 45), pnl=10.0),
        closed_trade(when=datetime(2026, 7, 13, 9, 45), pnl=20.0),
        closed_trade(when=datetime(2026, 7, 1, 9, 45), pnl=30.0),
        closed_trade(when=datetime(2026, 1, 2, 9, 45), pnl=40.0),
        closed_trade(when=datetime(2025, 12, 31, 9, 45), pnl=50.0),
    ]
    assert PerformanceService.calculate(
        trades, "PAPER", PerformancePeriod.TODAY, now, 0.0
    ).realized_pnl == 10.0
    assert PerformanceService.calculate(
        trades, "PAPER", PerformancePeriod.WEEK, now, 0.0
    ).realized_pnl == 30.0
    assert PerformanceService.calculate(
        trades, "PAPER", PerformancePeriod.MONTH, now, 0.0
    ).realized_pnl == 60.0
    assert PerformanceService.calculate(
        trades, "PAPER", PerformancePeriod.YEAR, now, 0.0
    ).realized_pnl == 100.0
    assert PerformanceService.calculate(
        trades, "PAPER", PerformancePeriod.ALL_TIME, now, 0.0
    ).realized_pnl == 150.0


def test_open_trade_without_exit_time_is_not_realized():
    now = datetime(2026, 7, 15, 11, 0, tzinfo=IST)
    open_trade = SimpleNamespace(
        exit_time=None, net_pnl=-99_999.0, execution_mode="PAPER"
    )
    result = PerformanceService.calculate(
        [open_trade], "PAPER", PerformancePeriod.ALL_TIME, now, active_pnl=-125.0
    )
    assert result.realized_pnl == 0.0
    assert result.active_pnl == -125.0


def test_execution_mode_round_trips_through_trade_store(tmp_path):
    store = TradeStore(str(tmp_path / "trades.db"))
    trade = Trade(
        id="paper-mode",
        execution_mode="PAPER",
        direction=TradeDirection.LONG_CE,
        strike_ce=24_200,
        strike_pe=24_200,
        entry_ce_price=100.0,
        entry_pe_price=100.0,
        quantity=1,
        lot_size=65,
        entry_time=datetime(2026, 7, 15, 10, 0),
        regime_at_entry=MarketRegime.DIRECTIONAL,
        phase=TradePhase.CLOSED,
        exit_ce_price=105.0,
        exit_pe_price=98.0,
        exit_time=datetime(2026, 7, 15, 10, 5),
    )
    store.save_trade(trade)

    loaded = store.get_all_trades()[0]

    assert loaded.execution_mode == "PAPER"
