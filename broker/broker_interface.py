"""
Abstract Broker Interface

Every broker implementation must follow this contract.
"""

from abc import ABC, abstractmethod


class BrokerInterface(ABC):

    @abstractmethod
    def connect(self):
        pass

    @abstractmethod
    def get_profile(self):
        pass

    @abstractmethod
    def get_funds(self):
        pass

    @abstractmethod
    def get_positions(self):
        pass

    @abstractmethod
    def get_holdings(self):
        pass

    @abstractmethod
    def get_quote(self, security_id: str):
        pass