"""
Exit Manager
"""

from datetime import datetime


class ExitManager:

    @staticmethod
    def close(position, exit_price, reason):

        position["closed"] = True

        position["status"] = "EXITED"

        position["exit_price"] = exit_price

        position["exit_time"] = datetime.now()

        position["exit_reason"] = reason

        return position