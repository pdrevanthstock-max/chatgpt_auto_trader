"""
AutoTrader UI — Main Streamlit Application
────────────────────────────────────────────
§9: "Currently entirely unbuilt in both prior repos"

Now it exists. Features:
  - Start/Stop controls
  - Mode selector (Backtest / Paper / Live)
  - Live view of positions and PnL
  - Historical PnL view
  - Capital and threshold configuration
  - Pair trading display
"""

import streamlit as st

st.set_page_config(
    page_title="AutoTrader — CE/PE Divergence",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from config.settings import TradingConfig, APP_NAME, APP_VERSION
from ui.pages.backtest_page import render_backtest_page
from ui.pages.history_page import render_history_page
from ui.pages.live_view_page import render_live_view_page
from ui.components.controls import render_sidebar


def main():
    """Main Streamlit app entry point."""

    # Load config (persisted to config.json)
    if "config" not in st.session_state:
        st.session_state.config = TradingConfig.load()

    config = st.session_state.config

    # ── Sidebar ──
    selected_page = render_sidebar(config)

    # ── Header ──
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            padding: 1.5rem 2rem;
            border-radius: 12px;
            margin-bottom: 1.5rem;
            border: 1px solid rgba(255,255,255,0.1);
        ">
            <h1 style="
                color: #e0e0e0;
                margin: 0;
                font-size: 1.8rem;
                font-weight: 700;
                letter-spacing: -0.5px;
            ">📊 {APP_NAME} <span style="
                color: #4fc3f7;
                font-size: 0.9rem;
                font-weight: 400;
            ">v{APP_VERSION}</span></h1>
            <p style="
                color: #90a4ae;
                margin: 0.3rem 0 0 0;
                font-size: 0.95rem;
            ">CE/PE Divergence Capture Strategy — Directional Mode</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Page Router ──
    if selected_page == "Backtest":
        render_backtest_page(config)
    elif selected_page == "History":
        render_history_page(config)
    elif selected_page == "Live View":
        render_live_view_page(config)


if __name__ == "__main__":
    main()
