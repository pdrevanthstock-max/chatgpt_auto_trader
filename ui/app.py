import os
import sys
import logging
import time
import threading
import asyncio
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, date, timedelta, time as datetime_time
from pathlib import Path
import streamlit as st
import pandas as pd

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from config.settings import TradingConfig, APP_NAME, APP_VERSION
from core.enums import ExecutionMode, MarketRegime, TradePhase, ExitReason, SignalType, TradeDirection, OrderType
from core.models import Trade, TradePlan, ExecutionSignal, PairedCandle, ScoredCandidate
from data.historical_loader import HistoricalLoader
from backtest.engine import BacktestEngine
from backtest.results import BacktestResults
from database.trade_store import TradeStore
from reporting.excel_export import ExcelExporter
from monitoring.health_monitor import HealthMonitor

from strategy.pair_candidate_generator import PairCandidateGenerator
from strategy.liquidity_filter import LiquidityFilter
from strategy.divergence_scanner import DivergenceScanner
from strategy.entry_signal import EntrySignal
from strategy.pair_ranker import PairRanker
from strategy.regime_detector import RegimeDetector
from strategy.trade_planner import TradePlanner
from strategy.position_guard import PositionGuard
from strategy.daily_circuit_breaker import DailyCircuitBreaker
from strategy.position_sizer import PositionSizer
from strategy.order_type_selector import OrderTypeSelector
from strategy.exit_manager import ExitManager
from strategy.hedge_cut_manager import HedgeCutManager
from strategy.single_leg_exit_manager import SingleLegExitManager
from strategy.rotation_engine import RotationEngine
from strategy.decision_memory import DecisionMemory
from execution.execution_validator import ExecutionValidator
from execution.execution_queue import ExecutionQueue
from execution.paper_executor import PaperExecutor
from execution.broker_executor import BrokerExecutor
from execution.crash_recovery import CrashRecovery

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AutoTrader")

st.set_page_config(
    page_title="AutoTrader Dashboard",
    page_icon="📈",
    layout="wide"
)

# Custom premium CSS for dark mode and styling
st.markdown(
    """
    <style>
    .reportview-container {
        background: #0f172a;
    }
    .metric-card {
        background-color: #1e293b;
        border-radius: 12px;
        padding: 20px;
        border: 1px solid #334155;
        box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
        text-align: center;
    }
    .metric-value {
        font-size: 2rem;
        font-weight: 700;
        margin-top: 5px;
    }
    .health-bar {
        background: rgba(30, 41, 59, 0.7);
        border: 1px solid #475569;
        border-radius: 8px;
        padding: 10px 20px;
        margin-bottom: 20px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .health-indicator {
        font-size: 0.9rem;
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True
)

class LiveEngine:
    """
    Background orchestrator loop for live/paper option divergence execution.
    Fires when user clicks 'Start' and manages execution via Thread.
    """
    def __init__(self) -> None:
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.config = TradingConfig.load()
        
        # Strategy components
        self.generator = PairCandidateGenerator()
        self.liq_filter = LiquidityFilter()
        self.scanner = DivergenceScanner()
        self.entry_signal = EntrySignal()
        self.ranker = PairRanker()
        self.regime_detector = RegimeDetector()
        self.planner = TradePlanner()
        self.pos_guard = PositionGuard()
        self.circuit_breaker = DailyCircuitBreaker()
        self.sizer = PositionSizer()
        self.order_selector = OrderTypeSelector()
        self.exit_manager = ExitManager()
        self.hedge_cut_manager = HedgeCutManager()
        self.single_leg_exit_manager = SingleLegExitManager()
        self.rotation_engine = RotationEngine()
        self.decision_memory = DecisionMemory()
        self.validator = ExecutionValidator()
        self.queue = ExecutionQueue()
        self.paper_executor = PaperExecutor()
        self.broker_executor = BrokerExecutor()
        self.recovery = CrashRecovery()
        self.health_monitor = HealthMonitor()
        self.store = TradeStore()
        
        # Real-time state
        self.realized_pnl = 0.0
        self.active_trade: Optional[Trade] = None
        
        # Regime detector windows
        self.spot_closes = []
        self.spot_highs = []
        self.spot_lows = []
        self.vwap_values = []
        self.atr_values = []

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        logger.info("LiveEngine started background thread loop.")

    def stop(self) -> None:
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        logger.info("LiveEngine stopped background thread loop.")

    def _loop(self) -> None:
        # Load state from crash recovery
        self.realized_pnl, self.active_trade = self.recovery.load_state()
        
        # Start Live Feed & Queue worker
        from data.live_feed import LiveFeed
        self.feed = LiveFeed()
        self.feed.start()
        
        self.queue.clear()
        self.queue.start_background_worker(self._execute_signal)
        
        while self.running:
            try:
                self.config = TradingConfig.load()
                self._run_strategy_cycle()
                time.sleep(5)  # strategy evaluates every 5 seconds
            except Exception as e:
                logger.error(f"Error in LiveEngine background iteration: {e}")
                time.sleep(5)

        self.feed.stop()
        self.queue.stop_background_worker()

    def _run_strategy_cycle(self) -> None:
        now = datetime.now()
        current_time_only = now.time()
        
        start_hour, start_min = map(int, self.config.scan_start.split(":"))
        end_hour, end_min = map(int, self.config.scan_end.split(":"))
        entry_cutoff_hour, entry_cutoff_min = map(int, self.config.last_entry_time.split(":"))
        
        trading_hours = datetime_time(start_hour, start_min) <= current_time_only < datetime_time(end_hour, end_min)
        last_entry_passed = current_time_only >= datetime_time(entry_cutoff_hour, entry_cutoff_min)
        is_preclose = current_time_only >= datetime_time(15, 0)

        # Get spot price from MarketCache
        from data.market_cache import market_cache
        spot_price, _ = market_cache.get_spot()
        if spot_price <= 0.0:
            return  # cache not populated by feed yet
            
        atm_strike = market_cache.get_atm_strike()

        # Update spot windows
        self.spot_closes.append(spot_price)
        self.spot_highs.append(spot_price)
        self.spot_lows.append(spot_price)
        self.vwap_values.append(spot_price)
        self.atr_values.append(2.0)  # mock ATR

        if len(self.spot_closes) > 20:
            self.spot_closes.pop(0)
            self.spot_highs.pop(0)
            self.spot_lows.pop(0)
            self.vwap_values.pop(0)
            self.atr_values.pop(0)

        regime, spot_trend = self.regime_detector.detect_regime(
            spot_closes=self.spot_closes,
            spot_highs=self.spot_highs,
            spot_lows=self.spot_lows,
            vwap_values=self.vwap_values,
            atr_values=self.atr_values,
            atm_strike=atm_strike
        )

        breaker_hit = self.circuit_breaker.is_breaker_triggered(self.realized_pnl, self.config)

        if self.active_trade and self.active_trade.is_open:
            ce_data = market_cache.get_option(self.active_trade.strike_ce, "CE")
            pe_data = market_cache.get_option(self.active_trade.strike_pe, "PE")
            
            if ce_data and pe_data:
                ce_p = ce_data["last"]
                pe_p = pe_data["last"]
                
                # Check EOD flatten
                if current_time_only >= datetime_time(end_hour, end_min):
                    self.queue.enqueue(ExecutionSignal(
                        type=SignalType.EXIT_BOTH,
                        trade_id=self.active_trade.id,
                        reason="EOD_SQUARE_OFF"
                    ))
                else:
                    if self.active_trade.phase == TradePhase.PHASE_1_BOTH_LEGS:
                        exit_res = self.exit_manager.check_exits(
                            trade=self.active_trade,
                            ce_price=ce_p,
                            pe_price=pe_p,
                            iv_percentile=50.0,
                            is_preclose=is_preclose,
                            config=self.config
                        )
                        if exit_res:
                            self.queue.enqueue(ExecutionSignal(
                                type=SignalType.EXIT_BOTH,
                                trade_id=self.active_trade.id,
                                reason=exit_res.value
                            ))
                        else:
                            if self.active_trade.regime_at_entry == MarketRegime.DIRECTIONAL:
                                if self.hedge_cut_manager.should_hedge_cut(self.active_trade, ce_p, pe_p, self.config):
                                    self.queue.enqueue(ExecutionSignal(
                                        type=SignalType.HEDGE_CUT,
                                        trade_id=self.active_trade.id
                                    ))
                                else:
                                    self._check_rotation_live(regime, ce_p, pe_p)
                            else:
                                self._check_rotation_live(regime, ce_p, pe_p)
                                
                    elif self.active_trade.phase == TradePhase.PHASE_2_SINGLE_LEG:
                        exit_res = self.single_leg_exit_manager.check_single_leg_exit(
                            trade=self.active_trade,
                            ce_price=ce_p,
                            pe_price=pe_p,
                            config=self.config
                        )
                        if exit_res:
                            self.queue.enqueue(ExecutionSignal(
                                type=SignalType.EXIT_BOTH,
                                trade_id=self.active_trade.id,
                                reason=exit_res.value
                            ))
                        else:
                            if regime == MarketRegime.SIDEWAYS:
                                self._check_rotation_live(regime, ce_p, pe_p)
        else:
            # Check entry conditions
            if trading_hours and not last_entry_passed and not breaker_hit:
                healthy, _ = self.health_monitor.check_health(self.config)
                if healthy:
                    candidates = self.generator.generate_candidates()
                    ce_strikes = [c[0] for c in candidates]
                    pe_strikes = [c[1] for c in candidates]
                    
                    filtered_ce = self.liq_filter.filter_strikes(ce_strikes, "CE", self.config)
                    filtered_pe = self.liq_filter.filter_strikes(pe_strikes, "PE", self.config)
                    
                    filtered_candidates = []
                    for ce in filtered_ce:
                        for pe in filtered_pe:
                            filtered_candidates.append((ce, pe))
                            
                    scanned = self.scanner.scan_candidates(filtered_candidates)
                    survivors = self.entry_signal.evaluate_signals(scanned, regime, spot_trend, self.config)
                    top_candidate = self.ranker.rank_candidates(survivors, self.config)
                    
                    if top_candidate:
                        ce_data = market_cache.get_option(top_candidate.ce_strike, "CE")
                        pe_data = market_cache.get_option(top_candidate.pe_strike, "PE")
                        if ce_data and pe_data:
                            qty = self.sizer.calculate_lots(ce_data["last"], pe_data["last"], self.config)
                            if qty > 0:
                                plan = self.planner.plan_trade(
                                    candidate=top_candidate,
                                    regime=regime,
                                    quantity=qty,
                                    ce_price=ce_data["last"],
                                    pe_price=pe_data["last"],
                                    config=self.config
                                )
                                is_valid, _ = self.validator.validate_entry(
                                    plan=plan,
                                    realized_pnl=self.realized_pnl,
                                    active_trade=self.active_trade,
                                    config=self.config
                                )
                                if is_valid:
                                    self.queue.enqueue(ExecutionSignal(
                                        type=SignalType.ENTRY,
                                        trade_plan=plan
                                    ))

    def _check_rotation_live(self, regime: MarketRegime, ce_p: float, pe_p: float) -> None:
        candidates = self.generator.generate_candidates()
        ce_strikes = [c[0] for c in candidates]
        pe_strikes = [c[1] for c in candidates]
        
        filtered_ce = self.liq_filter.filter_strikes(ce_strikes, "CE", self.config)
        filtered_pe = self.liq_filter.filter_strikes(pe_strikes, "PE", self.config)
        
        filtered_candidates = []
        for ce in filtered_ce:
            for pe in filtered_pe:
                filtered_candidates.append((ce, pe))
                
        scanned = self.scanner.scan_candidates(filtered_candidates)
        survivors = self.entry_signal.evaluate_signals(scanned, regime, "SIDEWAYS", self.config)
        top_candidate = self.ranker.rank_candidates(survivors, self.config)

        if top_candidate:
            now = datetime.now()
            should, reason = self.rotation_engine.should_rotate(
                active_trade=self.active_trade,
                top_candidate=top_candidate,
                current_time=now,
                current_regime=regime,
                config=self.config
            )
            if should:
                plan = self.planner.plan_trade(
                    candidate=top_candidate,
                    regime=regime,
                    quantity=self.active_trade.quantity,
                    ce_price=ce_p,
                    pe_price=pe_p,
                    config=self.config
                )
                self.queue.enqueue(ExecutionSignal(
                    type=SignalType.ROTATION,
                    trade_plan=plan,
                    reason=reason
                ))

    def _execute_signal(self, signal: ExecutionSignal) -> None:
        now = datetime.now()
        is_live = self.config.execution_mode == ExecutionMode.LIVE.value

        if signal.type == SignalType.ENTRY:
            plan = signal.trade_plan
            if is_live:
                loop = asyncio.new_event_loop()
                trade = loop.run_until_complete(self.broker_executor.execute_entry(plan, now))
                loop.close()
            else:
                trade = self.paper_executor.execute_entry(plan, now)

            self.active_trade = trade
            self.store.save_trade(trade)
            self.recovery.save_state(self.realized_pnl, trade)
            self.decision_memory.log_entry(trade.id, plan)

        elif signal.type == SignalType.EXIT_BOTH:
            if self.active_trade and self.active_trade.is_open:
                reason = ExitReason(signal.reason or "MANUAL")
                if is_live:
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(self.broker_executor.execute_exit_both(self.active_trade, now, reason))
                    loop.close()
                else:
                    self.paper_executor.execute_exit_both(self.active_trade, now, reason)

                self.realized_pnl = round(self.realized_pnl + self.active_trade.combined_pnl, 2)
                self.store.save_trade(self.active_trade)
                self.recovery.save_state(self.realized_pnl, None)
                self.decision_memory.log_exit(self.active_trade.id, self.active_trade, reason.value)
                self.active_trade = None

        elif signal.type == SignalType.HEDGE_CUT:
            if self.active_trade and self.active_trade.phase == TradePhase.PHASE_1_BOTH_LEGS:
                if is_live:
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(self.broker_executor.execute_hedge_cut(self.active_trade, now))
                    loop.close()
                else:
                    self.paper_executor.execute_hedge_cut(self.active_trade, now)

                self.store.save_trade(self.active_trade)
                self.recovery.save_state(self.realized_pnl, self.active_trade)
                self.decision_memory.log_hedge_cut(
                    self.active_trade.id,
                    self.active_trade.losing_leg,
                    self.active_trade.losing_leg_exit_price,
                    self.active_trade.losing_leg_pnl
                )

        elif signal.type == SignalType.ROTATION:
            if self.active_trade and self.active_trade.is_open:
                # Close current
                if is_live:
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(self.broker_executor.execute_exit_both(self.active_trade, now, ExitReason.ROTATION))
                    loop.close()
                else:
                    self.paper_executor.execute_exit_both(self.active_trade, now, ExitReason.ROTATION)

                self.realized_pnl = round(self.realized_pnl + self.active_trade.combined_pnl, 2)
                self.store.save_trade(self.active_trade)
                self.rotation_engine.set_cooldown(self.active_trade.strike_ce, self.active_trade.strike_pe, now, self.config)

                old_id = self.active_trade.id
                old_pnl = self.active_trade.combined_pnl
                self.active_trade = None

                # Enter new
                plan = signal.trade_plan
                if is_live:
                    loop = asyncio.new_event_loop()
                    trade = loop.run_until_complete(self.broker_executor.execute_entry(plan, now))
                    loop.close()
                else:
                    trade = self.paper_executor.execute_entry(plan, now)

                self.active_trade = trade
                self.store.save_trade(trade)
                self.recovery.save_state(self.realized_pnl, trade)
                self.decision_memory.log_rotation(old_id, old_pnl, plan, signal.reason or "Better score")
                self.decision_memory.log_entry(trade.id, plan)

def main():
    # Load config
    config = TradingConfig.load()
    store = TradeStore()
    monitor = HealthMonitor()

    # Initialize Singleton LiveEngine in st.session_state
    if "live_engine" not in st.session_state:
        st.session_state["live_engine"] = LiveEngine()
    engine_inst = st.session_state["live_engine"]

    # Title Banner
    st.markdown(
        f"""
        <div style="background: linear-gradient(135deg, #1e3a8a, #0f172a); padding: 25px; border-radius: 12px; margin-bottom: 20px; border: 1px solid #2563eb;">
            <h1 style="color: white; margin: 0; font-size: 2.2rem;">📊 {APP_NAME} <span style="font-size: 1.2rem; color: #60a5fa;">v{APP_VERSION}</span></h1>
            <p style="color: #94a3b8; margin: 5px 0 0 0;">Adaptive CE/PE Option Divergence Capture Engine (v6 vwap+atr matrix scan)</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    # Sidebar configurations
    st.sidebar.markdown("### ⚙️ Engine Configurations")
    
    exec_mode = st.sidebar.selectbox(
        "Execution Mode",
        options=[ExecutionMode.BACKTEST.value, ExecutionMode.PAPER.value, ExecutionMode.LIVE.value],
        index=[ExecutionMode.BACKTEST.value, ExecutionMode.PAPER.value, ExecutionMode.LIVE.value].index(config.execution_mode)
    )
    config.execution_mode = exec_mode

    # Manual Start / Stop Controls
    st.sidebar.markdown("### 🚦 Engine Operational Status")
    
    # Render Start / Stop Buttons
    if exec_mode != ExecutionMode.BACKTEST.value:
        col_start, col_stop = st.sidebar.columns(2)
        with col_start:
            if st.button("▶️ Start Engine", disabled=engine_inst.running, use_container_width=True):
                engine_inst.start()
                st.toast("AutoTrader Live/Paper Engine started successfully!", icon="🟢")
                st.rerun()
        with col_stop:
            if st.button("⏹️ Stop Engine", disabled=not engine_inst.running, use_container_width=True):
                engine_inst.stop()
                st.toast("AutoTrader Live/Paper Engine stopped.", icon="🛑")
                st.rerun()

        status_text = "🟢 RUNNING" if engine_inst.running else "🛑 STOPPED"
        st.sidebar.markdown(f"Status: **{status_text}**")
    else:
        st.sidebar.markdown("Status: **N/A (Backtest Mode)**")

    # Allocation & Sizing
    total_capital = st.sidebar.number_input(
        "Total Capital (₹)",
        min_value=1000.0,
        max_value=1000000.0,
        value=config.total_capital,
        step=5000.0
    )
    config.total_capital = total_capital

    nifty_lot = st.sidebar.number_input(
        "Nifty Lot Size",
        min_value=5,
        max_value=250,
        value=config.nifty_lot_size,
        step=5
    )
    config.nifty_lot_size = nifty_lot

    # Scanning params
    matrix_range = st.sidebar.slider(
        "Matrix Scan Range (ATM ± N strikes)",
        min_value=1,
        max_value=15,
        value=config.pair_scan_range
    )
    config.pair_scan_range = matrix_range

    # Divergence band slider
    divergence_min = st.sidebar.slider(
        "Min Divergence Band (%)",
        min_value=0.1,
        max_value=5.0,
        value=config.divergence_band_min,
        step=0.1
    )
    config.divergence_band_min = divergence_min

    divergence_max = st.sidebar.slider(
        "Max Divergence Band (%)",
        min_value=1.0,
        max_value=15.0,
        value=config.divergence_band_max,
        step=0.5
    )
    config.divergence_band_max = divergence_max

    # Dates for backtester
    st.sidebar.markdown("### 📅 Backtest Date Range")
    default_from = date.today() - timedelta(days=35)
    default_to = date.today() - timedelta(days=1)
    
    from_date = st.sidebar.date_input("From Date", default_from)
    to_date = st.sidebar.date_input("To Date", default_to)

    config.backtest_from_date = from_date.strftime("%Y-%m-%d")
    config.backtest_to_date = to_date.strftime("%Y-%m-%d")

    # Save configs on change
    config.save()

    # Health Monitor Status Line
    healthy, status_msg = monitor.check_health(config)
    health_color = "#10b981" if healthy else "#ef4444"
    st.markdown(
        f"""
        <div class="health-bar">
            <div class="health-indicator">System Health Monitor: <span style="color: {health_color};">{status_msg}</span></div>
            <div class="health-indicator">EOD Cutoff: <span style="color: #60a5fa;">{config.scan_end} IST</span></div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # Main Tabs
    tab_bt, tab_live, tab_hist = st.tabs(["📉 Backtest Engine", "🟢 Live Monitoring", "📜 Trade Journal"])

    # -------------------------------------------------------------
    # TAB 1: BACKTESTER
    # -------------------------------------------------------------
    with tab_bt:
        st.subheader("Historical Simulation Replay")
        st.write("Replay historical tick data through the divergence matrix scanner to compute profitability.")

        col_run, col_status = st.columns([1, 4])
        with col_run:
            run_btn = st.button("🚀 Run Backtest", use_container_width=True)

        if run_btn:
            try:
                with st.spinner("Fetching option chain candles..."):
                    loader = HistoricalLoader()
                    days = loader.fetch_historical_data(
                        from_date=config.backtest_from_date,
                        to_date=config.backtest_to_date,
                        scan_range=config.pair_scan_range,
                        interval_minutes=config.candle_interval_minutes
                    )
                
                with st.spinner("Replaying historical days..."):
                    engine = BacktestEngine(config)
                    trades = engine.run(days)
                    
                    # Save trades to Database for persistence
                    for t in trades:
                        store.save_trade(t)
                    
                    # Store backtest results in session state
                    st.session_state["bt_trades"] = trades
                    st.success(f"Backtest run complete! Executed {len(trades)} trades.")
            except Exception as e:
                st.error(f"Backtest execution failed: {e}")

        # Render results if available
        if "bt_trades" in st.session_state and st.session_state["bt_trades"]:
            trades = st.session_state["bt_trades"]
            res = BacktestResults(trades, config.total_capital)
            metrics = res.calculate_metrics()

            # Side-by-side Gross/Net PnL & Stats cards
            st.markdown("### Performance Metrics")
            c1, c2, c3, c4 = st.columns(4)
            
            pnl_color = "#10b981" if metrics["total_pnl"] >= 0 else "#ef4444"
            c1.markdown(f'<div class="metric-card">Gross P&L<div class="metric-value" style="color: {pnl_color};">₹{metrics["total_pnl"]:,.2f}</div></div>', unsafe_allow_html=True)
            c2.markdown(f'<div class="metric-card">Win Rate<div class="metric-value" style="color: #60a5fa;">{metrics["win_rate"]}%</div></div>', unsafe_allow_html=True)
            c3.markdown(f'<div class="metric-card">Profit Factor<div class="metric-value" style="color: #fbbf24;">{metrics["profit_factor"]}</div></div>', unsafe_allow_html=True)
            c4.markdown(f'<div class="metric-card">Max Drawdown<div class="metric-value" style="color: #f87171;">₹{metrics["max_drawdown"]:,.2f}</div></div>', unsafe_allow_html=True)

            # Equity Curve chart
            st.markdown("### Equity Curve")
            equity = [config.total_capital]
            for t in trades:
                equity.append(equity[-1] + t.combined_pnl)
            
            df_eq = pd.DataFrame({"Portfolio Value": equity})
            st.line_chart(df_eq)

            # Excel download
            excel_filename = f"backtest_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            if st.button("📥 Generate and Download Excel Report"):
                filepath = ExcelExporter.export_backtest(trades, excel_filename)
                with open(filepath, "rb") as f:
                    st.download_button(
                        label="Download Excel File",
                        data=f,
                        file_name=excel_filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

    # -------------------------------------------------------------
    # TAB 2: LIVE MONITORING
    # -------------------------------------------------------------
    with tab_live:
        st.subheader("Live Operational View")
        
        # Display currently-held pair
        active_trades = [t for t in store.get_all_trades() if t.is_open]
        
        if active_trades:
            active_trade = active_trades[-1]
            st.info(f"⚡ Currently holding open position: {active_trade.id}")
            
            lc1, lc2, lc3 = st.columns(3)
            with lc1:
                st.markdown(
                    f"""
                    <div style="background: #1e293b; padding: 15px; border-radius: 8px; border: 1px solid #3b82f6;">
                        <h4 style="margin: 0; color: #60a5fa;">CE Leg Status</h4>
                        <p style="margin: 5px 0 0 0; font-size: 1.2rem; font-weight: 700; color: white;">Strike: {active_trade.strike_ce} | Entry: ₹{active_trade.entry_ce_price:.2f}</p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            with lc2:
                st.markdown(
                    f"""
                    <div style="background: #1e293b; padding: 15px; border-radius: 8px; border: 1px solid #10b981;">
                        <h4 style="margin: 0; color: #34d399;">PE Leg Status</h4>
                        <p style="margin: 5px 0 0 0; font-size: 1.2rem; font-weight: 700; color: white;">Strike: {active_trade.strike_pe} | Entry: ₹{active_trade.entry_pe_price:.2f}</p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            with lc3:
                pnl_style = "color: #10b981;" if active_trade.combined_pnl >= 0 else "color: #ef4444;"
                st.markdown(
                    f"""
                    <div style="background: #1e293b; padding: 15px; border-radius: 8px; border: 1px solid #fbbf24;">
                        <h4 style="margin: 0; color: #fbbf24;">Position Details</h4>
                        <p style="margin: 5px 0 0 0; font-size: 1.1rem; color: white;">Phase: {active_trade.phase.value} | PnL: <span style="{pnl_style} font-weight:700;">₹{active_trade.combined_pnl:.2f}</span></p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
        else:
            st.info("No active open position at this moment.")

    # -------------------------------------------------------------
    # TAB 3: TRADE JOURNAL
    # -------------------------------------------------------------
    with tab_hist:
        st.subheader("Historical Trade Journal")
        all_trades = store.get_all_trades()
        
        if all_trades:
            rows = []
            for t in all_trades:
                rows.append({
                    "Trade ID": t.id,
                    "Direction": t.direction.value,
                    "CE Strike": t.strike_ce,
                    "PE Strike": t.strike_pe,
                    "CE Entry": t.entry_ce_price,
                    "PE Entry": t.entry_pe_price,
                    "Regime": t.regime_at_entry.value,
                    "Phase": t.phase.value,
                    "Hedge-Cut Time": t.hedge_cut_time.strftime("%H:%M:%S") if t.hedge_cut_time else "N/A",
                    "CE Exit": t.exit_ce_price if t.exit_ce_price else "N/A",
                    "PE Exit": t.exit_pe_price if t.exit_pe_price else "N/A",
                    "Exit Time": t.exit_time.strftime("%m-%d %H:%M:%S") if t.exit_time else "OPEN",
                    "Reason": t.exit_reason.value if t.exit_reason else "N/A",
                    "PnL (₹)": t.combined_pnl
                })
            
            df_hist = pd.DataFrame(rows)
            st.dataframe(df_hist, use_container_width=True)
        else:
            st.info("No trades saved in SQLite database yet.")

if __name__ == "__main__":
    main()
