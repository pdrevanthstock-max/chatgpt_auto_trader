"""
Exit Manager

Finalises a position when stop-loss is triggered.
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

        # Finalise PnL using actual exit price
        position["pnl"] = round(
            (exit_price - position["entry_price"])
            * position["quantity"],
            2,
        )

        return position