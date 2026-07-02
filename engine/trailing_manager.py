"""
Trailing Stop Manager
"""


class TrailingManager:

    @staticmethod
    def update(position):

        if not position["trail"]:
            return position

        current = position["current_price"]

        stop = position["stop_loss"]

        risk = position["initial_risk"]

        new_stop = current - risk

        if new_stop > stop:

            position["stop_loss"] = round(
                new_stop,
                2,
            )

        return position