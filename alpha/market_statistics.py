"""
Market Statistics
"""


class MarketStatistics:

    @staticmethod
    def calculate(chain):

        ce_volumes = []
        pe_volumes = []

        ce_oi = []
        pe_oi = []

        ce_iv = []
        pe_iv = []

        ce_spreads = []
        pe_spreads = []

        for strike in chain.values():

            ce = strike["ce"]
            pe = strike["pe"]

            ce_volumes.append(ce["volume"])
            pe_volumes.append(pe["volume"])

            ce_oi.append(ce["oi"])
            pe_oi.append(pe["oi"])

            ce_iv.append(ce["implied_volatility"])
            pe_iv.append(pe["implied_volatility"])

            if ce["last_price"] > 0:
                ce_spreads.append(
                    (ce["top_ask_price"] - ce["top_bid_price"])
                    / ce["last_price"]
                )

            if pe["last_price"] > 0:
                pe_spreads.append(
                    (pe["top_ask_price"] - pe["top_bid_price"])
                    / pe["last_price"]
                )

        return {

            "volume_min": min(ce_volumes + pe_volumes),
            "volume_max": max(ce_volumes + pe_volumes),

            "oi_min": min(ce_oi + pe_oi),
            "oi_max": max(ce_oi + pe_oi),

            "iv_min": min(ce_iv + pe_iv),
            "iv_max": max(ce_iv + pe_iv),

            "spread_min": min(ce_spreads + pe_spreads),
            "spread_max": max(ce_spreads + pe_spreads),
        }