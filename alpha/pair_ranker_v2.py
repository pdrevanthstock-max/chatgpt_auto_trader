"""
Normalized Pair Ranker
"""

from alpha.feature_extractor import FeatureExtractor
from alpha.normalized_scorer import NormalizedScorer
from alpha.market_statistics import MarketStatistics


class PairRankerV2:

    @staticmethod
    def rank(pairs, spot, chain):

        stats = MarketStatistics.calculate(chain)

        ranked = []

        for pair in pairs:

            features = FeatureExtractor.extract(
                pair,
                spot,
            )

            score = NormalizedScorer.score(
                features,
                stats,
            )

            ranked.append(
                {
                    "pair": pair,
                    "score": score,
                    "features": features,
                }
            )

        ranked.sort(
            key=lambda x: x["score"],
            reverse=True,
        )

        return ranked