from pprint import pprint

from alpha.option_chain import OptionChain
from alpha.strike_selector import StrikeSelector
from alpha.pair_generator import PairGenerator
from alpha.feature_extractor import FeatureExtractor
from alpha.market_statistics import MarketStatistics
from alpha.normalized_scorer import NormalizedScorer


chain = OptionChain().download()

selector = StrikeSelector(chain)

window = selector.get_window()

pairs = PairGenerator.generate(
    window,
    chain["chain"],
)

stats = MarketStatistics.calculate(chain["chain"])

pair = pairs[0]

features = FeatureExtractor.extract(
    pair,
    chain["spot"],
)

score = NormalizedScorer.score(
    features,
    stats,
)

print("=" * 80)
print("FEATURES")
print("=" * 80)

pprint(features)

print()

print("=" * 80)
print("MARKET STATS")
print("=" * 80)

pprint(stats)

print()

print("=" * 80)
print("NORMALIZED SCORE")
print("=" * 80)

print(score)