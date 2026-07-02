# tests/test_chain_statistics.py

from alpha.option_chain import OptionChain

chain = OptionChain().download()

strikes = chain["chain"]

oi = []
volume = []

for strike in strikes.values():

    oi.append(strike["ce"]["oi"])
    oi.append(strike["pe"]["oi"])

    volume.append(strike["ce"]["volume"])
    volume.append(strike["pe"]["volume"])

print("Max OI:", max(oi))
print("Min OI:", min(oi))

print("Max Volume:", max(volume))
print("Min Volume:", min(volume))