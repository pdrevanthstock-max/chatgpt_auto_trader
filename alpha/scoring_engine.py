"""
Scoring Engine
"""


class ScoringEngine:

    @staticmethod
    def score(pair):

        ce = pair["ce"]
        pe = pair["pe"]

        score = 0

        # Liquidity
        score += ce["volume"]
        score += pe["volume"]

        # Open Interest
        score += ce["oi"] * 2
        score += pe["oi"] * 2

        # Bid Quantity
        score += ce["top_bid_quantity"] * 10
        score += pe["top_bid_quantity"] * 10

        # Ask Quantity
        score += ce["top_ask_quantity"] * 10
        score += pe["top_ask_quantity"] * 10

        return score