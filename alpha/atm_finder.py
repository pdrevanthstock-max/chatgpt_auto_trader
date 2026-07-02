class ATMFinder:

    @staticmethod
    def find(spot, strikes):
        """
        Return the strike closest to the spot price.
        """

        return min(
            strikes,
            key=lambda strike: abs(strike - spot)
        )