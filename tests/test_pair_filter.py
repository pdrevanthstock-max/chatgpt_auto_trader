from alpha.option_chain import OptionChain
from alpha.strike_selector import StrikeSelector
from alpha.pair_generator import PairGenerator
from alpha.pair_selector import PairSelector

chain = OptionChain().download()

selector = StrikeSelector(chain)

window = selector.get_window(5)

pairs = PairGenerator.generate(
    window,
    chain["chain"]
)

ranking, rejected = PairSelector().select(
    pairs
)

print("=" * 80)
print("TOTAL GENERATED")
print("=" * 80)
print(len(pairs))

print()

print("=" * 80)
print("VALID")
print("=" * 80)
print(len(ranking))

print()

print("=" * 80)
print("REJECTED")
print("=" * 80)
print(rejected)

print()

print("=" * 80)
print("TOP 10")
print("=" * 80)

for row in ranking[:10]:
    print(row)