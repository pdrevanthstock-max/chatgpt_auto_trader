"""
Trading Engine

Runs one complete scan of the market.

No broker-specific logic belongs here.
"""

from alpha.option_chain import OptionChain
from alpha.strike_selector import StrikeSelector
from alpha.pair_generator import PairGenerator
from alpha.liquidity_filter import LiquidityFilter
from alpha.pair_ranker_v2 import PairRankerV2
from alpha.decision_engine import DecisionEngine
from alpha.trade_planner import TradePlanner
from engine.trade_manager import TradeManager
from engine.position_decision import PositionDecision
from engine.risk_manager import RiskManager
from engine.trailing_manager import TrailingManager
from engine.exit_manager import ExitManager
from engine.position_monitor import PositionMonitor
from engine.price_lookup import PriceLookup
#from database.position_store import PositionStore
from database.trade_journal import TradeJournal


class TradingEngine:

    def __init__(self):

        self.trade_manager = TradeManager()

    def run(self):

        if self.trade_manager.has_position():

            return self.manage_position()

        return self.search_trade()
    
    def search_trade(self):

        print("\nDownloading option chain...")

        chain = OptionChain().download()

        print("Selecting strike window...")

        selector = StrikeSelector(chain)

        window = selector.get_window()

        print("Generating CE/PE combinations...")

        pairs = PairGenerator.generate(
            window,
            chain["chain"],
        )

        print(f"Generated {len(pairs)} pairs")

        print("Filtering liquidity...")

        valid_pairs, rejected_pairs = LiquidityFilter.filter(pairs)

        print(f"Remaining {len(valid_pairs)} pairs")
        print(f"Rejected {len(rejected_pairs)} pairs")

        print("Ranking pairs...")

        ranked = PairRankerV2.rank(
            valid_pairs,
            chain["spot"],
            chain["chain"],
        )

        best_result = ranked[0]

        best = best_result["pair"]

        print()

        print("=" * 80)
        print("BEST PAIR")
        print("=" * 80)

        print(
            best["ce_strike"],
            "<->",
            best["pe_strike"],
        )

        print()

        decision = DecisionEngine.decide(
            best,
            "BULLISH",
        )

        print("=" * 80)
        print("DECISION")
        print("=" * 80)

        print(decision["direction"])

        print()

        trade = TradePlanner.build(
            best,
            decision,
        )
        trade = RiskManager.apply(trade)

        print("=" * 80)
        print("TRADE PLAN")
        print("=" * 80)

        print(trade)

        print()

        current_position = self.trade_manager.position

        mode = PositionDecision.decide(
            current_position,
            decision["direction"],
        )

        print()
        print("MODE :", mode)
        print()

        if mode == "ENTRY":

           position = self.trade_manager.open(
               trade
           )

        elif mode == "HOLD":

             position = self.trade_manager.update(
                 trade["entry_price"]
    )

        elif mode == "REVERSE":

            self.trade_manager.close()

            position = self.trade_manager.open(
                trade
            )

        print("=" * 80)
        print("PAPER POSITION")
        print("=" * 80)

        print(position)

        return {

            "mode": mode,

            "position": position,

            "trade": trade,

            "decision": decision,

            "best_pair": best,

            "score": best_result["score"],
        } 
    
    def manage_position(self):

        print()
        print("=" * 80)
        print("MANAGING EXISTING POSITION")
        print("=" * 80)

        position = self.trade_manager.position

    # In future this will come from live market
        #from engine.position_monitor import PositionMonitor
       # from engine.price_lookup import PriceLookup

        chain = OptionChain().download()

        current_price = PriceLookup.get_price(
            chain["chain"],
            position["entry_security_id"],
        )

        position = PositionMonitor.update(
            position,
            current_price,
        ) 

        position = TrailingManager.update(
            position,
            
        )

        if position["exit_reason"] is not None:

            position = ExitManager.close(
                position,
                current_price,
                position["exit_reason"],
            )

            TradeJournal.append(position)

        # Always keep TradeManager updated
        self.trade_manager.position = position

# Always save latest position
        self.trade_manager.save()

        print(position)

        return {

            "mode": "MANAGE",

            "position": position,

        }