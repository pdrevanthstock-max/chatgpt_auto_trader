"""
Trading Scheduler

Runs the Trading Engine continuously during market hours.

Phases:
  09:15 – 09:30  MONITORING   Observe market, determine trend, DO NOT trade
  09:30 – 15:00  TRADING      Execute trades when conditions match
  15:00+         CLOSED       Stop scanning, manage only existing positions

Risk Rules:
  • Per-trade SL   : 2%
  • Daily loss cap : 3% of capital → stops trading for the day
"""

import time
import json
from datetime import datetime, time as dtime
from pathlib import Path

from engine.trading_engine import TradingEngine
from alpha.market_state import MarketState
from alpha.option_chain import OptionChain
from alpha.strike_selector import StrikeSelector
from config.constants import DEFAULT_CAPITAL


class TradingScheduler:

    MONITOR_START = dtime(9, 15)    # start watching market
    TRADE_START = dtime(9, 30)      # start executing trades
    MARKET_CLOSE = dtime(15, 0)     # stop opening new trades
    DAILY_LOSS_LIMIT = 0.03         # 3% of capital

    def __init__(self):

        self.engine = TradingEngine()

        self.market_state = MarketState()

        self.running = False

    # ----------------------------------------------------------
    # MAIN LOOP
    # ----------------------------------------------------------

    def start(self, interval=30):

        self.running = True

        print("=" * 80)
        print("AUTO TRADING STARTED")
        print(f"Monitor Phase : {self.MONITOR_START} – {self.TRADE_START}")
        print(f"Trading Phase : {self.TRADE_START} – {self.MARKET_CLOSE}")
        print(f"Interval      : {interval}s")
        print(f"Daily Loss Cap: {self.DAILY_LOSS_LIMIT * 100}% of ₹{DEFAULT_CAPITAL}")
        print("=" * 80)

        try:

            while self.running:

                print()
                print("=" * 80)
                print(datetime.now())
                print("=" * 80)

                now = datetime.now().time()

                # ---- Before market ----

                if now < self.MONITOR_START:

                    print("Market not open yet — waiting...")
                    print(f"Monitoring starts at {self.MONITOR_START}")
                    time.sleep(interval)
                    continue

                # ---- Monitoring phase (9:15 - 9:30) ----

                if self.MONITOR_START <= now < self.TRADE_START:

                    self._monitor_market()

                    print()
                    print(f"Monitoring phase — trading starts at {self.TRADE_START}")
                    print(f"Sleeping {interval} seconds...")

                    time.sleep(interval)
                    continue

                # ---- After market close ----

                if now > self.MARKET_CLOSE:

                    # If we still have a position, keep managing it
                    if self.engine.trade_manager.has_position():

                        print("Market closed — managing existing position...")

                        try:
                            result = self.engine.manage_position()
                            self._print_summary(result)
                        except Exception as e:
                            print(f"Error managing position: {e}")

                        time.sleep(interval)
                        continue

                    print(f"Market closed ({self.MARKET_CLOSE}) — stopping")
                    self._print_daily_stats()
                    self.running = False
                    break

                # ---- Daily loss limit check ----

                if not self._check_daily_risk():

                    print()
                    print("=" * 80)
                    print("DAILY LOSS LIMIT REACHED — STOPPING")
                    print("=" * 80)

                    self._print_daily_stats()
                    self.running = False
                    break

                # ---- Trading phase (9:30 - 15:00) ----

                try:

                    result = self.engine.run()

                    self._print_summary(result)

                except Exception as e:

                    print()
                    print("ENGINE ERROR")
                    print(e)
                    import traceback
                    traceback.print_exc()

                print()
                print(f"Sleeping {interval} seconds...")

                time.sleep(interval)

        except KeyboardInterrupt:

            print()
            print("=" * 80)
            print("TRADING STOPPED BY USER")
            print("=" * 80)

            self._print_daily_stats()
            self.running = False

    def stop(self):

        self.running = False

    # ----------------------------------------------------------
    # MONITORING PHASE (9:15 – 9:30)
    # ----------------------------------------------------------

    def _monitor_market(self):
        """
        Download option chain and observe market direction.
        Updates MarketState so that when trading starts at 9:30,
        the system already knows the trend.
        """

        print()
        print("-" * 40)
        print("MONITORING MARKET")
        print("-" * 40)

        try:

            chain = OptionChain().download()

            spot = chain["spot"]

            selector = StrikeSelector(chain)
            atm = selector.get_atm()

            self.market_state.update(spot, atm)

            movement = self.market_state.movement()

            if movement > 0:
                trend = "BULLISH"
            elif movement < 0:
                trend = "BEARISH"
            else:
                trend = "NEUTRAL"

            print(f"Spot     : {spot}")
            print(f"ATM      : {atm}")
            print(f"Movement : {movement:+.2f}")
            print(f"Trend    : {trend}")

            if self.market_state.previous_spot:
                print(f"Previous : {self.market_state.previous_spot}")

        except Exception as e:

            print(f"Monitor error: {e}")

    # ----------------------------------------------------------
    # DISPLAY SUMMARY
    # ----------------------------------------------------------

    def _print_summary(self, result):

        print()
        print("=" * 80)
        print("ENGINE SUMMARY")
        print("=" * 80)

        mode = result.get("mode", "UNKNOWN")

        print("Mode :", mode)

        if mode == "ENTRY":

            print("Direction :", result["decision"]["direction"])
            print("CE Strike :", result["best_pair"]["ce_strike"])
            print("PE Strike :", result["best_pair"]["pe_strike"])
            print("Score     :", round(result["score"], 4))

        elif mode == "MANAGE":

            position = result["position"]

            print("Managing Existing Position")
            print("Direction :", position["direction"])
            print("Entry     :", position["entry_price"])
            print("Current   :", position.get("current_price"))
            print("Stop Loss :", position.get("stop_loss"))
            print("PnL       :", position.get("pnl"))
            print("Status    :", position.get("status"))

        elif mode == "EXIT":

            position = result["position"]

            print("*** TRADE CLOSED ***")
            print("Direction :", position["direction"])
            print("Entry     :", position["entry_price"])
            print("Exit      :", position["exit_price"])
            print("PnL       :", position["pnl"])
            print("Reason    :", position["exit_reason"])

            self._print_daily_stats()

        elif mode == "NO_TRADE":

            print("Reason :", result.get("reason", "N/A"))

        elif mode in ("HOLD", "REVERSE"):

            print("Direction :", result["decision"]["direction"])

    # ----------------------------------------------------------
    # DAILY RISK CHECK
    # ----------------------------------------------------------

    def _check_daily_risk(self):
        """
        Returns False if daily loss limit (3%) has been reached.
        Reads trade_history.json — safe if file is missing.
        """

        history_file = Path("database/trade_history.json")

        if not history_file.exists():
            return True

        try:

            with open(history_file) as f:
                trades = json.load(f)

        except (json.JSONDecodeError, IOError):
            return True

        if not trades:
            return True

        today = datetime.now().date()
        daily_pnl = 0

        for trade in trades:

            exit_time = trade.get("exit_time")

            if exit_time is None:
                continue

            try:
                if isinstance(exit_time, str):
                    trade_date = datetime.fromisoformat(
                        exit_time
                    ).date()
                else:
                    trade_date = exit_time.date()

                if trade_date == today:
                    daily_pnl += trade.get("pnl", 0)

            except (ValueError, AttributeError):
                continue

        max_loss = DEFAULT_CAPITAL * self.DAILY_LOSS_LIMIT

        if daily_pnl <= -max_loss:

            print(f"Daily PnL: ₹{daily_pnl:.2f}")
            print(f"Limit    : -₹{max_loss:.2f}")

            return False

        return True

    # ----------------------------------------------------------
    # DAILY STATISTICS
    # ----------------------------------------------------------

    def _print_daily_stats(self):

        history_file = Path("database/trade_history.json")

        if not history_file.exists():
            return

        try:

            with open(history_file) as f:
                trades = json.load(f)

        except (json.JSONDecodeError, IOError):
            return

        if not trades:
            return

        today = datetime.now().date()

        today_trades = []

        for trade in trades:

            exit_time = trade.get("exit_time")

            if exit_time is None:
                continue

            try:
                if isinstance(exit_time, str):
                    trade_date = datetime.fromisoformat(
                        exit_time
                    ).date()
                else:
                    trade_date = exit_time.date()

                if trade_date == today:
                    today_trades.append(trade)

            except (ValueError, AttributeError):
                continue

        if not today_trades:
            return

        wins = sum(1 for t in today_trades if t.get("pnl", 0) > 0)
        losses = len(today_trades) - wins
        total_pnl = sum(t.get("pnl", 0) for t in today_trades)

        print()
        print("-" * 40)
        print("TODAY'S STATS")
        print("-" * 40)
        print(f"Trades : {len(today_trades)}")
        print(f"Wins   : {wins}")
        print(f"Losses : {losses}")
        print(f"Net PnL: ₹{total_pnl:.2f}")
        print("-" * 40)