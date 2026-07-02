"""
Strike Window Generator
"""


class StrikeWindow:

    @staticmethod
    def generate(strikes, atm, distance=5):
        """
        Return strikes around ATM.

        distance=5

        ATM-5 ..... ATM ..... ATM+5
        """

        strikes = sorted(strikes)

        atm_index = strikes.index(atm)

        start = max(0, atm_index - distance)

        end = min(len(strikes), atm_index + distance + 1)

        return strikes[start:end]