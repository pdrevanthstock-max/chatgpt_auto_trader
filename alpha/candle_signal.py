"""
Simple Candle Signal
"""


class CandleSignal:

    @staticmethod
    def detect(state):

        if state.is_first_run():
            return "NEUTRAL"

        move = state.movement()

        if move > 0:
            return "BULLISH"

        if move < 0:
            return "BEARISH"

        return "NEUTRAL"