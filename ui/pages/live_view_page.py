"""
Live View Page
────────────────
§8: "Must require a deliberate, explicit switch — never a default state."
§13: "Live trading — not until backtest and paper trading both validate."

This page is gated for v1. Shows a clear message explaining why.
Structural placeholder for future paper/live mode.
"""

import streamlit as st

from config.settings import TradingConfig


def render_live_view_page(config: TradingConfig):
    """Render the live/paper trading view (gated for v1)."""

    st.markdown("## 🔴 Live View")

    if config.execution_mode == "BACKTEST":
        st.markdown(
            """
            <div style="
                background: linear-gradient(135deg, #1a1a2e, #16213e);
                padding: 2rem;
                border-radius: 12px;
                border: 1px solid rgba(255,255,255,0.1);
                text-align: center;
            ">
                <h2 style="color: #ff9800; margin-bottom: 1rem;">🔒 Not Available Yet</h2>
                <p style="color: #b0bec5; font-size: 1.1rem; max-width: 600px; margin: 0 auto;">
                    Live and Paper trading are <strong>gated</strong> until the backtest
                    validates the divergence strategy on real historical data.
                </p>
                <br>
                <p style="color: #78909c; font-size: 0.9rem;">
                    §7.1: "Do not go to paper or live trading until a backtest has run
                    against real historical data and the divergence idea shows something
                    worth trading."
                </p>
                <br>
                <p style="color: #4fc3f7; font-size: 1rem;">
                    ➡️ Go to the <strong>Backtest</strong> page to run your first test.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # ── Future: Paper / Live Mode ──
    st.warning(
        f"Mode: **{config.execution_mode}** — "
        "Paper/Live trading implementation pending. "
        "This will show real-time positions, PnL, and the currently traded CE/PE pair."
    )

    # Structural placeholder for future implementation
    st.markdown("### Currently Watched Pair")
    st.info("ATM CE/PE pair tracking will appear here in paper/live mode.")

    st.markdown("### Open Positions")
    st.info("Active positions and real-time PnL will appear here.")

    st.markdown("### Today's Session")
    st.info("Running daily PnL and circuit breaker status will appear here.")
