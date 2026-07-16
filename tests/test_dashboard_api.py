from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from api.app import create_app
from application.diagnostic_capture import DiagnosticCaptureService
from application.runtime_service import RuntimeService
from tests.test_runtime_service import FakeEngine
from config.settings import TradingConfig
from core.enums import MarketRegime, TradeDirection, TradePhase
from core.models import Trade
from database.capital_ledger import CapitalLedger
from database.trade_store import TradeStore


IST = ZoneInfo("Asia/Kolkata")


def trade(*, trade_id: str, when: datetime, pnl_prices: tuple[float, float], phase: TradePhase) -> Trade:
    ce_exit, pe_exit = pnl_prices
    return Trade(
        id=trade_id,
        execution_mode="PAPER",
        index_symbol="BANKNIFTY",
        direction=TradeDirection.LONG_CE,
        strike_ce=24_200,
        strike_pe=24_200,
        entry_ce_price=100.0,
        entry_pe_price=100.0,
        quantity=2,
        lot_size=65,
        entry_time=when - timedelta(minutes=5),
        regime_at_entry=MarketRegime.DIRECTIONAL,
        phase=phase,
        exit_ce_price=ce_exit if phase is TradePhase.CLOSED else None,
        exit_pe_price=pe_exit if phase is TradePhase.CLOSED else None,
        exit_time=when if phase is TradePhase.CLOSED else None,
        hard_stop_loss=900.0,
    )


def client_with_data(tmp_path, *, now: datetime) -> tuple[TestClient, TradeStore, CapitalLedger]:
    store = TradeStore(str(tmp_path / "trades.db"))
    ledger = CapitalLedger(str(tmp_path / "capital.db"))
    app = create_app(
        trade_store=store,
        capital_ledger=ledger,
        config=TradingConfig(total_capital=45_000.0, execution_mode="PAPER"),
        diagnostics=DiagnosticCaptureService(),
        now_provider=lambda: now,
    )
    return TestClient(app), store, ledger


def test_performance_endpoint_is_period_and_mode_scoped(tmp_path):
    now = datetime(2026, 7, 15, 11, 0, tzinfo=IST)
    client, store, _ = client_with_data(tmp_path, now=now)
    store.save_trade(trade(trade_id="yesterday", when=now - timedelta(days=1), pnl_prices=(80, 80), phase=TradePhase.CLOSED))
    store.save_trade(trade(trade_id="today", when=now - timedelta(minutes=1), pnl_prices=(110, 100), phase=TradePhase.CLOSED))

    body = client.get("/api/performance", params={"period": "today", "mode": "PAPER"}).json()

    assert body["period"] == "today"
    assert body["mode"] == "PAPER"
    assert body["realized_pnl"] == store.get_all_trades()[1].net_pnl
    assert body["active_pnl"] == 0.0


def test_active_position_and_journal_expose_lots_units_and_price_freshness(tmp_path):
    now = datetime(2026, 7, 15, 11, 0, tzinfo=IST)
    client, store, _ = client_with_data(tmp_path, now=now)
    store.save_trade(trade(trade_id="open", when=now, pnl_prices=(0, 0), phase=TradePhase.PHASE_1_BOTH_LEGS))

    position = client.get("/api/positions/active", params={"mode": "PAPER"}).json()
    journal = client.get("/api/trades", params={"mode": "PAPER"}).json()

    assert position["trade_id"] == "open"
    assert position["index_symbol"] == "BANKNIFTY"
    assert position["lots"] == 2
    assert position["units_per_leg"] == 130
    assert position["mark_to_market_available"] is False
    assert position["active_pnl"] is None
    assert journal[0]["lots"] == 2
    assert journal[0]["index_symbol"] == "BANKNIFTY"
    assert journal[0]["units_per_leg"] == 130


def test_paper_capital_endpoint_separates_equity_from_ledger_adjustments(tmp_path):
    now = datetime(2026, 7, 15, 11, 0, tzinfo=IST)
    client, store, ledger = client_with_data(tmp_path, now=now)
    closed = trade(trade_id="closed", when=now, pnl_prices=(110, 100), phase=TradePhase.CLOSED)
    store.save_trade(closed)
    ledger.adjust_paper_to_target(45_000.0 + closed.net_pnl, 50_000.0, "Test refill", False, False)

    body = client.get("/api/capital", params={"mode": "PAPER"}).json()

    assert body["base_capital"] == 45_000.0
    assert body["equity"] == 50_000.0
    assert body["cash_adjustments"] == round(5_000.0 - closed.net_pnl, 2)
    assert body["transactions"][0]["note"] == "Test refill"


def test_paper_equity_reconciles_legacy_trade_pnl_ledger_before_refill(tmp_path):
    """A refill target must not add historical losses back as spendable equity."""
    now = datetime(2026, 7, 15, 11, 0, tzinfo=IST)
    client, _, ledger = client_with_data(tmp_path, now=now)
    ledger.record_trade_pnl("PAPER", "legacy-paper-trade", -36_365.35)
    ledger.adjust_paper_to_target(8_634.65, 45_000.0, "Restore PAPER test equity", False, False)

    body = client.get("/api/capital", params={"mode": "PAPER"}).json()

    assert body["realized_pnl"] == -36_365.35
    assert body["cash_adjustments"] == 36_365.35
    assert body["equity"] == 45_000.0


def test_diagnostics_can_start_stop_and_download_without_affecting_trading(tmp_path):
    now = datetime(2026, 7, 15, 11, 0, tzinfo=IST)
    client, _, _ = client_with_data(tmp_path, now=now)

    started = client.post("/api/diagnostics/start", json={"top_count": 5})
    stopped = client.post("/api/diagnostics/stop")
    csv_response = client.get("/api/diagnostics/download", params={"format": "csv"})

    assert started.status_code == 200
    assert started.json()["capturing"] is True
    assert started.json()["top_count"] == 5
    assert stopped.json()["capturing"] is False
    assert csv_response.status_code == 200
    assert csv_response.headers["content-type"].startswith("text/csv")


def test_live_mutation_is_not_exposed_by_dashboard_api(tmp_path):
    now = datetime(2026, 7, 15, 11, 0, tzinfo=IST)
    client, _, _ = client_with_data(tmp_path, now=now)

    assert client.post("/api/capital", json={"amount": 100_000}).status_code == 405


def test_paper_target_adjustment_requires_stopped_engine_and_is_audited(tmp_path):
    now = datetime(2026, 7, 15, 11, 0, tzinfo=IST)
    store = TradeStore(str(tmp_path / "trades.db"))
    ledger = CapitalLedger(str(tmp_path / "capital.db"))
    runtime = RuntimeService(lambda: FakeEngine())
    client = TestClient(create_app(
        trade_store=store,
        capital_ledger=ledger,
        config=TradingConfig(total_capital=45_000.0, execution_mode="PAPER"),
        runtime=runtime,
        now_provider=lambda: now,
    ))

    runtime.start()
    blocked = client.post("/api/capital/paper/target", json={"target_equity": 50_000, "note": "refill"})
    runtime.stop()
    accepted = client.post("/api/capital/paper/target", json={"target_equity": 50_000, "note": "refill"})

    assert blocked.status_code == 409
    assert accepted.status_code == 200
    assert accepted.json()["equity"] == 50_000.0
    assert accepted.json()["transactions"][0]["note"] == "refill"
