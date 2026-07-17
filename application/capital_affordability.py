from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime

from core.transaction_costs import calculate_option_round_trip_costs


@dataclass(frozen=True)
class CapitalAffordabilityView:
    combined_ask: float
    lot_size: int
    available_capital: float
    deployable_capital: float
    one_lot_premium: float
    max_lots: int
    charges_estimate: float
    capital_shortfall: float
    maximum_premium_at_risk: float
    quote_age_seconds: float | None
    affordable: bool

    @property
    def estimated_round_trip_charges(self) -> float:
        return self.charges_estimate

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def build_capital_affordability(
    *,
    ce_ask: float,
    pe_ask: float,
    lot_size: int,
    available_capital: float,
    deployment_fraction: float,
    ce_quote_time: datetime | None = None,
    pe_quote_time: datetime | None = None,
    as_of: datetime | None = None,
) -> CapitalAffordabilityView:
    """Build an observational one-pair capital view without deciding eligibility."""
    if not all(math.isfinite(float(value)) and value > 0.0 for value in (ce_ask, pe_ask)):
        raise ValueError("Executable asks must be finite and positive.")
    if lot_size <= 0:
        raise ValueError("lot_size must be positive.")
    if not math.isfinite(float(available_capital)) or available_capital < 0.0:
        raise ValueError("available_capital must be finite and non-negative.")
    if not math.isfinite(float(deployment_fraction)) or not 0.0 <= deployment_fraction <= 1.0:
        raise ValueError("deployment_fraction must be between 0 and 1.")

    combined_ask = round(float(ce_ask) + float(pe_ask), 2)
    available = round(float(available_capital), 2)
    deployable = round(available * float(deployment_fraction), 2)
    one_lot_premium = round(combined_ask * lot_size, 2)
    max_lots = int(math.floor(deployable / one_lot_premium)) if one_lot_premium > 0.0 else 0
    charges = calculate_option_round_trip_costs(
        float(ce_ask),
        float(pe_ask),
        float(ce_ask),
        float(pe_ask),
        lots=1,
        lot_size=lot_size,
    ).total

    quote_age: float | None = None
    quote_times = [value for value in (ce_quote_time, pe_quote_time) if value is not None]
    if quote_times and as_of is not None:
        quote_age = round(max(0.0, max((as_of - value).total_seconds() for value in quote_times)), 3)

    shortfall = round(max(0.0, one_lot_premium - deployable), 2)
    return CapitalAffordabilityView(
        combined_ask=combined_ask,
        lot_size=int(lot_size),
        available_capital=available,
        deployable_capital=deployable,
        one_lot_premium=one_lot_premium,
        max_lots=max_lots,
        charges_estimate=charges,
        capital_shortfall=shortfall,
        maximum_premium_at_risk=round(one_lot_premium * max_lots, 2),
        quote_age_seconds=quote_age,
        affordable=max_lots > 0,
    )
