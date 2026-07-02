"""
Strike Selection Module
"""


class StrikeSelector:

    def __init__(self, option_chain):

        self.option_chain = option_chain

    def get_atm(self):

        spot = self.option_chain["spot"]

        return round(spot / 50) * 50

    def get_window(self, distance=5):

        atm = self.get_atm()

        strikes = []

        for i in range(-distance, distance + 1):

            strikes.append(atm + i * 50)

        return strikes