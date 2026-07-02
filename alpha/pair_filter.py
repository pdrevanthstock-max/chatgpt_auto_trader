"""
Pair Eligibility Filter
"""


class PairFilter:

    def is_valid(self, ce, pe):

        # both contracts must exist

        if ce is None or pe is None:
            return False

        # OI

        if ce["oi"] <= 0:
            return False

        if pe["oi"] <= 0:
            return False

        # Volume

        if ce["volume"] <= 0:
            return False

        if pe["volume"] <= 0:
            return False

        # Bid price

        if ce["top_bid_price"] <= 0:
            return False

        if pe["top_bid_price"] <= 0:
            return False

        # Ask price

        if ce["top_ask_price"] <= 0:
            return False

        if pe["top_ask_price"] <= 0:
            return False

        return True