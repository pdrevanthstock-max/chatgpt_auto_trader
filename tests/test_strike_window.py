from alpha.option_chain import OptionChain
from alpha.atm_finder import ATMFinder
from alpha.strike_window import StrikeWindow

chain = OptionChain()

data = chain.download()

spot = data["spot"]

strikes = sorted(
    float(s)
    for s in data["chain"].keys()
)

atm = ATMFinder.find(
    spot,
    strikes,
)

window = StrikeWindow.generate(
    strikes,
    atm,
)

print("=" * 80)
print("SPOT")
print("=" * 80)
print(spot)

print()

print("=" * 80)
print("ATM")
print("=" * 80)
print(atm)

print()

print("=" * 80)
print("WINDOW")
print("=" * 80)

for strike in window:
    print(strike)