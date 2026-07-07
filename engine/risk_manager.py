"""
Risk Manager

Per-trade risk rules:
  • Stop Loss   : 2% below entry price
  • Target       : None (no fixed target — trailing stop handles exits)
  • Trailing     : Enabled — activates at +1% profit, locks 90% of gains

Daily risk cap  : 3% of capital (enforced by TradingScheduler)
"""


class RiskManager:

    STOP_LOSS_PCT = 0.02       # 2% per trade
    TRAIL_ACTIVATION = 0.01    # activate trailing after +1% profit
    TRAIL_FACTOR = 0.90        # lock in 90% of unrealised profit

    @classmethod
    def apply(cls, trade):

        entry = trade["entry_price"]

        stop_loss = round(entry * (1 - cls.STOP_LOSS_PCT), 2)

        trade["stop_loss"] = stop_loss
        trade["target"] = None          # no fixed target
        trade["trail"] = True

        return trade