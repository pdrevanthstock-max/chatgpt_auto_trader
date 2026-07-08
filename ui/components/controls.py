"""
Sidebar Controls
──────────────────
§9 requirements:
  - Start/Stop controls
  - Mode selector: Backtest / Paper / Live
  - Capital setting (editable, independent of broker balance)
  - Divergence threshold parameters (visible/editable)
"""

import streamlit as st

from config.settings import TradingConfig


def render_sidebar(config: TradingConfig) -> str:
    """
    Render the sidebar with all controls.
    Returns the selected page name.
    """
    with st.sidebar:
        # ── Navigation ──
        st.markdown("### 🧭 Navigation")
        selected_page = st.radio(
            "Page",
            ["Backtest", "History", "Live View"],
            label_visibility="collapsed",
        )

        st.divider()

        # ── Mode & Status ──
        st.markdown("### ⚡ Execution Mode")

        mode = st.selectbox(
            "Mode",
            ["BACKTEST", "PAPER", "LIVE"],
            index=["BACKTEST", "PAPER", "LIVE"].index(config.execution_mode),
            help="§8: Paper and Live are gated until backtest validates the strategy.",
        )

        if mode != config.execution_mode:
            if mode == "LIVE":
                st.error(
                    "⚠️ Live trading requires explicit confirmation. "
                    "Not available until backtest and paper trading validate the strategy."
                )
            elif mode == "PAPER":
                st.warning("Paper trading: simulated fills on real-time data.")
            config.execution_mode = mode
            config.save()

        st.divider()

        # ── Capital (§6) ──
        st.markdown("### 💰 Capital")
        new_capital = st.number_input(
            "Total Allocated Capital (₹)",
            min_value=1000.0,
            max_value=10_000_000.0,
            value=config.total_capital,
            step=5000.0,
            help="§6: Independent of actual broker account balance. Bot never uses more than this.",
        )
        if new_capital != config.total_capital:
            config.total_capital = new_capital
            config.save()

        # Show derived values
        daily_limit = config.total_capital * config.daily_loss_limit_pct
        st.caption(f"Daily loss limit: ₹{daily_limit:,.0f} ({config.daily_loss_limit_pct*100:.0f}%)")

        st.divider()

        # ── Entry Parameters (§4) ──
        st.markdown("### 🎯 Entry Parameters")

        col1, col2 = st.columns(2)
        with col1:
            new_min = st.number_input(
                "Min Divergence %",
                min_value=0.0,
                max_value=10.0,
                value=config.divergence_min_pct,
                step=0.1,
                format="%.1f",
                help="Lower band: ignore signals below this.",
            )
        with col2:
            new_max = st.number_input(
                "Max Divergence %",
                min_value=0.0,
                max_value=10.0,
                value=config.divergence_max_pct,
                step=0.1,
                format="%.1f",
                help="Upper band: don't chase signals above this.",
            )

        if new_min != config.divergence_min_pct or new_max != config.divergence_max_pct:
            config.divergence_min_pct = new_min
            config.divergence_max_pct = new_max
            config.save()

        st.caption(f"Entry band: {config.divergence_min_pct}% – {config.divergence_max_pct}%")

        candle_interval = st.number_input(
            "Candle Interval (minutes)",
            min_value=1,
            max_value=60,
            value=config.candle_interval_minutes,
            step=1,
            help="Aggregate 1-min candles into N-min for velocity calculation.",
        )
        if candle_interval != config.candle_interval_minutes:
            config.candle_interval_minutes = candle_interval
            config.save()

        st.divider()

        # ── Risk Parameters (§5) ──
        st.markdown("### 🛡️ Risk Management")

        per_trade_stop = st.number_input(
            "Per-Trade Stop (%)",
            min_value=0.1,
            max_value=20.0,
            value=config.per_trade_stop_pct * 100,
            step=0.5,
            format="%.1f",
            help="§5.1: Exit when trade loss exceeds this % of allocated capital.",
        )
        new_stop = per_trade_stop / 100
        if abs(new_stop - config.per_trade_stop_pct) > 0.0001:
            config.per_trade_stop_pct = new_stop
            config.save()

        trail_lock = st.number_input(
            "Trailing Lock-in (%)",
            min_value=10.0,
            max_value=99.0,
            value=config.trail_lock_factor * 100,
            step=5.0,
            format="%.0f",
            help="§2.1: Lock this % of peak profits. E.g., 85% = ₹85 stop on ₹100 profit.",
        )
        new_trail = trail_lock / 100
        if abs(new_trail - config.trail_lock_factor) > 0.0001:
            config.trail_lock_factor = new_trail
            config.save()

        daily_limit_pct = st.number_input(
            "Daily Loss Limit (%)",
            min_value=0.5,
            max_value=20.0,
            value=config.daily_loss_limit_pct * 100,
            step=0.5,
            format="%.1f",
            help="§5.2: Stop all trading when daily loss exceeds this % of capital.",
        )
        new_daily = daily_limit_pct / 100
        if abs(new_daily - config.daily_loss_limit_pct) > 0.0001:
            config.daily_loss_limit_pct = new_daily
            config.save()

        st.divider()

        # ── Trading Window (§3) ──
        st.markdown("### 🕐 Trading Window")
        st.text(f"Start: {config.scan_start} IST")
        st.text(f"End:   {config.scan_end} IST (force-flatten)")

        st.divider()
        st.caption(f"Config auto-saved to config.json")

    return selected_page
