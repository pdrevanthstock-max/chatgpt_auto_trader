from alpha.option_chain import OptionChain
from alpha.strike_selector import StrikeSelector
from alpha.pair_generator import PairGenerator
from alpha.pair_ranker import PairRanker

chain_data = OptionChain().download()

window = StrikeSelector(chain_data).get_window()

pairs = PairGenerator.generate(
    window,
    chain_data["chain"]
)

ranked = PairRanker.rank(pairs)

print("=" * 80)
print("TOTAL")
print("=" * 80)
print(len(ranked))

print()

print("=" * 80)
print("TOP 10")
print("=" * 80)

for pair in ranked[:10]:

    print(
        pair["ce_strike"],
        "<->",
        pair["pe_strike"],
        "Score:",
        round(pair["score"], 2),
    )