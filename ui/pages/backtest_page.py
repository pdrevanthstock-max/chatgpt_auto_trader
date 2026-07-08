"""
Backtest Page
──────────────
§7.1: "This is the agreed build order."
§9: UI for running backtests and viewing results.

Features:
  - Date range picker
  - Run backtest button
  - Results summary cards
  - Trade journal table
  - Equity curve chart
  - Excel export download
  - Shows which CE/PE pair is being traded (user feedback on Q2)
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

from config.settings import TradingConfig
from data.historical_loader import HistoricalLoader
from data.dhan_client import DhanClient
from backtest.engine import BacktestEngine
from backtest.results import BacktestResults
from reporting.excel_export import ExcelExporter
from database.trade_store import TradeStore


def render_backtest_page(config: TradingConfig):
    """Render the backtest configuration and results page."""

    st.markdown("## 📈 Backtest — Directional Mode")
    st.caption(
        "Replay historical data through the CE/PE divergence strategy. "
        "No real-time API calls, no real orders."
    )

    # ── Date Range ──
    col1, col2, col3 = st.columns([2, 2, 1])

    with col1:
        from_date = st.date_input(
            "From Date",
            value=datetime.now() - timedelta(days=30),
            max_value=datetime.now(),
            help="Start date for historical data fetch.",
        )
    with col2:
        to_date = st.date_input(
            "To Date",
            value=datetime.now() - timedelta(days=1),
            max_value=datetime.now(),
            help="End date for historical data fetch.",
        )
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        run_button = st.button(
            "🚀 Run Backtest",
            use_container_width=True,
            type="primary",
        )

    # ── Parameter Summary ──
    with st.expander("📋 Current Parameters", expanded=False):
        param_col1, param_col2, param_col3 = st.columns(3)
        with param_col1:
            st.metric("Capital", f"₹{config.total_capital:,.0f}")
            st.metric("Divergence Band", f"{config.divergence_min_pct}% – {config.divergence_max_pct}%")
        with param_col2:
            st.metric("Per-Trade Stop", f"{config.per_trade_stop_pct*100:.1f}%")
            st.metric("Trailing Lock", f"{config.trail_lock_factor*100:.0f}%")
        with param_col3:
            st.metric("Daily Loss Limit", f"{config.daily_loss_limit_pct*100:.1f}%")
            st.metric("Candle Interval", f"{config.candle_interval_minutes} min")

    # ── Run Backtest ──
    if run_button:
        _run_backtest(config, str(from_date), str(to_date))

    # ── Display Previous Results ──
    if "backtest_results" in st.session_state:
        _display_results(st.session_state.backtest_results)


def _run_backtest(config: TradingConfig, from_date: str, to_date: str):
    """Execute backtest and store results in session state."""

    progress = st.progress(0, text="Initializing...")

    try:
        # Step 1: Fetch data
        progress.progress(10, text="Fetching historical data from Dhan API...")
        loader = HistoricalLoader()
        day_buckets = loader.fetch_day_buckets(
            from_date=from_date,
            to_date=to_date,
            strike="ATM",
            interval_minutes=config.candle_interval_minutes,
        )

        if not day_buckets:
            st.error("No data returned from Dhan API for the selected date range.")
            progress.empty()
            return

        progress.progress(40, text=f"Loaded {len(day_buckets)} trading days. Running strategy...")

        # Step 2: Run backtest
        engine = BacktestEngine(config)
        results = engine.run(day_buckets)

        progress.progress(80, text="Saving results...")

        # Step 3: Save to database
        store = TradeStore()
        store.clear_backtest_trades()
        store.save_trades(results.closed_trades)

        # Step 4: Store in session
        st.session_state.backtest_results = results

        progress.progress(100, text="Backtest complete!")
        st.success(
            f"✅ Backtest complete: {results.total_trades} trades, "
            f"P&L = ₹{results.total_pnl:,.2f}"
        )

    except Exception as e:
        st.error(f"Backtest failed: {e}")
        import traceback
        st.code(traceback.format_exc())
    finally:
        progress.empty()


def _display_results(results: BacktestResults):
    """Display backtest results with cards, table, and charts."""

    st.divider()
    st.markdown("### 📊 Results")

    # ── Summary Cards ──
    summary = results.summary()
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(
            _metric_card("Total P&L", summary["total_pnl"],
                         "positive" if results.total_pnl >= 0 else "negative"),
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            _metric_card("Win Rate", summary["win_rate"], "neutral"),
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            _metric_card("Total Trades", str(summary["total_trades"]), "neutral"),
            unsafe_allow_html=True,
        )
    with col4:
        st.markdown(
            _metric_card("Max Drawdown", summary["max_drawdown"], "negative"),
            unsafe_allow_html=True,
        )

    # ── Second Row ──
    col5, col6, col7, col8 = st.columns(4)
    with col5:
        st.markdown(
            _metric_card("Avg Profit", summary["avg_profit"], "positive"),
            unsafe_allow_html=True,
        )
    with col6:
        st.markdown(
            _metric_card("Avg Loss", summary["avg_loss"], "negative"),
            unsafe_allow_html=True,
        )
    with col7:
        st.markdown(
            _metric_card("Profit Factor", str(summary["profit_factor"]), "neutral"),
            unsafe_allow_html=True,
        )
    with col8:
        st.markdown(
            _metric_card("Circuit Breaker Days", str(summary["circuit_breaker_days"]), "warning"),
            unsafe_allow_html=True,
        )

    # ── Equity Curve ──
    equity_data = results.equity_curve
    if equity_data:
        st.markdown("### 📈 Equity Curve")
        df_equity = pd.DataFrame(equity_data)
        df_equity["time"] = pd.to_datetime(df_equity["time"])
        st.line_chart(df_equity.set_index("time")["pnl"], use_container_width=True)

    # ── Trade Journal ──
    st.markdown("### 📋 Trade Journal")
    trades = results.closed_trades
    if trades:
        trade_data = []
        for t in trades:
            trade_data.append({
                "ID": t.id,
                "Date": t.entry_time.strftime("%Y-%m-%d") if t.entry_time else "",
                "Direction": t.direction.value,
                "CE/PE Pair": f"CE={t.entry_ce_price:.1f} / PE={t.entry_pe_price:.1f}",
                "Qty": t.quantity,
                "Entry Time": t.entry_time.strftime("%H:%M") if t.entry_time else "",
                "Exit Time": t.exit_time.strftime("%H:%M") if t.exit_time else "",
                "P&L (₹)": t.combined_pnl,
                "Exit Reason": t.exit_reason.value if t.exit_reason else "",
            })

        df_trades = pd.DataFrame(trade_data)
        st.dataframe(
            df_trades,
            use_container_width=True,
            hide_index=True,
            column_config={
                "P&L (₹)": st.column_config.NumberColumn(format="₹%.2f"),
            },
        )
    else:
        st.info("No trades generated in the backtest period.")

    # ── Daily P&L ──
    daily = results.daily_pnl
    if daily:
        st.markdown("### 📅 Daily P&L")
        daily_data = []
        for d in daily:
            daily_data.append({
                "Date": d["date"].strftime("%Y-%m-%d") if d["date"] else "",
                "Trades": d["trades"],
                "P&L (₹)": d["realized_pnl"],
                "Circuit Breaker": "🔴" if d["circuit_breaker"] else "",
            })
        st.dataframe(
            pd.DataFrame(daily_data),
            use_container_width=True,
            hide_index=True,
        )

    # ── Export ──
    st.markdown("### 💾 Export")
    if st.button("📥 Download Excel Report", type="secondary"):
        try:
            filepath = ExcelExporter.export_backtest(results)
            with open(filepath, "rb") as f:
                st.download_button(
                    label="⬇️ Click to Download",
                    data=f.read(),
                    file_name=filepath.name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
        except Exception as e:
            st.error(f"Export failed: {e}")


def _metric_card(label: str, value: str, style: str) -> str:
    """Generate a styled metric card."""
    colors = {
        "positive": ("#1b5e20", "#e8f5e9", "#4caf50"),
        "negative": ("#b71c1c", "#ffebee", "#ef5350"),
        "neutral": ("#1565c0", "#e3f2fd", "#42a5f5"),
        "warning": ("#e65100", "#fff3e0", "#ff9800"),
    }
    text_color, bg_color, accent = colors.get(style, colors["neutral"])

    return f"""
    <div style="
        background: {bg_color};
        border-left: 4px solid {accent};
        padding: 1rem;
        border-radius: 8px;
        margin-bottom: 0.5rem;
    ">
        <p style="color: #666; margin: 0; font-size: 0.8rem; text-transform: uppercase;">{label}</p>
        <p style="color: {text_color}; margin: 0; font-size: 1.4rem; font-weight: 700;">{value}</p>
    </div>
    """
