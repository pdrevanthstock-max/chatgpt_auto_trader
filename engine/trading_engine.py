"""
Trading Engine

Runs one complete cycle of the market scan + trade management.

No broker-specific logic belongs here.
"""

from alpha.option_chain import OptionChain
from alpha.strike_selector import StrikeSelector
from alpha.pair_generator import PairGenerator
from alpha.liquidity_filter import LiquidityFilter
from alpha.pair_ranker_v2 import PairRankerV2
from alpha.market_confirmation import MarketConfirmation
from alpha.decision_engine import DecisionEngine
from alpha.trade_planner import TradePlanner
from engine.trade_manager import TradeManager
from engine.position_decision import PositionDecision
from engine.risk_manager import RiskManager
from engine.trailing_manager import TrailingManager
from engine.exit_manager import ExitManager
from engine.position_monitor import PositionMonitor
from engine.price_lookup import PriceLookup
from database.trade_journal import TradeJournal


class TradingEngine:

    def __init__(self):

        self.trade_manager = TradeManager()

    def run(self):

        if self.trade_manager.has_position():

            return self.manage_position()

        return self.search_trade()

    # ----------------------------------------------------------
    # SEARCH FOR A NEW TRADE
    # ----------------------------------------------------------

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

        if not valid_pairs:

            print("No valid pairs found — skipping cycle")

            return {
                "mode": "NO_TRADE",
                "reason": "No valid pairs after liquidity filter",
            }

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

        # --------------------------------------------------
        # Get market direction from MarketConfirmation
        # --------------------------------------------------

        confirmation = MarketConfirmation.confirm({
            "spot": chain["spot"],
            "best_pair": best_result,
        })

        market_signal = confirmation["signal"]

        print()
        print("=" * 80)
        print("MARKET SIGNAL")
        print("=" * 80)
        print(f"Signal     : {market_signal}")
        print(f"Confidence : {confirmation['confidence']}")
        print(f"Reason     : {confirmation['reason']}")

        # --------------------------------------------------
        # Decide trade direction
        # --------------------------------------------------

        decision = DecisionEngine.decide(
            best,
            market_signal,
        )

        if decision is None:

            print()
            print("=" * 80)
            print("NO TRADE — Market is SIDEWAYS / NEUTRAL")
            print("=" * 80)

            return {
                "mode": "NO_TRADE",
                "reason": f"Market signal: {market_signal}",
                "confirmation": confirmation,
            }

        print()
        print("=" * 80)
        print("DECISION")
        print("=" * 80)

        print(decision["direction"])

        # --------------------------------------------------
        # Build trade plan with risk management
        # --------------------------------------------------

        trade = TradePlanner.build(
            best,
            decision,
        )
        trade = RiskManager.apply(trade)

        print()
        print("=" * 80)
        print("TRADE PLAN")
        print("=" * 80)

        print(trade)

        # --------------------------------------------------
        # Check position state and act
        # --------------------------------------------------

        current_position = self.trade_manager.position

        mode = PositionDecision.decide(
            current_position,
            decision["direction"],
        )

        print()
        print("MODE :", mode)

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

        print()
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

    # ----------------------------------------------------------
    # MANAGE AN EXISTING POSITION
    # ----------------------------------------------------------

    def manage_position(self):

        print()
        print("=" * 80)
        print("MANAGING EXISTING POSITION")
        print("=" * 80)

        position = self.trade_manager.position

        # Download fresh option chain for current prices
        chain = OptionChain().download()

        current_price = PriceLookup.get_price(
            chain["chain"],
            position["entry_security_id"],
        )

        if current_price is None:

            print("WARNING: Could not find current price — skipping update")
            self.trade_manager.save()

            return {
                "mode": "MANAGE",
                "position": position,
            }

        # Update PnL and check stop-loss
        position = PositionMonitor.update(
            position,
            current_price,
        )

        # Update trailing stop (only moves up after +1% profit)
        position = TrailingManager.update(
            position,
        )

        # --------------------------------------------------
        # EXIT if stop-loss was triggered
        # --------------------------------------------------

        if position["exit_reason"] is not None:

            print()
            print("=" * 80)
            print(f"EXIT TRIGGERED: {position['exit_reason']}")
            print("=" * 80)

            position = ExitManager.close(
                position,
                current_price,
                position["exit_reason"],
            )

            # Record in trade history
            TradeJournal.append(position)

            # Clean up — remove position file so next cycle starts fresh
            self.trade_manager.clear()

            print(f"Direction  : {position['direction']}")
            print(f"Entry      : {position['entry_price']}")
            print(f"Exit       : {position['exit_price']}")
            print(f"PnL        : {position['pnl']}")
            print(f"Reason     : {position['exit_reason']}")

            return {
                "mode": "EXIT",
                "position": position,
            }

        # --------------------------------------------------
        # No exit — save updated position and continue
        # --------------------------------------------------

        self.trade_manager.position = position

        self.trade_manager.save()

        return {
            "mode": "MANAGE",
            "position": position,
        }