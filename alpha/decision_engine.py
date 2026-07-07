"""
Decision Engine

Maps market signal → trade direction.

  BULLISH  → LONG_CE  (buy call option)
  BEARISH  → LONG_PE  (buy put option)
  SIDEWAYS → None     (no trade — future strategy)
"""


class DecisionEngine:

    @staticmethod
    def decide(pair, market_signal):

        ce = pair["ce"]
        pe = pair["pe"]

        if market_signal == "BULLISH":

            return {
                "direction": "LONG_CE",
                "entry": ce,
                "hedge": pe,
            }

        if market_signal == "BEARISH":

            return {
                "direction": "LONG_PE",
                "entry": pe,
                "hedge": ce,
            }

        # SIDEWAYS / NEUTRAL / NO_TRADE → skip
        return None