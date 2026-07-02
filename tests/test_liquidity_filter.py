from pprint import pprint

from alpha.option_chain import OptionChain
from alpha.strike_selector import StrikeSelector
from alpha.pair_generator import PairGenerator

chain_data = OptionChain().download()

selector = StrikeSelector(chain_data)

window = selector.get_window()

pairs = PairGenerator.generate(
    window,
    chain_data["chain"]
)

print("=" * 80)
print("FIRST 5 PAIRS")
print("=" * 80)

for pair in pairs[:5]:

    print()
    print("CE:", pair["ce_strike"])
    pprint(pair["ce"])

    print()

    print("PE:", pair["pe_strike"])
    pprint(pair["pe"])

    print("-" * 80)