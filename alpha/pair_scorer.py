"""
Pair Scoring Engine
"""


class PairScorer:

    def score(self, ce, pe):

        score = 0

        # Liquidity

        score += min(ce["oi"], pe["oi"]) / 1000

        # Volume

        score += min(
            ce["volume"],
            pe["volume"]
        ) / 100

        # Bid Ask

        ce_spread = ce["top_ask_price"] - ce["top_bid_price"]
        pe_spread = pe["top_ask_price"] - pe["top_bid_price"]

        score -= ce_spread
        score -= pe_spread

        return round(score, 2)