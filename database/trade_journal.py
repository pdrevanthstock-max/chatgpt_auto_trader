"""
Trade Journal

Stores all completed trades.
"""

import json
from pathlib import Path


class TradeJournal:

    FILE = Path("database/trade_history.json")

    @classmethod
    def append(cls, trade):

        if cls.FILE.exists():

            with open(cls.FILE) as f:
                history = json.load(f)

        else:

            history = []

        history.append(trade)

        with open(cls.FILE, "w") as f:

            json.dump(
                history,
                f,
                indent=4,
                default=str,
            )