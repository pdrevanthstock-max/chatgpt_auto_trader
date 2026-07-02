"""
Position Decision

Decides whether to

• HOLD
• EXIT
• REVERSE
"""

class PositionDecision:

    @staticmethod
    def decide(current_position, new_direction):

        if current_position is None:
            return "ENTRY"

        if current_position["closed"]:
            return "ENTRY"

        current_direction = current_position["direction"]

        if current_direction == new_direction:
            return "HOLD"

        return "REVERSE"