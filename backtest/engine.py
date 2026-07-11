import logging
from datetime import datetime, time, timedelta
from typing import List, Dict, Any, Optional
from config.settings import TradingConfig
from core.models import Trade, DaySession, ExecutionSignal, Candle, PairedCandle
from core.enums import MarketRegime, TradePhase, ExitReason, SignalType, OrderType
from data.market_cache import market_cache
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
from backtest.simulated_fill import SimulatedFill
from execution.crash_recovery import CrashRecovery
from monitoring.health_monitor import HealthMonitor

logger = logging.getLogger("AutoTrader")

class BacktestEngine:
    """
    Replays historical option candles through the AutoTrader v6 strategy.
    Maintains 100% parity with live execution by feeding candles into MarketCache
    and using the exact same strategy components and ExecutionQueue.
    """
    def __init__(self, config: TradingConfig) -> None:
        self.config = config
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
        self.filler = SimulatedFill()
        self.recovery = CrashRecovery()
        self.health_monitor = HealthMonitor()

        # State tracking
        self.realized_pnl = 0.0
        self.active_trade: Optional[Trade] = None
        self.trades: List[Trade] = []

    def run(self, days_data: List[Any]) -> List[Trade]:
        """Runs backtest over loaded list of HistoricalDayData."""
        self.trades.clear()
        self.realized_pnl = 0.0
        self.active_trade = None

        for day in days_data:
            logger.info(f"--- Starting Backtest Day: {day.date} ---")
            self._run_day_session(day)
            
        logger.info(f"Backtest complete. Total trades: {len(self.trades)}, Realized PnL: ₹{self.realized_pnl:.2f}")
        return self.trades

    def _run_day_session(self, day: Any) -> None:
        # Reset daily session state
        day_session = DaySession(date=day.date, realized_pnl=0.0)
        
        # Sliding windows for regime detection
        spot_closes: List[float] = []
        spot_highs: List[float] = []
        spot_lows: List[float] = []
        vwap_values: List[float] = []
        tr_values: List[float] = []
        atr_values: List[float] = []

        cumulative_volume = 0.0
        cumulative_vwap_sum = 0.0

        for ts in day.timestamps:
            # 1. Update MarketCache for all strikes at timestamp ts
            market_cache.clear()
            strike_data = day.candles[ts]
            
            atm_ce = strike_data.get("ATM", {}).get("CE")
            atm_pe = strike_data.get("ATM", {}).get("PE")

            if not atm_ce or not atm_pe:
                continue

            # Populate cache with all strikes
            for strike, legs in strike_data.items():
                if "CE" in legs:
                    c = legs["CE"]
                    market_cache.update_option(strike, "CE", {
                        "open": c.open, "high": c.high, "low": c.low, "close": c.close,
                        "last": c.close, "volume": c.volume, "oi": c.oi, "timestamp": ts
                    })
                if "PE" in legs:
                    p = legs["PE"]
                    market_cache.update_option(strike, "PE", {
                        "open": p.open, "high": p.high, "low": p.low, "close": p.close,
                        "last": p.close, "volume": p.volume, "oi": p.oi, "timestamp": ts
                    })

            # Calculate synthetic spot price (put-call parity proxy for Q2)
            spot_close = 24000.0 + atm_ce.close - atm_pe.close
            spot_open = 24000.0 + atm_ce.open - atm_pe.open
            spot_high = max(spot_open, spot_close) + (atm_ce.high - atm_ce.open) + (atm_pe.high - atm_pe.open)
            spot_low = min(spot_open, spot_close) - (atm_ce.open - atm_ce.low) - (atm_pe.open - atm_pe.low)

            market_cache.update_spot(spot_close, ts)

            # Update sliding windows
            spot_closes.append(spot_close)
            spot_highs.append(spot_high)
            spot_lows.append(spot_low)

            # True Range and ATR (10-period)
            if len(spot_closes) == 1:
                tr = spot_high - spot_low
            else:
                prev_close = spot_closes[-2]
                tr = max(spot_high - spot_low, abs(spot_high - prev_close), abs(spot_low - prev_close))
            tr_values.append(tr)
            
            # Simple 10-period ATR
            if len(tr_values) >= 10:
                atr_values.append(sum(tr_values[-10:]) / 10.0)
            else:
                atr_values.append(tr)

            # VWAP (volume-weighted spot close)
            vol = atm_ce.volume + atm_pe.volume
            if vol > 0:
                cumulative_volume += vol
                cumulative_vwap_sum += spot_close * vol
                vwap = cumulative_vwap_sum / cumulative_volume
            else:
                vwap = spot_close if not vwap_values else vwap_values[-1]
            vwap_values.append(vwap)
            market_cache.update_vwap(vwap, ts)

            # Time limits
            current_time_only = ts.time()
            start_hour, start_min = map(int, self.config.scan_start.split(":"))
            end_hour, end_min = map(int, self.config.scan_end.split(":"))
            entry_cutoff_hour, entry_cutoff_min = map(int, self.config.last_entry_time.split(":"))

            trading_hours = time(start_hour, start_min) <= current_time_only < time(end_hour, end_min)
            last_entry_passed = current_time_only >= time(entry_cutoff_hour, entry_cutoff_min)
            is_preclose = current_time_only >= time(15, 0) # 15:00 preclose window

            # Detect market regime
            regime, spot_trend = self.regime_detector.detect_regime(
                spot_closes=spot_closes,
                spot_highs=spot_highs,
                spot_lows=spot_lows,
                vwap_values=vwap_values,
                atr_values=atr_values,
                atm_strike=market_cache.get_atm_strike()
            )

            # Check daily circuit breaker
            breaker_hit = self.circuit_breaker.is_breaker_triggered(day_session.realized_pnl, self.config)
            if breaker_hit:
                day_session.circuit_breaker_hit = True

            # 2. RUN STRATEGY PIPELINE
            # Target option prices for active trade updates
            if self.active_trade and self.active_trade.is_open:
                # Update current active trade prices in engine
                ce_curr = market_cache.get_option(self.active_trade.strike_ce, "CE")
                pe_curr = market_cache.get_option(self.active_trade.strike_pe, "PE")
                
                if ce_curr and pe_curr:
                    ce_p = ce_curr["last"]
                    pe_p = pe_curr["last"]
                else:
                    ce_p = self.active_trade.ce_current_price
                    pe_p = self.active_trade.pe_current_price

                # Check EOD Flatten (15:20 IST cutoff)
                if current_time_only >= time(end_hour, end_min):
                    self.queue.enqueue(ExecutionSignal(
                        type=SignalType.EXIT_BOTH,
                        timestamp=ts,
                        trade_id=self.active_trade.id,
                        reason="EOD_SQUARE_OFF"
                    ))
                else:
                    # Regular exits (Phase 1)
                    if self.active_trade.phase == TradePhase.PHASE_1_BOTH_LEGS:
                        # Check exit manager
                        exit_reason = self.exit_manager.check_exits(
                            trade=self.active_trade,
                            ce_price=ce_p,
                            pe_price=pe_p,
                            iv_percentile=50.0,  # normal IV
                            is_preclose=is_preclose,
                            config=self.config
                        )
                        if exit_reason:
                            self.queue.enqueue(ExecutionSignal(
                                type=SignalType.EXIT_BOTH,
                                timestamp=ts,
                                trade_id=self.active_trade.id,
                                reason=exit_reason.value
                            ))
                        else:
                            # Check hedge cut (Directional only)
                            if self.active_trade.regime_at_entry == MarketRegime.DIRECTIONAL:
                                if self.hedge_cut_manager.should_hedge_cut(self.active_trade, ce_p, pe_p, self.config):
                                    self.queue.enqueue(ExecutionSignal(
                                        type=SignalType.HEDGE_CUT,
                                        timestamp=ts,
                                        trade_id=self.active_trade.id
                                    ))
                                else:
                                    # Check rotation
                                    self._evaluate_rotation_sync(ts, regime, day_session)
                            else:
                                # Sideways mode check rotation
                                self._evaluate_rotation_sync(ts, regime, day_session)

                    # Single leg exit trailing (Phase 2)
                    elif self.active_trade.phase == TradePhase.PHASE_2_SINGLE_LEG:
                        exit_reason = self.single_leg_exit_manager.check_single_leg_exit(
                            trade=self.active_trade,
                            ce_price=ce_p,
                            pe_price=pe_p,
                            config=self.config
                        )
                        if exit_reason:
                            self.queue.enqueue(ExecutionSignal(
                                type=SignalType.EXIT_BOTH,
                                timestamp=ts,
                                trade_id=self.active_trade.id,
                                reason=exit_reason.value
                            ))
                        else:
                            # Rotation checks allowed if regime has flipped to Sideways
                            if regime == MarketRegime.SIDEWAYS:
                                self._evaluate_rotation_sync(ts, regime, day_session)

            else:
                # No active position -> check entry conditions
                if trading_hours and not last_entry_passed and not breaker_hit:
                    # Run matrix scan
                    candidates = self.generator.generate_candidates()
                    
                    # Pre-Cartesian filter CE/PE strikes
                    ce_strikes = [c[0] for c in candidates]
                    pe_strikes = [c[1] for c in candidates]
                    
                    filtered_ce = self.liq_filter.filter_strikes(ce_strikes, "CE", self.config)
                    filtered_pe = self.liq_filter.filter_strikes(pe_strikes, "PE", self.config)
                    
                    # Generate filtered pairs
                    filtered_candidates = []
                    for ce in filtered_ce:
                        for pe in filtered_pe:
                            filtered_candidates.append((ce, pe))
                            
                    # Divergence scan
                    scanned = self.scanner.scan_candidates(filtered_candidates)
                    
                    # Evaluate entry signals
                    survivors = self.entry_signal.evaluate_signals(scanned, regime, spot_trend, self.config)
                    
                    # Rank candidates
                    top_candidate = self.ranker.rank_candidates(survivors, self.config)
                    
                    if top_candidate:
                        ce_data = market_cache.get_option(top_candidate.ce_strike, "CE")
                        pe_data = market_cache.get_option(top_candidate.pe_strike, "PE")
                        
                        if ce_data and pe_data:
                            ce_last = ce_data["last"]
                            pe_last = pe_data["last"]
                            
                            # Quantity sizing
                            qty = self.sizer.calculate_lots(ce_last, pe_last, self.config)
                            
                            if qty > 0:
                                # Trade Plan
                                plan = self.planner.plan_trade(
                                    candidate=top_candidate,
                                    regime=regime,
                                    quantity=qty,
                                    ce_price=ce_last,
                                    pe_price=pe_last,
                                    config=self.config
                                )
                                
                                # Validate Entry
                                is_valid, reason = self.validator.validate_entry(
                                    plan=plan,
                                    realized_pnl=day_session.realized_pnl,
                                    active_trade=self.active_trade,
                                    config=self.config
                                )
                                
                                if is_valid:
                                    self.queue.enqueue(ExecutionSignal(
                                        type=SignalType.ENTRY,
                                        timestamp=ts,
                                        trade_plan=plan
                                    ))

            # 3. PROCESS EXECUTION QUEUE SYNCHRONOUSLY
            self.queue.process_pending_sync(lambda sig: self._handle_execution_signal(sig, ts, day_session))

    def _evaluate_rotation_sync(self, ts: datetime, regime: MarketRegime, day_session: DaySession) -> None:
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
            should_rotate, reason = self.rotation_engine.should_rotate(
                active_trade=self.active_trade,
                top_candidate=top_candidate,
                current_time=ts,
                current_regime=regime,
                config=self.config
            )
            
            if should_rotate:
                ce_data = market_cache.get_option(top_candidate.ce_strike, "CE")
                pe_data = market_cache.get_option(top_candidate.pe_strike, "PE")
                
                if ce_data and pe_data:
                    qty = self.sizer.calculate_lots(ce_data["last"], pe_data["last"], self.config)
                    if qty > 0:
                        new_plan = self.planner.plan_trade(
                            candidate=top_candidate,
                            regime=regime,
                            quantity=qty,
                            ce_price=ce_data["last"],
                            pe_price=pe_data["last"],
                            config=self.config
                        )
                        # Queue rotation
                        self.queue.enqueue(ExecutionSignal(
                            type=SignalType.ROTATION,
                            timestamp=ts,
                            trade_id=self.active_trade.id,
                            trade_plan=new_plan,
                            reason=reason
                        ))

    def _handle_execution_signal(self, signal: ExecutionSignal, ts: datetime, day_session: DaySession) -> None:
        chain = market_cache.get_option_chain()

        if signal.type == SignalType.ENTRY:
            # Simulated entry
            plan = signal.trade_plan
            ce_strike = plan.scored_candidate.ce_strike
            pe_strike = plan.scored_candidate.pe_strike
            
            ce_data = chain.get(ce_strike, {}).get("CE")
            pe_data = chain.get(pe_strike, {}).get("PE")
            
            if ce_data and pe_data:
                # Sim fill CE + PE
                paired_candle = PairedCandle(
                    timestamp=ts,
                    ce_open=ce_data["open"], ce_high=ce_data["high"], ce_low=ce_data["low"], ce_close=ce_data["close"], ce_volume=ce_data["volume"],
                    pe_open=pe_data["open"], pe_high=pe_data["high"], pe_low=pe_data["low"], pe_close=pe_data["close"], pe_volume=pe_data["volume"]
                )
                try:
                    trade = self.filler.fill_entry(plan, paired_candle)
                    self.active_trade = trade
                    self.trades.append(trade)
                    day_session.trades.append(trade)
                    self.decision_memory.log_entry(trade.id, plan)
                except Exception as e:
                    logger.error(f"Failed to fill entry signal: {e}")

        elif signal.type == SignalType.EXIT_BOTH:
            if self.active_trade and self.active_trade.is_open:
                # Sim exit
                ce_data = chain.get(self.active_trade.strike_ce, {}).get("CE")
                pe_data = chain.get(self.active_trade.strike_pe, {}).get("PE")
                
                if ce_data and pe_data:
                    paired_candle = PairedCandle(
                        timestamp=ts,
                        ce_open=ce_data["open"], ce_high=ce_data["high"], ce_low=ce_data["low"], ce_close=ce_data["close"], ce_volume=ce_data["volume"],
                        pe_open=pe_data["open"], pe_high=pe_data["high"], pe_low=pe_data["low"], pe_close=pe_data["close"], pe_volume=pe_data["volume"]
                    )
                    
                    reason_str = signal.reason or "MANUAL"
                    reason_enum = ExitReason(reason_str)
                    
                    if self.active_trade.phase == TradePhase.PHASE_1_BOTH_LEGS:
                        self.filler.fill_exit_both(self.active_trade, paired_candle, reason_enum)
                    else:
                        self.filler.fill_single_leg_exit(self.active_trade, paired_candle, reason_enum)
                        
                    # Add to session realized PnL
                    day_session.close_trade(self.active_trade)
                    self.realized_pnl = round(self.realized_pnl + self.active_trade.combined_pnl, 2)
                    self.decision_memory.log_exit(self.active_trade.id, self.active_trade, reason_str)
                    
                    self.active_trade = None

        elif signal.type == SignalType.HEDGE_CUT:
            if self.active_trade and self.active_trade.phase == TradePhase.PHASE_1_BOTH_LEGS:
                ce_data = chain.get(self.active_trade.strike_ce, {}).get("CE")
                pe_data = chain.get(self.active_trade.strike_pe, {}).get("PE")
                
                if ce_data and pe_data:
                    paired_candle = PairedCandle(
                        timestamp=ts,
                        ce_open=ce_data["open"], ce_high=ce_data["high"], ce_low=ce_data["low"], ce_close=ce_data["close"], ce_volume=ce_data["volume"],
                        pe_open=pe_data["open"], pe_high=pe_data["high"], pe_low=pe_data["low"], pe_close=pe_data["close"], pe_volume=pe_data["volume"]
                    )
                    self.filler.fill_hedge_cut(self.active_trade, paired_candle)
                    self.decision_memory.log_hedge_cut(
                        self.active_trade.id,
                        self.active_trade.losing_leg,
                        self.active_trade.losing_leg_exit_price,
                        self.active_trade.losing_leg_pnl
                    )

        elif signal.type == SignalType.ROTATION:
            if self.active_trade and self.active_trade.is_open:
                # 1. Exit active trade first
                ce_data = chain.get(self.active_trade.strike_ce, {}).get("CE")
                pe_data = chain.get(self.active_trade.strike_pe, {}).get("PE")
                
                if ce_data and pe_data:
                    paired_candle = PairedCandle(
                        timestamp=ts,
                        ce_open=ce_data["open"], ce_high=ce_data["high"], ce_low=ce_data["low"], ce_close=ce_data["close"], ce_volume=ce_data["volume"],
                        pe_open=pe_data["open"], pe_high=pe_data["high"], pe_low=pe_data["low"], pe_close=pe_data["close"], pe_volume=pe_data["volume"]
                    )
                    
                    if self.active_trade.phase == TradePhase.PHASE_1_BOTH_LEGS:
                        self.filler.fill_exit_both(self.active_trade, paired_candle, ExitReason.ROTATION)
                    else:
                        self.filler.fill_single_leg_exit(self.active_trade, paired_candle, ExitReason.ROTATION)
                        
                    day_session.close_trade(self.active_trade)
                    self.realized_pnl = round(self.realized_pnl + self.active_trade.combined_pnl, 2)
                    
                    # Set rotation cooldown on rotated strikes
                    self.rotation_engine.set_cooldown(self.active_trade.strike_ce, self.active_trade.strike_pe, ts, self.config)
                    
                    old_id = self.active_trade.id
                    old_pnl = self.active_trade.combined_pnl
                    
                    self.active_trade = None
                    
                    # 2. Enter new trade immediately
                    new_plan = signal.trade_plan
                    new_ce_strike = new_plan.scored_candidate.ce_strike
                    new_pe_strike = new_plan.scored_candidate.pe_strike
                    
                    new_ce_data = chain.get(new_ce_strike, {}).get("CE")
                    new_pe_data = chain.get(new_pe_strike, {}).get("PE")
                    
                    if new_ce_data and new_pe_data:
                        new_paired_candle = PairedCandle(
                            timestamp=ts,
                            ce_open=new_ce_data["open"], ce_high=new_ce_data["high"], ce_low=new_ce_data["low"], ce_close=new_ce_data["close"], ce_volume=new_ce_data["volume"],
                            pe_open=new_pe_data["open"], pe_high=new_pe_data["high"], pe_low=new_pe_data["low"], pe_close=new_pe_data["close"], pe_volume=new_pe_data["volume"]
                        )
                        try:
                            trade = self.filler.fill_entry(new_plan, new_paired_candle)
                            self.active_trade = trade
                            self.trades.append(trade)
                            day_session.trades.append(trade)
                            self.decision_memory.log_rotation(old_id, old_pnl, new_plan, signal.reason or "Better score")
                            self.decision_memory.log_entry(trade.id, new_plan)
                        except Exception as e:
                            logger.error(f"Failed to fill entry signal during rotation: {e}")
