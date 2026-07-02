"""
Trade Statistics
"""

import json
from pathlib import Path


class TradeStatistics:

    FILE = Path("database/trade_history.json")

    @classmethod
    def load(cls):

        if not cls.FILE.exists():
            return []

        with open(cls.FILE) as f:
            return json.load(f)

    @classmethod
    def summary(cls):

        trades = cls.load()

        if not trades:

            return {

                "trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0,
                "net_pnl": 0,
            }

        wins = 0
        losses = 0
        pnl = 0

        for trade in trades:

            trade_pnl = trade["pnl"]

            pnl += trade_pnl

            if trade_pnl > 0:
                wins += 1
            else:
                losses += 1

        return {

            "trades": len(trades),

            "wins": wins,

            "losses": losses,

            "win_rate": round(
                wins * 100 / len(trades),
                2,
            ),

            "net_pnl": round(pnl, 2),
        }