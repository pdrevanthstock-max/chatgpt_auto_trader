from __future__ import annotations

from typing import Iterable


class PairTemplateGenerator:
    """Produces bounded executable strike layouts instead of a CE×PE matrix."""

    @staticmethod
    def matched_atm(strikes: Iterable[int | float | str], spot: float) -> list[tuple[object, object]]:
        unique = list(dict.fromkeys(strikes))
        if "ATM" in unique:
            return [("ATM", "ATM")]
        numeric = [value for value in unique if isinstance(value, (int, float))]
        if not numeric or spot <= 0.0:
            return []
        nearest = min(numeric, key=lambda strike: (abs(float(strike) - spot), float(strike)))
        return [(nearest, nearest)]
