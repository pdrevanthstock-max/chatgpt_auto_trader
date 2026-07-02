"""
Execution Manager
"""

from alpha.paper_executor import PaperExecutor
from alpha.broker_executor import BrokerExecutor


class ExecutionManager:

    MODE = "PAPER"

    @classmethod
    def execute(cls, trade):

        if cls.MODE == "PAPER":

            return PaperExecutor.execute(trade)

        elif cls.MODE == "LIVE":

            return BrokerExecutor.execute(trade)

        raise ValueError(
            f"Unknown execution mode: {cls.MODE}"
        )