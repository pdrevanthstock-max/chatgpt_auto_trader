"""
Position Monitor

Updates a live position with the current market price.

Checks ONLY stop-loss — there is no fixed target.
The trailing stop (in TrailingManager) handles profit exits.
"""


class PositionMonitor:

    @staticmethod
    def update(position, current_price):

        entry = position["entry_price"]

        pnl = (
            current_price - entry
        ) * position["quantity"]

        position["current_price"] = current_price
        position["pnl"] = round(pnl, 2)

        # Reset exit reason each cycle
        position["exit_reason"] = None

        # Stop-loss hit
        if current_price <= position["stop_loss"]:

            position["exit_reason"] = "STOP_LOSS"

        # No fixed target check — trailing stop handles exits

        return position