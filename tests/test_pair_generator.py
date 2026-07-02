from alpha.option_chain import OptionChain
from alpha.atm_finder import ATMFinder
from alpha.strike_window import StrikeWindow
from alpha.pair_generator import PairGenerator

chain = OptionChain()

market = chain.download()

spot = market["spot"]

strikes = sorted(
    float(s)
    for s in market["chain"].keys()
)

atm = ATMFinder.find(
    spot,
    strikes,
)

window = StrikeWindow.generate(
    strikes,
    atm,
)

pairs = PairGenerator.generate(
    window,
    market["chain"],
)

print("=" * 80)
print("TOTAL PAIRS")
print("=" * 80)

print(len(pairs))

print()

print("=" * 80)
print("FIRST PAIR")
print("=" * 80)

print(
    pairs[0]["ce_strike"],
    "<->",
    pairs[0]["pe_strike"]
)

print()

print("=" * 80)
print("LAST PAIR")
print("=" * 80)

print(
    pairs[-1]["ce_strike"],
    "<->",
    pairs[-1]["pe_strike"]
)