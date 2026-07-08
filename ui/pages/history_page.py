"""
History Page
──────────────
§9: "Historical view: PnL by past day (not just today)."

Displays daily P&L from the SQLite database.
"""

import streamlit as st
import pandas as pd

from config.settings import TradingConfig
from database.trade_store import TradeStore


def render_history_page(config: TradingConfig):
    """Render the historical P&L view."""

    st.markdown("## 📆 Trade History")
    st.caption("P&L by past trading day — all trades stored in database.")

    store = TradeStore()

    # ── Daily Summary ──
    daily = store.get_daily_summary()

    if not daily:
        st.info(
            "No trade history yet. Run a backtest first to generate trades."
        )
        return

    # Summary metrics
    total_pnl = sum(d["pnl"] for d in daily)
    total_trades = sum(d["trades"] for d in daily)
    total_wins = sum(d["wins"] for d in daily)
    total_losses = sum(d["losses"] for d in daily)
    win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total P&L", f"₹{total_pnl:,.2f}")
    col2.metric("Total Trades", total_trades)
    col3.metric("Win Rate", f"{win_rate:.1f}%")
    col4.metric("Trading Days", len(daily))

    st.divider()

    # ── Daily P&L Table ──
    df = pd.DataFrame(daily)
    df["win_rate"] = df.apply(
        lambda r: f"{r['wins']/(r['wins']+r['losses'])*100:.0f}%"
        if (r["wins"] + r["losses"]) > 0 else "—",
        axis=1,
    )

    st.dataframe(
        df[["date", "trades", "pnl", "wins", "losses", "win_rate"]].rename(
            columns={
                "date": "Date",
                "trades": "Trades",
                "pnl": "P&L (₹)",
                "wins": "Wins",
                "losses": "Losses",
                "win_rate": "Win Rate",
            }
        ),
        use_container_width=True,
        hide_index=True,
        column_config={
            "P&L (₹)": st.column_config.NumberColumn(format="₹%.2f"),
        },
    )

    # ── P&L Bar Chart ──
    if len(df) > 1:
        st.markdown("### 📊 Daily P&L Distribution")
        chart_df = df[["date", "pnl"]].copy()
        chart_df["date"] = pd.to_datetime(chart_df["date"])
        chart_df = chart_df.set_index("date").sort_index()
        st.bar_chart(chart_df["pnl"], use_container_width=True)

    # ── Detailed Trade Lookup ──
    st.divider()
    st.markdown("### 🔍 Trade Details by Date")

    selected_date = st.selectbox(
        "Select a date",
        options=[d["date"] for d in daily],
        format_func=lambda x: x,
    )

    if selected_date:
        from datetime import datetime
        date_obj = datetime.strptime(selected_date, "%Y-%m-%d")
        trades = store.get_trades_by_date(date_obj)

        if trades:
            trade_df = pd.DataFrame(trades)
            display_cols = [
                "id", "direction", "entry_ce_price", "entry_pe_price",
                "exit_ce_price", "exit_pe_price", "quantity",
                "combined_pnl", "exit_reason",
            ]
            available = [c for c in display_cols if c in trade_df.columns]
            st.dataframe(
                trade_df[available].rename(columns={
                    "id": "Trade ID",
                    "direction": "Direction",
                    "entry_ce_price": "Entry CE",
                    "entry_pe_price": "Entry PE",
                    "exit_ce_price": "Exit CE",
                    "exit_pe_price": "Exit PE",
                    "quantity": "Qty",
                    "combined_pnl": "P&L (₹)",
                    "exit_reason": "Exit Reason",
                }),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No trades found for this date.")
