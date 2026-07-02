"""
Market State

Stores recent market observations.
"""


class MarketState:

    def __init__(self):

        self.previous_spot = None
        self.current_spot = None

        self.previous_atm = None
        self.current_atm = None

        self.last_signal = None

    def update(self, spot, atm):

        self.previous_spot = self.current_spot
        self.previous_atm = self.current_atm

        self.current_spot = spot
        self.current_atm = atm

    def is_first_run(self):

        return self.previous_spot is None

    def movement(self):

        if self.is_first_run():
            return 0

        return self.current_spot - self.previous_spot