from __future__ import annotations

import math
from numbers import Real
from typing import Mapping

from core.enums import MarketRegime


def has_valid_book(quote: Mapping[str, object] | None) -> bool:
    """Return whether a quote has a finite, positive, non-inverted top of book."""
    if not quote:
        return False
    bid = quote.get("bid")
    ask = quote.get("ask")
    if (
        isinstance(bid, bool)
        or isinstance(ask, bool)
        or not isinstance(bid, Real)
        or not isinstance(ask, Real)
    ):
        return False
    bid_value = float(bid)
    ask_value = float(ask)
    return (
        math.isfinite(bid_value)
        and math.isfinite(ask_value)
        and bid_value > 0.0
        and ask_value >= bid_value
    )


def leg_spread_is_within_emergency_limit(
    quote: Mapping[str, object] | None,
    *,
    maximum_pct: float,
    absolute_floor: float = 0.50,
) -> bool:
    """Reject only an obviously unexecutable book before regime selection."""
    if not has_valid_book(quote):
        return False
    bid = float(quote["bid"])
    ask = float(quote["ask"])
    mid = (bid + ask) / 2.0
    return (ask - bid) <= max(absolute_floor, mid * maximum_pct)


def combined_spread_limit(
    regime: MarketRegime,
    *,
    combined_mid: float,
    absolute_floor: float,
    directional_pct: float,
    sideways_pct: float,
) -> float:
    percentage = (
        directional_pct
        if regime == MarketRegime.DIRECTIONAL
        else sideways_pct
    )
    return max(absolute_floor, combined_mid * percentage)
