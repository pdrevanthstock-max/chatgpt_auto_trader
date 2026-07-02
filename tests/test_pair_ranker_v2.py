from alpha.option_chain import OptionChain
from alpha.strike_selector import StrikeSelector
from alpha.pair_generator import PairGenerator
from alpha.pair_ranker_v2 import PairRankerV2


chain = OptionChain().download()

selector = StrikeSelector(chain)

window = selector.get_window()

pairs = PairGenerator.generate(
    window,
    chain["chain"],
)

ranked = PairRankerV2.rank(
    pairs,
    chain["spot"],
    chain["chain"],
)

print("=" * 80)
print("TOP 20 NORMALIZED PAIRS")
print("=" * 80)

for item in ranked[:20]:

    print(
        f'CE {item["pair"]["ce_strike"]:.0f} '
        f'PE {item["pair"]["pe_strike"]:.0f} '
        f'Score {item["score"]:.4f}'
    )