"""
Pair Ranker
"""

from alpha.scoring_engine import ScoringEngine


class PairRanker:

    @staticmethod
    def rank(pairs):

        ranked = []

        for pair in pairs:

            pair["score"] = ScoringEngine.score(pair)

            ranked.append(pair)

        ranked.sort(
            key=lambda x: x["score"],
            reverse=True,
        )

        return ranked