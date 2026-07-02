"""
Feature Extractor
"""


class FeatureExtractor:

    @staticmethod
    def extract(pair, atm):

        ce = pair["ce"]
        pe = pair["pe"]

        ce_bid = ce["top_bid_price"]
        ce_ask = ce["top_ask_price"]

        pe_bid = pe["top_bid_price"]
        pe_ask = pe["top_ask_price"]

        ce_ltp = max(ce["last_price"], 0.01)
        pe_ltp = max(pe["last_price"], 0.01)

        ce_spread = ce_ask - ce_bid
        pe_spread = pe_ask - pe_bid

        ce_spread_pct = ce_spread / ce_ltp
        pe_spread_pct = pe_spread / pe_ltp

        return {

            "ce_volume": ce["volume"],
            "pe_volume": pe["volume"],

            "ce_oi": ce["oi"],
            "pe_oi": pe["oi"],

            "ce_iv": ce["implied_volatility"],
            "pe_iv": pe["implied_volatility"],

            "ce_spread": ce_spread_pct,
            "pe_spread": pe_spread_pct,

            "ce_distance": abs(pair["ce_strike"] - atm),
            "pe_distance": abs(pair["pe_strike"] - atm),
        }