"""
Decision Engine
"""


class DecisionEngine:

    @staticmethod
    def decide(pair, candle_signal):

        ce = pair["ce"]
        pe = pair["pe"]

        if candle_signal == "BULLISH":

            return {
                "direction": "LONG_CE",
                "entry": ce,
                "hedge": pe,
            }

        if candle_signal == "BEARISH":

            return {
                "direction": "LONG_PE",
                "entry": pe,
                "hedge": ce,
            }

        return None