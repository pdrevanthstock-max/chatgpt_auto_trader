"""
Market Data Layer

Responsible for

1. Current Expiry
2. Option Chain
3. In-Memory Cache
"""

from datetime import datetime

from broker.dhan_client import DhanClient


class MarketData:

    def __init__(self):

        self.broker = DhanClient()

        self.option_chain = None

        self.current_expiry = None

        self.last_update = None

    # --------------------------------------------------

    def get_current_expiry(self):

        response = self.broker.client.expiry_list(
            under_security_id=13,
            under_exchange_segment="IDX_I",
        )

        if response["status"] != "success":
            raise Exception(response)

        expiry = response["data"][0]

        self.current_expiry = expiry

        return expiry

    # --------------------------------------------------

    def download_option_chain(self):

        if self.current_expiry is None:

            self.get_current_expiry()

        response = self.broker.client.option_chain(
            under_security_id=13,
            under_exchange_segment="IDX_I",
            expiry=self.current_expiry,
        )

        if response["status"] != "success":
            raise Exception(response)

        self.option_chain = response["data"]

        self.last_update = datetime.now()

        return self.option_chain

    # --------------------------------------------------

    def refresh(self):

        return self.download_option_chain()

    # --------------------------------------------------

    def summary(self):

        return {

            "expiry": self.current_expiry,

            "contracts": len(self.option_chain),

            "last_update": self.last_update,

        }