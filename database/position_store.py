"""
Position Store

Saves and loads the current paper position.
"""

import json
from pathlib import Path


class PositionStore:

    FILE = Path("database/current_position.json")

    @classmethod
    def save(cls, position):

        print("WRITING FILE...")
        print(position)
        print("Saving position...")

        with open(cls.FILE, "w") as f:
            json.dump(
                position,
                f,
                indent=4,
                default=str,
            )

    @classmethod
    def load(cls):

        if not cls.FILE.exists():
            return None

        with open(cls.FILE) as f:
            return json.load(f)

    @classmethod
    def clear(cls):

        if cls.FILE.exists():
            cls.FILE.unlink()