"""
Backtest Engine
────────────────
§7.1: Replay historical data, no real-time API calls, no orders.

This is the agreed starting point: "Do not go to paper or live trading
until a backtest has run against real historical data."

Flow per day:
  1. Filter candles to trading window (09:30–15:00)
  2. For each 2-min candle:
     a. Check daily circuit breaker (§5.2)
     b. If position open → check exits (per-trade stop, trailing, EOD)
     c. If no position → compute velocity divergence → check entry band
  3. At 15:00: force-flatten any open position (Option A confirmed)
  4. Record session results
"""

from __future__ import annotations

from datetime import datetime, time as dtime
from typing import List, Optional
from dataclasses import asdict

from loguru import logger

from core.models import DayBucket, DaySession, Trade, PairedCandle
from core.enums import ExitReason
from config.settings import TradingConfig
from strategy.divergence_scanner import DivergenceScanner
from strategy.entry_signal import EntryFilter
from strategy.exit_manager import ExitManager
from strategy.daily_circuit_breaker import DailyCircuitBreaker
from backtest.simulated_fill import SimulatedFill
from backtest.results import BacktestResults


class BacktestEngine:
    """
    Replays historical day buckets through the strategy.
    Produces BacktestResults for reporting and UI display.
    """

    def __init__(self, config: TradingConfig = None):
        self.config = config or TradingConfig.load()
        self._scanner = DivergenceScanner()
        self._entry_filter = EntryFilter()
        self._exit_manager = ExitManager()
        self._circuit_breaker = DailyCircuitBreaker()
        self._fill = SimulatedFill()

    def run(self, day_buckets: List[DayBucket]) -> BacktestResults:
        """
        Run backtest across all day buckets.

        Args:
            day_buckets: List of DayBucket, one per trading day,
                         each containing aligned 2-min CE+PE candles.

        Returns:
            BacktestResults with all trades and statistics.
        """
        results = BacktestResults(
            config_snapshot=asdict(self.config),
            start_date=day_buckets[0].date if day_buckets else None,
            end_date=day_buckets[-1].date if day_buckets else None,
        )

        logger.info(
            f"Starting backtest: {len(day_buckets)} days, "
            f"capital=₹{self.config.total_capital:,.0f}, "
            f"divergence band={self.config.divergence_min_pct}–"
            f"{self.config.divergence_max_pct}%"
        )

        for bucket in day_buckets:
            session = self._run_day(bucket)
            results.add_session(session)

            logger.info(
                f"Day {bucket.date.strftime('%Y-%m-%d')}: "
                f"{session.trade_count} trades, "
                f"PnL=₹{session.realized_pnl:.2f}"
                f"{' [BREAKER]' if session.circuit_breaker_hit else ''}"
            )

        logger.info(
            f"Backtest complete: {results.total_trades} trades, "
            f"PnL=₹{results.total_pnl:,.2f}, "
            f"Win rate={results.win_rate}%"
        )

        return results

    def _run_day(self, bucket: DayBucket) -> DaySession:
        """
        Process one trading day.

        §3: No scanning before 09:30 or after 15:00.
        §5.2: Check circuit breaker before every potential entry.
        Force-flatten at 15:00 (Option A).
        """
        session = DaySession(date=bucket.date)

        if bucket.is_empty:
            return session

        # Parse trading window times
        start_h, start_m = map(int, self.config.scan_start.split(":"))
        end_h, end_m = map(int, self.config.scan_end.split(":"))
        window_start = dtime(start_h, start_m)
        window_end = dtime(end_h, end_m)

        for candle in bucket.candles:
            candle_time = candle.timestamp.time()

            # §3: Skip candles outside trading window
            if candle_time < window_start:
                continue
            if candle_time >= window_end:
                # Force-flatten any open position at EOD
                self._handle_eod(session, candle)
                break

            # §5.2: Check circuit breaker first
            if session.circuit_breaker_hit:
                # Only manage existing position, no new entries
                if session.open_trade:
                    self._manage_position(session, candle)
                continue

            if self._circuit_breaker.is_breaker_hit(session, self.config):
                if session.open_trade:
                    self._manage_position(session, candle)
                continue

            # If we have an open trade, manage it
            if session.open_trade is not None:
                self._manage_position(session, candle)
            else:
                # Look for entry signal
                self._scan_for_entry(session, candle)

        # Handle case where we never hit the window_end candle
        # (data might end before 15:00)
        if session.open_trade is not None and bucket.candles:
            last_candle = bucket.candles[-1]
            self._force_exit(
                session, last_candle,
                ExitReason.EOD_FLATTEN,
            )

        return session

    def _scan_for_entry(
        self, session: DaySession, candle: PairedCandle
    ) -> None:
        """
        Compute velocity divergence and check entry conditions.

        Step 2: Velocity_CE and Velocity_PE per candle
        Step 3: Filter by 1–1.5% band
        Step 4: Execute 2-contract basket entry
        """
        # Can we open a new trade?
        if not self._circuit_breaker.can_open_new_trade(session, self.config):
            return

        # Compute velocity
        velocity = self._scanner.compute_velocity(candle)

        # Check entry band
        signal = self._entry_filter.evaluate(velocity, candle, self.config)

        if signal is None:
            return  # No qualifying divergence

        # Fill the entry (both legs bought)
        trade = self._fill.fill_entry(signal, self.config)

        if trade is None:
            return  # Sizing failed

        session.trades.append(trade)

    def _manage_position(
        self, session: DaySession, candle: PairedCandle
    ) -> None:
        """
        Update current prices and check all exit conditions.
        """
        trade = session.open_trade
        if trade is None:
            return

        # Update current prices
        trade.current_ce_price = candle.ce_close
        trade.current_pe_price = candle.pe_close

        # Check all exits (EOD, per-trade stop, trailing stop)
        exit_reason = self._exit_manager.check_all_exits(
            trade=trade,
            current_time=candle.timestamp.time(),
            config=self.config,
        )

        if exit_reason is not None:
            self._execute_exit(session, trade, candle, exit_reason)

    def _handle_eod(
        self, session: DaySession, candle: PairedCandle
    ) -> None:
        """Force-flatten at EOD (§3, Option A confirmed)."""
        trade = session.open_trade
        if trade is None:
            return

        trade.current_ce_price = candle.ce_close
        trade.current_pe_price = candle.pe_close

        self._execute_exit(
            session, trade, candle, ExitReason.EOD_FLATTEN,
        )

    def _force_exit(
        self, session: DaySession, candle: PairedCandle,
        reason: ExitReason,
    ) -> None:
        """Force exit with given reason."""
        trade = session.open_trade
        if trade is None:
            return

        trade.current_ce_price = candle.ce_close
        trade.current_pe_price = candle.pe_close

        self._execute_exit(session, trade, candle, reason)

    def _execute_exit(
        self,
        session: DaySession,
        trade: Trade,
        candle: PairedCandle,
        reason: ExitReason,
    ) -> None:
        """Execute an exit and record results."""
        self._fill.fill_exit(
            trade=trade,
            ce_price=candle.ce_close,
            pe_price=candle.pe_close,
            exit_time=candle.timestamp,
            reason=reason,
        )

        # Record realized PnL
        session.close_trade(trade)

        logger.debug(
            f"  Trade {trade.id} closed: {reason.value}, "
            f"PnL=₹{trade.combined_pnl:.2f}, "
            f"Day total=₹{session.realized_pnl:.2f}"
        )
