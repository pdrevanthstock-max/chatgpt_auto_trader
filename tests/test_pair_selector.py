from pprint import pprint

from alpha.option_chain import OptionChain
from alpha.strike_selector import StrikeSelector
from alpha.pair_generator import PairGenerator
from alpha.pair_selector import PairSelector

chain = OptionChain().download()

selector = StrikeSelector(chain)

window = selector.get_window(5)

pairs = PairGenerator().generate(window)

ranking = PairSelector().select(chain, pairs)

print("=" * 80)
print("TOP 20")
print("=" * 80)

for row in ranking[:20]:

    pprint(row)