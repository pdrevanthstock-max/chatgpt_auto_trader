from pathlib import Path


def test_live_cards_and_journal_show_lots_and_units_per_leg():
    app_source = (Path(__file__).parents[1] / "ui" / "app.py").read_text(
        encoding="utf-8"
    )

    assert "{active_trade.quantity:,} lots" in app_source
    assert "{units_per_leg(active_trade):,} units/leg" in app_source
    assert '"Lots": t.quantity' in app_source
    assert '"Units / Leg": units_per_leg(t)' in app_source


def test_streamlit_reruns_reuse_engine_store_and_health_monitor():
    app_source = (Path(__file__).parents[1] / "ui" / "app.py").read_text(
        encoding="utf-8"
    )

    assert app_source.count("TradeStore()") == 1
    assert app_source.count("HealthMonitor()") == 1


def test_ui_exposes_audited_paper_refill_and_read_only_live_allocation_controls():
    app_source = (Path(__file__).parents[1] / "ui" / "app.py").read_text(
        encoding="utf-8"
    )

    assert '"Target PAPER Equity (₹)"' in app_source
    assert "adjust_paper_to_target(" in app_source
    assert '"Refresh Dhan Funds (Read Only)"' in app_source
    assert "set_live_allocation(" in app_source
    assert "engine_running=engine_inst.running" in app_source
    assert "has_open_position=has_open_position" in app_source


def test_trade_journal_displays_capital_transactions_separately_from_trading_pnl():
    app_source = (Path(__file__).parents[1] / "ui" / "app.py").read_text(
        encoding="utf-8"
    )

    assert 'st.subheader("Capital Transaction Ledger")' in app_source
    assert "capital_ledger.list_transactions()" in app_source


def test_live_view_and_daily_breaker_use_date_scoped_performance_service():
    app_source = Path("ui/app.py").read_text(encoding="utf-8")

    assert "from application.performance_service import" in app_source
    assert "daily_risk_pnl = daily_performance.daily_risk_pnl" in app_source
    assert "daily_risk_pnl, self.config" in app_source
    assert "total_pnl = selected_performance.realized_pnl" in app_source
    assert '"Transaction Type": transaction.transaction_type.value' in app_source
    assert '"Allocation After (₹)": transaction.allocation_after' in app_source


def test_live_engine_persists_and_honors_same_day_daily_stop_latch():
    app_source = (Path(__file__).parents[1] / "ui" / "app.py").read_text(
        encoding="utf-8"
    )

    assert "is_live_daily_stop_active(date.today())" in app_source
    assert "latch_live_daily_stop(" in app_source
    assert "LIVE ENTRY BLOCKED: daily loss stop is latched for today" in app_source
    assert "self.realized_pnl, None, execution_mode=execution_mode" in app_source
