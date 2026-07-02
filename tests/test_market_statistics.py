from pprint import pprint

from alpha.option_chain import OptionChain
from alpha.market_statistics import MarketStatistics

chain = OptionChain().download()

stats = MarketStatistics.calculate(
    chain["chain"]
)

pprint(stats)