"""
Pair Selector
"""

from alpha.pair_filter import PairFilter
from alpha.pair_scorer import PairScorer


class PairSelector:

    def __init__(self):

        self.filter = PairFilter()
        self.scorer = PairScorer()

    def select(self, pairs):

        ranked = []

        rejected = 0

        for pair in pairs:

            ce = pair["ce"]
            pe = pair["pe"]

            if not self.filter.is_valid(ce, pe):

                rejected += 1
                continue

            ranked.append({

                "ce": pair["ce_strike"],
                "pe": pair["pe_strike"],
                "score": self.scorer.score(
                    ce,
                    pe
                )

            })

        ranked.sort(
            key=lambda x: x["score"],
            reverse=True
        )

        return ranked, rejected