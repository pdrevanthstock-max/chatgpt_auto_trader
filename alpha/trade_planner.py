"""
Trade Planner
"""


class TradePlanner:

    @staticmethod
    def build(best_pair, decision):

        if decision is None:
            return None

        direction = decision["direction"]

        entry = decision["entry"]

        hedge = decision["hedge"]

        if direction == "LONG_CE":

            entry_strike = best_pair["ce_strike"]

            hedge_strike = best_pair["pe_strike"]

        else:

            entry_strike = best_pair["pe_strike"]

            hedge_strike = best_pair["ce_strike"]

        return {

            "direction": direction,

            "entry_security_id": entry["security_id"],

            "hedge_security_id": hedge["security_id"],

            "entry_strike": entry_strike,

            "hedge_strike": hedge_strike,

            "entry_price": entry["last_price"],

            "bid": entry["top_bid_price"],

            "ask": entry["top_ask_price"],

            "quantity": 75,

            "order_type": "LIMIT",

            "stop_loss": None,

            "target": None,

            "trail": False,
        }