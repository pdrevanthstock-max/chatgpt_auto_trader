"""
Risk Manager
"""


class RiskManager:

    @staticmethod
    def apply(trade):

        entry = trade["entry_price"]

        stop_loss = round(entry * 0.90, 2)   # 10% SL
        target = round(entry * 1.20, 2)      # 20% Target

        trade["stop_loss"] = stop_loss
        trade["target"] = target
        trade["trail"] = True

        return trade