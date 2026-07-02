"""
Position Manager
"""


class PositionManager:

    @staticmethod
    def update(position, chain):

        if position["closed"]:
            return position

        security_id = position["entry_security_id"]

        current_price = None

        for strike in chain.values():

            ce = strike["ce"]

            pe = strike["pe"]

            if ce["security_id"] == security_id:
                current_price = ce["last_price"]
                break

            if pe["security_id"] == security_id:
                current_price = pe["last_price"]
                break

        if current_price is None:
            return position

        pnl = (
            current_price
            - position["entry_price"]
        ) * position["quantity"]

        position["current_price"] = current_price

        position["pnl"] = round(pnl, 2)

        return position