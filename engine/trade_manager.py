"""
Trade Manager

Maintains one active paper position.
"""

from alpha.position_manager import PositionManager
from database.position_store import PositionStore
from engine.execution_manager import ExecutionManager
from database.trade_journal import TradeJournal


class TradeManager:

    def __init__(self):

        self.position = PositionStore.load()

    def has_position(self):

        return (
            self.position is not None
            and not self.position.get("closed", True)
        )

    def open(self, trade):

        self.position = ExecutionManager.execute(trade)

        PositionStore.save(self.position)

        return self.position

    def update(self, current_price):

        if not self.has_position():
            return None

        PositionManager.update(
            self.position,
            current_price,
        )

        PositionStore.save(self.position)

        return self.position

    def close(self):

        if self.has_position():

            self.position["closed"] = True

            TradeJournal.append(self.position)

            PositionStore.save(self.position)

            self.position = None

        return self.position

    def clear(self):
        """Remove position file and reset state after exit."""

        PositionStore.clear()

        self.position = None

    def save(self):

        PositionStore.save(self.position)