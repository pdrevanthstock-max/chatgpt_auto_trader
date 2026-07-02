from pprint import pprint

from alpha.option_chain import OptionChain


chain = OptionChain()

data = chain.download()

print("=" * 80)
print("SPOT")
print("=" * 80)

print(data["spot"])

print()

print("=" * 80)
print("EXPIRY")
print("=" * 80)

print(data["expiry"])

print()

print("=" * 80)
print("NUMBER OF STRIKES")
print("=" * 80)

print(len(data["chain"]))

print()

print("=" * 80)
print("FIRST STRIKE")
print("=" * 80)

first = next(iter(data["chain"]))

print(first)

print()

pprint(data["chain"][first])