"""
Position Monitor
"""


class PositionMonitor:

    @staticmethod
    def update(position, current_price):

        entry = position["entry_price"]

        pnl = (
            current_price - entry
        ) * position["quantity"]

        position["current_price"] = current_price
        position["pnl"] = pnl

        position["exit_reason"] = None

        if current_price <= position["stop_loss"]:

            position["exit_reason"] = "STOP_LOSS"

        elif current_price >= position["target"]:

            position["exit_reason"] = "TARGET"

        return position