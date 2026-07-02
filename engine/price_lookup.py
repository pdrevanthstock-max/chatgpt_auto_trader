"""
Price Lookup

Finds the latest option price
using Security ID.
"""


class PriceLookup:

    @staticmethod
    def get_price(chain, security_id):

        for strike in chain.values():

            ce = strike["ce"]

            if ce["security_id"] == security_id:

                return ce["last_price"]

            pe = strike["pe"]

            if pe["security_id"] == security_id:

                return pe["last_price"]

        return None