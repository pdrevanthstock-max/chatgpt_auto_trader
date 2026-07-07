"""
Broker Order Executor

Places live orders through the Dhan broker API.

IMPORTANT: This is fully coded but NOT active.
ExecutionManager.MODE = "PAPER" by default.

Switch to "LIVE" only after:
  1. Strategy validated on historical data (backtest)
  2. Strategy validated on live paper trading
  3. Risk parameters confirmed
"""

from datetime import datetime
from broker.dhan_client import DhanClient


class BrokerExecutor:

    @staticmethod
    def execute(plan):
        """
        Place a real order on Dhan.

        Parameters
        ----------
        plan : dict
            Trade plan from TradePlanner + RiskManager.

        Returns
        -------
        dict
            Position dict matching the PaperExecutor format.
        """

        client = DhanClient()

        # Determine order side from direction
        if plan["direction"] == "LONG_CE":
            transaction_type = client.client.BUY
        elif plan["direction"] == "LONG_PE":
            transaction_type = client.client.BUY
        else:
            raise ValueError(
                f"Unknown direction: {plan['direction']}"
            )

        # Determine order type
        if plan.get("order_type") == "MARKET":
            order_type = client.client.MARKET
            price = 0
        else:
            order_type = client.client.LIMIT
            price = plan["entry_price"]

        # Place the entry order
        response = client.client.place_order(
            security_id=str(plan["entry_security_id"]),
            exchange_segment=client.client.NSE_FNO,
            transaction_type=transaction_type,
            quantity=plan["quantity"],
            order_type=order_type,
            product_type=client.client.INTRA,
            price=price,
        )

        if response["status"] != "success":
            raise Exception(
                f"Order placement failed: {response}"
            )

        order_id = response["data"].get("orderId")

        # Build position dict in same format as PaperExecutor
        return {

            "status": "PLACED",

            "order_id": order_id,

            "entry_security_id": plan["entry_security_id"],
            "hedge_security_id": plan["hedge_security_id"],

            "direction": plan["direction"],

            "entry_price": plan["entry_price"],

            "initial_risk": (
                plan["entry_price"] - plan["stop_loss"]
                if plan.get("stop_loss")
                else 0
            ),

            "quantity": plan["quantity"],

            "stop_loss": plan.get("stop_loss"),

            "target": plan.get("target"),

            "trail": plan.get("trail", True),

            "entry_time": datetime.now(),

            "current_price": plan["entry_price"],

            "exit_price": None,

            "exit_time": None,

            "exit_reason": None,

            "pnl": 0,

            "closed": False,
        }

    @staticmethod
    def close_position(position):
        """
        Place an exit order for an existing position.

        Called when stop-loss or trailing exit is triggered.
        """

        client = DhanClient()

        # Exit is always SELL for long positions
        transaction_type = client.client.SELL

        response = client.client.place_order(
            security_id=str(position["entry_security_id"]),
            exchange_segment=client.client.NSE_FNO,
            transaction_type=transaction_type,
            quantity=position["quantity"],
            order_type=client.client.MARKET,
            product_type=client.client.INTRA,
            price=0,
        )

        if response["status"] != "success":
            raise Exception(
                f"Exit order failed: {response}"
            )

        return response