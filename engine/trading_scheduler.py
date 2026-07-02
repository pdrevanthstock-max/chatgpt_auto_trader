"""
Trading Scheduler

Runs the Trading Engine continuously.
"""

import time
from datetime import datetime

from engine.trading_engine import TradingEngine
from alpha.market_state import MarketState


class TradingScheduler:

    def __init__(self):

        self.engine = TradingEngine()

        self.market_state = MarketState()

        self.running = False

    def start(self, interval=30):

        self.running = True

        print("=" * 80)
        print("AUTO TRADING STARTED")
        print("=" * 80)

        while self.running:

            print()
            print("=" * 80)
            print(datetime.now())
            print("=" * 80)

            try:

                result = self.engine.run()

                print()

                print("=" * 80)
                print("ENGINE SUMMARY")
                print("=" * 80)

                print("Mode :", result["mode"])

                if result["mode"] == "ENTRY":

                    print("Direction :", result["decision"]["direction"])
                    print("CE Strike :", result["best_pair"]["ce_strike"])
                    print("PE Strike :", result["best_pair"]["pe_strike"])
                    print("Score     :", round(result["score"], 4))

                elif result["mode"] == "MANAGE":

                    position = result["position"]

                    print("Managing Existing Position")
                    print("Direction :", position["direction"])
                    print("Current   :", position.get("current_price"))
                    print("PnL       :", position["pnl"])

                    print("Position  :", result["position"]["status"])

            except Exception as e:

                print("ENGINE ERROR")
                print(e)

            print()

            print(f"Sleeping {interval} seconds...")

            time.sleep(interval)

    def stop(self):

        self.running = False