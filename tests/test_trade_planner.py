from pprint import pprint

from alpha.option_chain import OptionChain
from alpha.strike_selector import StrikeSelector
from alpha.pair_generator import PairGenerator
from alpha.feature_extractor import FeatureExtractor
from alpha.market_statistics import MarketStatistics
from alpha.normalized_scorer import NormalizedScorer
from alpha.decision_engine import DecisionEngine
from alpha.trade_planner import TradePlanner

chain = OptionChain().download()

window = StrikeSelector(chain).get_window()

pairs = PairGenerator.generate(
    window,
    chain["chain"]
)

stats = MarketStatistics.calculate(
    chain["chain"]
)

for pair in pairs:

    features = FeatureExtractor.extract(
        pair,
        chain["spot"]
    )

    pair["score"] = NormalizedScorer.score(
        features,
        stats
    )

pairs.sort(
    key=lambda x: x["score"],
    reverse=True
)

best = pairs[0]

decision = DecisionEngine.decide(
    best,
    "BULLISH"
)

plan = TradePlanner.build(
    best,
    decision
)

print("=" * 80)
print("TRADE PLAN")
print("=" * 80)

pprint(plan)