"""
Pair Generator
"""


class PairGenerator:

    @staticmethod
    def generate(window, chain):
        """
        Generate every CE/PE combination
        inside the strike window.
        """

        pairs = []

        for ce_strike in window:

            ce = chain[str(f"{ce_strike:.6f}")]["ce"]

            for pe_strike in window:

                pe = chain[str(f"{pe_strike:.6f}")]["pe"]

                pairs.append(
                    {
                        "ce_strike": ce_strike,
                        "pe_strike": pe_strike,
                        "ce": ce,
                        "pe": pe,
                    }
                )

        return pairs