"""
Dhan Broker Client
Compatible with DhanHQ SDK 2.x
"""

from dhanhq import DhanContext, dhanhq

from config.settings import (
    DHAN_CLIENT_ID,
    DHAN_ACCESS_TOKEN,
)


class DhanClient:

    def __init__(self):

        self.context = DhanContext(
            DHAN_CLIENT_ID,
            DHAN_ACCESS_TOKEN,
        )

        self.client = dhanhq(self.context)

    def get_profile(self):
        return self.client.get_profile()

    def get_funds(self):
        return self.client.get_fund_limits()

    def get_positions(self):
        return self.client.get_positions()

    def get_holdings(self):
        return self.client.get_holdings()

    def get_expiry_list(self):
        """
        NIFTY Security ID = 13
        Underlying Type = INDEX
        """

        return self.client.get_expiry_list(
            underlying_security_id="13",
            underlying_type="INDEX",
        )

    def get_option_chain(self, expiry):

        return self.client.get_option_chain(
            underlying_security_id="13",
            underlying_type="INDEX",
            expiry_date=expiry,
        )