from alpha.option_chain import OptionChain
from alpha.strike_selector import StrikeSelector
from alpha.pair_generator import PairGenerator
from alpha.pair_ranker_v2 import PairRankerV2
from alpha.decision_engine import DecisionEngine


chain = OptionChain().download()

window = StrikeSelector(chain).get_window()

pairs = PairGenerator.generate(
    window,
    chain["chain"],
)

ranked = PairRankerV2.rank(
    pairs,
    chain["spot"],
    chain["chain"],
)

best = ranked[0]["pair"]

print("=" * 80)
print("BEST PAIR")
print("=" * 80)

print(best["ce_strike"], "<->", best["pe_strike"])

print()

decision = DecisionEngine.decide(
    best,
    "BULLISH",
)

print("=" * 80)
print("DECISION")
print("=" * 80)

print(decision["direction"])