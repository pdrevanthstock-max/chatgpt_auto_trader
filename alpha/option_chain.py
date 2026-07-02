"""
Option Chain Module
"""

from broker.dhan_client import DhanClient


class OptionChain:

    def __init__(self):

        self.broker = DhanClient()

    def get_current_expiry(self):

        response = self.broker.get_expiry_list()

        if response["status"] != "success":
            raise Exception(response)

        return response["data"]["data"][0]

    def download(self):

        expiry = self.get_current_expiry()

        response = self.broker.get_option_chain(expiry)

        if response["status"] != "success":
            raise Exception(response)

        data = response["data"]["data"]

        return {
            "spot": float(data["last_price"]),
            "expiry": expiry,
            "chain": data["oc"],
        }