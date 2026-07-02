"""
Position Manager Test
"""

from pprint import pprint

from alpha.option_chain import OptionChain
from alpha.strike_selector import StrikeSelector
from alpha.pair_generator import PairGenerator
from alpha.market_statistics import MarketStatistics
from alpha.feature_extractor import FeatureExtractor
from alpha.normalized_scorer import NormalizedScorer
from alpha.decision_engine import DecisionEngine
from alpha.trade_planner import TradePlanner
from alpha.paper_executor import PaperExecutor
from alpha.position_manager import PositionManager


chain = OptionChain().download()

selector = StrikeSelector(chain)

window = selector.get_window()

pairs = PairGenerator.generate(
    window,
    chain["chain"],
)

stats = MarketStatistics.calculate(
    chain["chain"],
)

best = None
best_score = -1

for pair in pairs:

    features = FeatureExtractor.extract(
        pair,
        chain["spot"],
    )

    score = NormalizedScorer.score(
        features,
        stats,
    )

    if score > best_score:

        best = pair
        best_score = score

decision = DecisionEngine.decide(
    best,
    "BULLISH",
)

plan = TradePlanner.build(
    best,
    decision,
)

position = PaperExecutor.execute(
    plan,
)

print("=" * 80)
print("INITIAL POSITION")
print("=" * 80)

pprint(position)

position = PositionManager.update(
    position,
    chain["chain"],
)

print()

print("=" * 80)
print("UPDATED POSITION")
print("=" * 80)

pprint(position)