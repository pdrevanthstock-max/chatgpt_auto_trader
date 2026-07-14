import os
import sys
import importlib
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
import strategy.pair_ranker
importlib.reload(strategy.pair_ranker)
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
import execution.crash_recovery
importlib.reload(execution.crash_recovery)
from execution.crash_recovery import CrashRecovery
from ui.trade_view import daily_sl_status, display_trade_id, units_per_leg

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AutoTrader")
_global_active_engine = None
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
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border-radius: 14px;
        padding: 24px;
        border: 2px solid #475569;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
        text-align: center;
        margin-bottom: 15px;
    }
    .metric-title {
        font-size: 1rem;
        font-weight: 700;
        color: #e2e8f0;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-bottom: 10px;
    }
    .metric-value {
        font-size: 2.3rem;
        font-weight: 800;
        margin-top: 5px;
        text-shadow: 0 2px 4px rgba(0,0,0,0.4);
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
        
        # Thread-safe activity log list
        self._log_lock = threading.Lock()
        self.activity_log: List[str] = []
        
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

    def log_activity(self, message: str) -> None:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted = f"[{ts}] {message}"
        with self._log_lock:
            self.activity_log.append(formatted)
            if len(self.activity_log) > 200:
                self.activity_log.pop(0)

    def start(self) -> None:
        if self.running:
            return
            
        # Re-instantiate all strategy modules to pick up disk code modifications on startup
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
        
        with self._log_lock:
            self.activity_log.clear()
            
        self.log_activity("Clearing stale market cache data...")
        from data.market_cache import market_cache
        market_cache.clear()

        self.log_activity("Initializing pre-flight credentials checks...")
        
        # Pre-flight token validation for live/paper modes
        if self.config.execution_mode in [ExecutionMode.PAPER.value, ExecutionMode.LIVE.value]:
            from data.dhan_client import DhanClient
            client = DhanClient()
            try:
                client.validate_credentials()
                self.log_activity("Pre-flight credentials check successful.")
            except Exception as auth_err:
                self.log_activity(f"Pre-flight authentication check failed: {auth_err}")
                logger.error(f"Pre-flight authentication check failed: {auth_err}")
                raise ValueError(f"Dhan Authentication Failed. Please check access token in .env. Details: {auth_err}")

        self.running = True
        self.recovery.save_engine_status(True)
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        self.log_activity(f"LiveEngine background thread loop started in {self.config.execution_mode} mode.")
        logger.info("LiveEngine started background thread loop.")

    def stop(self) -> None:
        self.running = False
        self.recovery.save_engine_status(False)
        if self.thread:
            self.thread.join(timeout=2.0)
        
        self.log_activity("Clearing market cache data...")
        from data.market_cache import market_cache
        market_cache.clear()

        self.log_activity("LiveEngine stopped background thread loop.")
        logger.info("LiveEngine stopped background thread loop.")

    def _loop(self) -> None:
        self.log_activity("Running recovery state load...")
        # Load state from crash recovery
        self.realized_pnl, self.active_trade = self.recovery.load_state()
        if self.active_trade:
            self.log_activity(f"Crash Recovery: Recovered active trade {display_trade_id(self.active_trade)} ({self.active_trade.phase.value})")
        else:
            self.log_activity("Crash Recovery: No active open trade found.")
        
        # Start Live Feed & Queue worker
        from data.live_feed import LiveFeed
        self.feed = LiveFeed()
        self.feed.start()
        self.log_activity("Live market-data feed initialization requested.")
        
        self.queue.clear()
        self.queue.start_background_worker(self._execute_signal)
        
        while self.running:
            try:
                self.config = TradingConfig.load()
                self._run_strategy_cycle()
                time.sleep(5)  # strategy evaluates every 5 seconds
            except Exception as e:
                self.log_activity(f"Error in LiveEngine cycle: {e}")
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
            self.log_activity("Waiting for spot price cache update...")
            return
            
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

        # Check daily circuit breaker using combined realized PnL + active trade unrealized PnL
        current_total_pnl = self.realized_pnl
        if self.active_trade and self.active_trade.is_open:
            current_total_pnl += self.active_trade.combined_pnl
            
        breaker_hit = self.circuit_breaker.is_breaker_triggered(current_total_pnl, self.config)

        if self.active_trade and self.active_trade.is_open:
            ce_data = market_cache.get_option(self.active_trade.strike_ce, "CE")
            pe_data = market_cache.get_option(self.active_trade.strike_pe, "PE")
            
            if ce_data and pe_data:
                self.active_trade.ce_current_price = ce_data["last"]
                self.active_trade.pe_current_price = pe_data["last"]
                
                # Save updated live prices and PnL to SQLite database & recovery state
                self.store.save_trade(self.active_trade)
                self.recovery.save_state(self.realized_pnl, self.active_trade)
                
                ce_p = ce_data["last"]
                pe_p = pe_data["last"]
                
                self.log_activity(f"Active Position holding: {display_trade_id(self.active_trade)} ({self.active_trade.phase.value}). Combined PnL: ₹{self.active_trade.combined_pnl:.2f}")
                
                # Check circuit breaker hit dynamically during active trade (protect 3% capital)
                if breaker_hit and self.config.execution_mode != ExecutionMode.PAPER.value:
                    self.log_activity("Daily loss limit breached by active trade unrealized loss. Enqueuing emergency exit!")
                    self.queue.enqueue(ExecutionSignal(
                        type=SignalType.EXIT_BOTH,
                        trade_id=self.active_trade.id,
                        reason="CIRCUIT_BREAKER_TRIGGERED"
                    ))
                    return

                # Check EOD flatten
                if current_time_only >= datetime_time(end_hour, end_min):
                    self.log_activity("EOD close cutoff reached. Enqueuing exit.")
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
                            self.log_activity(f"Exit trigger: {exit_res.value}. Enqueuing exit.")
                            self.queue.enqueue(ExecutionSignal(
                                type=SignalType.EXIT_BOTH,
                                trade_id=self.active_trade.id,
                                reason=exit_res.value
                            ))
                        else:
                            if self.active_trade.regime_at_entry == MarketRegime.DIRECTIONAL:
                                if self.hedge_cut_manager.should_hedge_cut(self.active_trade, ce_p, pe_p, self.config):
                                    self.log_activity("Losing leg breach. Enqueuing hedge cut.")
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
                            self.log_activity(f"Single leg trailing exit: {exit_res.value}. Enqueuing exit.")
                            self.queue.enqueue(ExecutionSignal(
                                type=SignalType.EXIT_BOTH,
                                trade_id=self.active_trade.id,
                                reason=exit_res.value
                            ))
                        else:
                            if regime == MarketRegime.SIDEWAYS:
                                self._check_rotation_live(regime, ce_p, pe_p)
        else:
            # Reconcile open positions with broker to catch orphan positions in LIVE mode
            if self.config.execution_mode == ExecutionMode.LIVE.value:
                try:
                    positions = self.broker_executor.client.get_positions()
                    active_positions = [p for p in positions if int(p.get("netQty", 0)) != 0]
                    if active_positions:
                        self.log_activity(f"Reconciliation Alert: Found {len(active_positions)} open positions at broker with no active trade. Squaring off!")
                        for pos in active_positions:
                            qty = abs(int(pos.get("netQty", 0)))
                            direction = "SELL" if int(pos.get("netQty", 0)) > 0 else "BUY"
                            details = {
                                "security_id": str(pos.get("securityId")),
                                "exchange_segment": pos.get("exchangeSegment", "NSE_FNO"),
                                "transaction_type": direction,
                                "quantity": qty,
                                "order_type": "MARKET",
                                "product_type": "MARGIN",
                                "price": 0.0
                            }
                            # Send order directly to client place_order
                            self.broker_executor.client.place_order(details)
                            self.log_activity(f"Reconciliation: Closed position {pos.get('tradingSymbol')} at broker.")
                except Exception as recon_err:
                    logger.error(f"Broker position reconciliation check failed: {recon_err}")

            # Check entry conditions
            if not trading_hours:
                self.log_activity(f"Outside trading hours (09:30-15:20). Current: {now.strftime('%H:%M:%S')}")
                return
            if last_entry_passed:
                self.log_activity(f"Last entry time passed. Entries disabled.")
                return
            if breaker_hit and self.config.execution_mode != ExecutionMode.PAPER.value:
                self.log_activity("Daily Circuit Breaker is active. Entries blocked.")
                return
            if breaker_hit:
                self.log_activity(
                    "PAPER daily loss threshold is active. Testing continues; "
                    "new trades will be tagged -SL."
                )

            self.log_activity(f"Scanning market. Spot: {spot_price:.2f} | ATM Strike: {atm_strike} | Regime: {regime.value} ({spot_trend})")
            healthy, health_msg = self.health_monitor.check_health(self.config)
            if not healthy:
                self.log_activity(f"Health check failed: {health_msg}. Skipping scan.")
                return

            candidates = self.generator.generate_candidates()
            if not candidates:
                self.log_activity("No candidates generated (empty option chain).")
                return
            # De-duplicate strikes before running liquidity filter (CPU and matrix sizing optimization)
            ce_strikes = list(set(c[0] for c in candidates))
            pe_strikes = list(set(c[1] for c in candidates))
            
            filtered_ce = self.liq_filter.filter_strikes(ce_strikes, "CE", self.config)
            filtered_pe = self.liq_filter.filter_strikes(pe_strikes, "PE", self.config)
            
            filtered_candidates = []
            for ce in filtered_ce:
                for pe in filtered_pe:
                    filtered_candidates.append((ce, pe))
            
            self.log_activity(f"Liquidity Filter: {len(filtered_candidates)} of {len(candidates)} pairs passed pre-Cartesian check.")
            if not filtered_candidates:
                return
                
            scanned = self.scanner.scan_candidates(filtered_candidates)
            survivors = self.entry_signal.evaluate_signals(scanned, regime, spot_trend, self.config)
            self.log_activity(f"Divergence check: {len(survivors)} of {len(scanned)} pairs passed entry criteria.")
            
            top_candidate = self.ranker.rank_candidates(survivors, self.config)
            
            if top_candidate:
                self.log_activity(f"Top Candidate selected: {top_candidate.ce_strike}CE-{top_candidate.pe_strike}PE (Divergence: {top_candidate.divergence:.2f}%)")
                ce_data = market_cache.get_option(top_candidate.ce_strike, "CE")
                pe_data = market_cache.get_option(top_candidate.pe_strike, "PE")
                if ce_data and pe_data:
                    ce_entry_price = ce_data.get("ask", ce_data["last"])
                    pe_entry_price = pe_data.get("ask", pe_data["last"])
                    qty = self.sizer.calculate_lots(
                        ce_entry_price,
                        pe_entry_price,
                        self.config,
                    )
                    if qty > 0:
                        plan = self.planner.plan_trade(
                            candidate=top_candidate,
                            regime=regime,
                            quantity=qty,
                            ce_price=ce_entry_price,
                            pe_price=pe_entry_price,
                            config=self.config
                        )
                        plan.post_daily_sl = (
                            self.config.execution_mode == ExecutionMode.PAPER.value
                            and breaker_hit
                        )
                        is_valid, reason = self.validator.validate_entry(
                            plan=plan,
                            realized_pnl=self.realized_pnl,
                            active_trade=self.active_trade,
                            config=self.config
                        )
                        if is_valid:
                            self.log_activity(f"Validation successful. Enqueuing entry signal for {qty} lots.")
                            self.queue.enqueue(ExecutionSignal(
                                type=SignalType.ENTRY,
                                trade_plan=plan
                            ))
                        else:
                            self.log_activity(f"Entry validation failed: {reason}")
                    else:
                        required_prem = (ce_entry_price + pe_entry_price) * self.config.nifty_lot_size
                        self.log_activity(f"Sizer returned 0 lots (Required: ₹{required_prem:.2f}, Capital: ₹{self.config.total_capital:.2f})")
            else:
                self.log_activity("No scanned pairs met entry signals.")

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
            plan.post_daily_sl = (
                self.config.execution_mode == ExecutionMode.PAPER.value
                and self.circuit_breaker.is_breaker_triggered(
                    self.realized_pnl, self.config
                )
            )
            self.log_activity(f"Executing ENTRY order for {plan.scored_candidate.ce_strike}CE / {plan.scored_candidate.pe_strike}PE ({plan.quantity} lots)...")
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
            self.log_activity(
                f"ENTRY SUCCESS: Position active (ID: {display_trade_id(trade)}). "
                f"CE: ₹{trade.entry_ce_price:.2f}, PE: ₹{trade.entry_pe_price:.2f}, "
                f"Size: {trade.quantity:,} lots / {units_per_leg(trade):,} units per leg."
            )

        elif signal.type == SignalType.EXIT_BOTH:
            if self.active_trade and self.active_trade.is_open:
                reason = ExitReason(signal.reason or "MANUAL")
                self.log_activity(f"Executing EXIT order for {display_trade_id(self.active_trade)} (Reason: {reason.value})...")
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
                self.log_activity(f"EXIT SUCCESS: Position closed. Combined PnL: ₹{self.active_trade.combined_pnl:.2f}. Total Session PnL: ₹{self.realized_pnl:.2f}")
                self.active_trade = None

        elif signal.type == SignalType.HEDGE_CUT:
            if self.active_trade and self.active_trade.phase == TradePhase.PHASE_1_BOTH_LEGS:
                self.log_activity(f"Executing HEDGE CUT order for losing leg of {display_trade_id(self.active_trade)}...")
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
                self.log_activity(f"HEDGE CUT SUCCESS: Losing leg ({self.active_trade.losing_leg}) cut at ₹{self.active_trade.losing_leg_exit_price:.2f}. Realized loss: ₹{self.active_trade.losing_leg_pnl:.2f}")

        elif signal.type == SignalType.ROTATION:
            if self.active_trade and self.active_trade.is_open:
                # Close current
                self.log_activity(f"Executing ROTATION close for {display_trade_id(self.active_trade)}...")
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
                self.log_activity(f"ROTATION CLOSE SUCCESS: Trade {old_id} closed at PnL ₹{old_pnl:.2f}.")
                self.active_trade = None

                # Enter new
                plan = signal.trade_plan
                plan.post_daily_sl = (
                    self.config.execution_mode == ExecutionMode.PAPER.value
                    and self.circuit_breaker.is_breaker_triggered(
                        self.realized_pnl, self.config
                    )
                )
                self.log_activity(f"Executing ROTATION entry for {plan.scored_candidate.ce_strike}CE / {plan.scored_candidate.pe_strike}PE ({plan.quantity} lots)...")
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
                self.log_activity(
                    f"ROTATION ENTRY SUCCESS: Position active (ID: {display_trade_id(trade)}). "
                    f"CE: ₹{trade.entry_ce_price:.2f}, PE: ₹{trade.entry_pe_price:.2f}, "
                    f"Size: {trade.quantity:,} lots / {units_per_leg(trade):,} units per leg."
                )

def main():
    # Load config
    config = TradingConfig.load()
    store = TradeStore()
    monitor = HealthMonitor()

    # Initialize Singleton LiveEngine using process-level sys persistence and thread locks
    import sys
    import threading
    _init_lock = globals().setdefault("_init_lock", threading.Lock())
    with _init_lock:
        if not hasattr(sys, "_global_active_engine") or sys._global_active_engine is None:
            sys._global_active_engine = LiveEngine()
            # Recover running state from disk to survive page refreshes (only on fresh server start)
            was_running = sys._global_active_engine.recovery.load_engine_status()
            if was_running and not sys._global_active_engine.running:
                try:
                    sys._global_active_engine.start()
                except Exception as e:
                    logger.error(f"Auto-recovery start failed on fresh server start: {e}")
                
    engine_inst = sys._global_active_engine
    st.session_state["live_engine"] = engine_inst

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
                try:
                    engine_inst.start()
                    st.toast("AutoTrader Live/Paper Engine started successfully!", icon="🟢")
                    st.rerun()
                except Exception as e:
                    st.sidebar.error(f"Failed to start: {e}")
        with col_stop:
            if st.button("⏹️ Stop Engine", disabled=not engine_inst.running, use_container_width=True):
                engine_inst.stop()
                st.toast("AutoTrader Live/Paper Engine stopped.", icon="🛑")
                st.rerun()

        status_text = "🟢 RUNNING" if engine_inst.running else "🛑 STOPPED"
        st.sidebar.markdown(f"Status: **{status_text}**")

        st.sidebar.write("")
        if st.sidebar.button("🧹 Reset Active Position & State", use_container_width=True):
            if engine_inst.running:
                engine_inst.stop()
            
            # Emergency exit square-off of active trade if open
            if engine_inst.active_trade and engine_inst.active_trade.is_open:
                st.toast("Triggering emergency square-off exit orders...", icon="🚨")
                try:
                    now = datetime.now()
                    if config.execution_mode == ExecutionMode.LIVE.value:
                        import asyncio
                        loop = asyncio.new_event_loop()
                        loop.run_until_complete(engine_inst.broker_executor.execute_exit_both(engine_inst.active_trade, now, ExitReason.MANUAL))
                        loop.close()
                    else:
                        engine_inst.paper_executor.execute_exit_both(engine_inst.active_trade, now, ExitReason.MANUAL)
                except Exception as square_err:
                    st.sidebar.error(f"Emergency square-off failed: {square_err}")
                
                # Update DB record with closed manual status
                engine_inst.active_trade.phase = TradePhase.CLOSED
                engine_inst.active_trade.exit_time = datetime.now()
                engine_inst.active_trade.exit_reason = ExitReason.MANUAL
                engine_inst.store.save_trade(engine_inst.active_trade)
            
            engine_inst.realized_pnl = 0.0
            engine_inst.active_trade = None
            engine_inst.recovery.save_state(0.0, None)
            from data.market_cache import market_cache
            market_cache.clear()
            st.toast("Active position, recovery state, and Cache wiped cleanly.", icon="🧹")
            st.rerun()
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
    tab_bt, tab_live, tab_hist = st.tabs([
        "📉 Backtest Engine (Backtest Mode Only)", 
        "🟢 Live Monitoring (Paper / Live Mode)", 
        "📜 Trade Journal (All Modes)"
    ])

    # -------------------------------------------------------------
    # TAB 1: BACKTESTER
    # -------------------------------------------------------------
    with tab_bt:
        st.subheader("Historical Simulation Replay")
        st.write("Replay historical tick data through the divergence matrix scanner to compute profitability.")

        # Observability banner for offline cache fallback
        if st.session_state.get("fallback_engaged", False):
            st.error("⚠️ ENGAGED OFFLINE CACHE FALLBACK: Live Nifty option chain fetch failed (invalid access token or rate limit). The system has automatically loaded from the offline cache, reducing the matrix scan scope to ATM-only strike pairs.")

        col_run, col_status = st.columns([1, 4])
        with col_run:
            run_btn = st.button("🚀 Run Backtest", use_container_width=True)

        if run_btn:
            # Clear previous fallback state
            st.session_state["fallback_engaged"] = False
            try:
                with st.spinner("Fetching option chain candles..."):
                    loader = HistoricalLoader()
                    days = loader.fetch_historical_data(
                        from_date=config.backtest_from_date,
                        to_date=config.backtest_to_date,
                        scan_range=config.pair_scan_range,
                        interval_minutes=config.candle_interval_minutes
                    )
                    
                    if getattr(loader, "fallback_engaged", False):
                        st.session_state["fallback_engaged"] = True
                
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
            c1, c2, c3, c4, c5 = st.columns(5)
            
            gross_pnl_color = "#10b981" if metrics["total_pnl"] >= 0 else "#ef4444"
            net_pnl_color = "#10b981" if metrics["total_net_pnl"] >= 0 else "#ef4444"
            
            c1.markdown(f'<div class="metric-card"><div class="metric-title">Gross P&L</div><div class="metric-value" style="color: {gross_pnl_color};">₹{metrics["total_pnl"]:,.2f}</div></div>', unsafe_allow_html=True)
            c2.markdown(f'<div class="metric-card"><div class="metric-title">Transaction Costs</div><div class="metric-value" style="color: #eab308;">₹{metrics["total_costs"]:,.2f}</div></div>', unsafe_allow_html=True)
            c3.markdown(f'<div class="metric-card"><div class="metric-title">Net P&L</div><div class="metric-value" style="color: {net_pnl_color};">₹{metrics["total_net_pnl"]:,.2f}</div></div>', unsafe_allow_html=True)
            c4.markdown(f'<div class="metric-card"><div class="metric-title">Win Rate</div><div class="metric-value" style="color: #60a5fa;">{metrics["win_rate"]}%</div></div>', unsafe_allow_html=True)
            c5.markdown(f'<div class="metric-card"><div class="metric-title">Max Drawdown (Net)</div><div class="metric-value" style="color: #f87171;">₹{metrics["max_drawdown"]:,.2f}</div></div>', unsafe_allow_html=True)

            # Equity Curve chart
            st.markdown("### Equity Curve")
            gross_equity = [config.total_capital]
            net_equity = [config.total_capital]
            for t in trades:
                gross_equity.append(gross_equity[-1] + t.combined_pnl)
                net_equity.append(net_equity[-1] + t.net_pnl)
            
            df_eq = pd.DataFrame({
                "Gross Portfolio Value": gross_equity,
                "Net Portfolio Value": net_equity
            })
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

        feed = getattr(engine_inst, "feed", None)
        if feed is not None and getattr(feed, "fallback_engaged", False):
            st.error(
                "⚠️ MARKET DATA FEED FAILURE: PAPER/LIVE execution is blocked. "
                "Synthetic prices are disabled and the market cache remains empty; "
                "restart only after restoring the Dhan feed."
            )
        
        # Display currently-held pair
        active_trade = engine_inst.active_trade
        
        # 1. Performance and Daily Session P&L Calculations
        total_pnl = engine_inst.realized_pnl
        active_pnl = active_trade.combined_pnl if (active_trade and active_trade.is_open) else 0.0
        total_day_pnl = total_pnl + active_pnl
        
        mc1, mc2, mc3 = st.columns(3)
        realized_color = "#10b981" if engine_inst.realized_pnl >= 0 else "#ef4444"
        active_color = "#10b981" if active_pnl >= 0 else "#ef4444"
        total_color = "#10b981" if total_day_pnl >= 0 else "#ef4444"
        
        mc1.markdown(f'<div class="metric-card"><div class="metric-title">Realized P&L</div><div class="metric-value" style="color: {realized_color};">₹{engine_inst.realized_pnl:,.2f}</div></div>', unsafe_allow_html=True)
        mc2.markdown(f'<div class="metric-card"><div class="metric-title">Active Position P&L</div><div class="metric-value" style="color: {active_color};">₹{active_pnl:,.2f}</div></div>', unsafe_allow_html=True)
        mc3.markdown(f'<div class="metric-card"><div class="metric-title">Total Day P&L</div><div class="metric-value" style="color: {total_color};">₹{total_day_pnl:,.2f}</div></div>', unsafe_allow_html=True)
        st.write("")

        if active_trade and active_trade.is_open:
            st.info(
                f"⚡ Currently holding open position: {display_trade_id(active_trade)} — "
                f"{active_trade.quantity:,} lots | "
                f"{units_per_leg(active_trade):,} units/leg | {daily_sl_status(active_trade)}"
            )
            
            # Derive order execution status for each leg
            ce_status = "FILLED"
            pe_status = "FILLED"
            if active_trade.phase == TradePhase.PHASE_2_SINGLE_LEG:
                if active_trade.winning_leg == "CE":
                    pe_status = "HEDGE CUT (CLOSED)"
                else:
                    ce_status = "HEDGE CUT (CLOSED)"
            elif active_trade.phase == TradePhase.CLOSED:
                ce_status = "CLOSED"
                pe_status = "CLOSED"
            
            lc1, lc2, lc3 = st.columns(3)
            with lc1:
                st.markdown(
                    f"""
                    <div style="background: #1e293b; padding: 15px; border-radius: 8px; border: 1px solid #3b82f6;">
                        <h4 style="margin: 0; color: #60a5fa;">CE Leg Status</h4>
                        <p style="margin: 5px 0 0 0; font-size: 1.2rem; font-weight: 700; color: white;">Strike: {active_trade.strike_ce} | Entry: ₹{active_trade.entry_ce_price:.2f}</p>
                        <p style="margin: 5px 0 0 0; font-size: 1rem; font-weight: 700; color: #e2e8f0;">Size: {active_trade.quantity:,} lots | {units_per_leg(active_trade):,} units/leg</p>
                        <p style="margin: 5px 0 0 0; font-size: 0.95rem; color: #94a3b8;">Status: <span style="color: #60a5fa; font-weight: 700;">{ce_status}</span></p>
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
                        <p style="margin: 5px 0 0 0; font-size: 1rem; font-weight: 700; color: #e2e8f0;">Size: {active_trade.quantity:,} lots | {units_per_leg(active_trade):,} units/leg</p>
                        <p style="margin: 5px 0 0 0; font-size: 0.95rem; color: #94a3b8;">Status: <span style="color: #34d399; font-weight: 700;">{pe_status}</span></p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            with lc3:
                pnl_style = "color: #10b981;" if active_trade.combined_pnl >= 0 else "color: #ef4444;"
                entry_time_str = active_trade.entry_time.strftime("%H:%M:%S") if active_trade.entry_time else "N/A"
                st.markdown(
                    f"""
                    <div style="background: #1e293b; padding: 15px; border-radius: 8px; border: 1px solid #fbbf24;">
                        <h4 style="margin: 0; color: #fbbf24;">Position Details</h4>
                        <p style="margin: 5px 0 0 0; font-size: 1.1rem; color: white;">Phase: {active_trade.phase.value} | PnL: <span style="{pnl_style} font-weight:700;">₹{active_trade.combined_pnl:.2f}</span></p>
                        <p style="margin: 5px 0 0 0; font-size: 0.9rem; color: #94a3b8;">Entry Time: {entry_time_str}</p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
        else:
            st.info("No active open position at this moment.")

        # Live Activity Log Console (newest logs at the top)
        st.markdown("### 🖥️ Engine Activity Console")
        st.markdown("<p style='color: #94a3b8; font-size: 0.9rem; margin-top: -10px;'>Real-time strategy pipeline execution logs (newest entries first, auto-refresh active)</p>", unsafe_allow_html=True)
        log_text = "\n".join(reversed(engine_inst.activity_log)) if engine_inst.activity_log else "Engine not started or no log entries yet."
        st.text_area("Activity Log", value=log_text, height=350, disabled=True, label_visibility="collapsed")

    # -------------------------------------------------------------
    # TAB 3: TRADE JOURNAL
    # -------------------------------------------------------------
    with tab_hist:
        st.subheader("Historical Trade Journal")
        
        filter_mode = st.selectbox(
            "Filter Journal by Execution Mode",
            options=["All Modes", "Backtest Mode Only (June 2026)", "Paper / Live Mode Only"],
            index=0
        )
        
        all_trades = store.get_all_trades()
        
        # Filter trades based on date heuristics (June 2026 backtest window vs live/paper runs)
        if filter_mode == "Backtest Mode Only (June 2026)":
            trades_to_show = [t for t in all_trades if t.entry_time and t.entry_time.year == 2026 and t.entry_time.month == 6]
        elif filter_mode == "Paper / Live Mode Only":
            trades_to_show = [t for t in all_trades if not (t.entry_time and t.entry_time.year == 2026 and t.entry_time.month == 6)]
        else:
            trades_to_show = all_trades

        if trades_to_show:
            rows = []
            for t in trades_to_show:
                rows.append({
                    "Trade ID": display_trade_id(t),
                    "Daily SL": daily_sl_status(t),
                    "Direction": t.direction.value,
                    "Lots": t.quantity,
                    "Units / Leg": units_per_leg(t),
                    "CE Strike": str(t.strike_ce),
                    "PE Strike": str(t.strike_pe),
                    "Entry Time": t.entry_time.strftime("%m-%d %H:%M:%S") if t.entry_time else None,
                    "CE Entry": t.entry_ce_price,
                    "PE Entry": t.entry_pe_price,
                    "Combined Entry (₹)": round(t.entry_ce_price + t.entry_pe_price, 2),
                    "Regime": t.regime_at_entry.value,
                    "Phase": t.phase.value,
                    "Hedge-Cut Time": t.hedge_cut_time.strftime("%H:%M:%S") if t.hedge_cut_time else None,
                    "CE Exit": t.exit_ce_price if t.exit_ce_price is not None else None,
                    "PE Exit": t.exit_pe_price if t.exit_pe_price is not None else None,
                    "Exit Time": t.exit_time.strftime("%m-%d %H:%M:%S") if t.exit_time else "OPEN",
                    "Reason": {
                        "GIVEBACK": "Trailing Stop-Loss (Profit Giveback)",
                        "TARGET_HIT": "Take-Profit Target Hit",
                        "ROTATION": "Option Pair Rotation (Strike Switch)",
                        "HEDGE_CUT": "Hedge Leg Cut",
                        "EOD_SQUARE_OFF": "End of Day Auto-Exit (15:20)",
                        "PARTIAL_FILL_ABORT": "Partial Fill Abort",
                        "MANUAL": "Manual Reset / Emergency Exit"
                    }.get(t.exit_reason.value, t.exit_reason.value) if t.exit_reason else None,
                    "Gross PnL (₹)": t.combined_pnl,
                    "Transaction Costs (₹)": t.transaction_costs,
                    "Net PnL (₹)": t.net_pnl
                })
            
            df_hist = pd.DataFrame(rows)
            st.dataframe(df_hist, use_container_width=True)
        else:
            st.info("No trades matched the selected filter mode.")

    # Auto-refresh UI when the engine is running to pull latest activity logs
    if getattr(engine_inst, "running", False):
        time.sleep(3)
        st.rerun()

if __name__ == "__main__":
    main()
