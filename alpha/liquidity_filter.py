"""
Liquidity Filter
"""


class LiquidityFilter:

    @staticmethod
    def is_valid(pair):

        ce = pair["ce"]
        pe = pair["pe"]

        # ---------- CE ----------

        if ce["oi"] <= 0:
            return False

        if ce["volume"] <= 0:
            return False

        if ce["last_price"] <= 0:
            return False

        if ce["top_bid_price"] <= 0:
            return False

        if ce["top_ask_price"] <= 0:
            return False

        # ---------- PE ----------

        if pe["oi"] <= 0:
            return False

        if pe["volume"] <= 0:
            return False

        if pe["last_price"] <= 0:
            return False

        if pe["top_bid_price"] <= 0:
            return False

        if pe["top_ask_price"] <= 0:
            return False

        return True

    @classmethod
    def filter(cls, pairs):

        valid = []

        rejected = []

        for pair in pairs:

            if cls.is_valid(pair):
                valid.append(pair)
            else:
                rejected.append(pair)

        return valid, rejected