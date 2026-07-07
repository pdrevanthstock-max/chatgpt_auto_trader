"""
Trailing Stop Manager

Logic:
  1. Only activates when profit >= 1% of entry price
  2. Sets stop-loss = entry + (current_profit × 0.90)
     → locks in 90% of unrealised gains
  3. Stop-loss only moves UP, never down

Example (entry = 100):
  price 101  → +1% → trailing activates → SL = 100 + (1 × 0.9) = 100.90
  price 110  → +10% → SL = 100 + (10 × 0.9) = 109.00
  price 105  → SL stays at 109.00 (never moves down)
  price 108  → below 109 → STOP_LOSS triggered
"""

from engine.risk_manager import RiskManager


class TrailingManager:

    @staticmethod
    def update(position):

        if not position.get("trail", False):
            return position

        entry = position["entry_price"]
        current = position["current_price"]

        profit = current - entry
        profit_pct = profit / entry if entry > 0 else 0

        # Only activate trailing after +1% profit
        if profit_pct < RiskManager.TRAIL_ACTIVATION:
            return position

        # New stop = entry + 90% of current profit
        new_stop = round(
            entry + (profit * RiskManager.TRAIL_FACTOR),
            2,
        )

        current_stop = position["stop_loss"]

        # Only move stop-loss UP, never down
        if new_stop > current_stop:
            position["stop_loss"] = new_stop

        return position