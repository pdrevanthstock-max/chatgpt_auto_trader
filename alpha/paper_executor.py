"""
Paper Order Executor
"""


from datetime import datetime


class PaperExecutor:

    @staticmethod
    def execute(plan):

        return {

            "status": "FILLED",

            "entry_security_id": plan["entry_security_id"],
            "hedge_security_id": plan["hedge_security_id"],
            #"initial_risk": plan["entry_price"] - plan["stop_loss"],

            "direction": plan["direction"],

            "entry_price": plan["entry_price"],

            "initial_risk": plan["entry_price"] - plan["stop_loss"],

            "quantity": plan["quantity"],

            "stop_loss": plan["stop_loss"],

            "target": plan["target"],

            "trail": plan["trail"],

            "entry_time": datetime.now(),

            "current_price": plan["entry_price"],

            "exit_price": None,

            "exit_time": None,

            "exit_reason": None,

            "pnl": 0,

            "closed": False,
        }