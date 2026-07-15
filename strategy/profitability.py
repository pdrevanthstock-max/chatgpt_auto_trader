from __future__ import annotations

import math
from dataclasses import dataclass

from core.transaction_costs import OptionCostBreakdown, calculate_option_round_trip_costs


@dataclass(frozen=True)
class ProfitabilityInput:
    entry_ce_ask: float
    entry_pe_ask: float
    projected_ce_bid: float
    projected_pe_bid: float
    lots: int
    lot_size: int
    freeze_units: int
    slippage_per_unit_per_fill: float
    minimum_net_profit: float
    minimum_return_pct: float


@dataclass(frozen=True)
class ProfitabilityResult:
    units_per_leg: int
    order_slices_per_leg: int
    executed_order_count: int
    deployed_capital: float
    gross_pnl: float
    transaction_costs: OptionCostBreakdown
    slippage: float
    projected_net_pnl: float
    projected_return_pct: float
    buffer_passed: bool


class ProfitabilityCalculator:
    @staticmethod
    def calculate(value: ProfitabilityInput) -> ProfitabilityResult:
        if value.lots <= 0 or value.lot_size <= 0 or value.freeze_units <= 0:
            raise ValueError("lots, lot_size, and freeze_units must be positive.")
        prices = (
            value.entry_ce_ask,
            value.entry_pe_ask,
            value.projected_ce_bid,
            value.projected_pe_bid,
        )
        if any(price <= 0.0 for price in prices):
            raise ValueError("profitability prices must be positive executable prices.")
        units = value.lots * value.lot_size
        slices = math.ceil(units / value.freeze_units)
        order_count = slices * 4
        deployed = (value.entry_ce_ask + value.entry_pe_ask) * units
        gross = (
            value.projected_ce_bid
            + value.projected_pe_bid
            - value.entry_ce_ask
            - value.entry_pe_ask
        ) * units
        costs = calculate_option_round_trip_costs(
            value.entry_ce_ask,
            value.entry_pe_ask,
            value.projected_ce_bid,
            value.projected_pe_bid,
            value.lots,
            value.lot_size,
            executed_order_count=order_count,
        )
        slippage = max(0.0, value.slippage_per_unit_per_fill) * units * 4
        net = gross - costs.total - slippage
        return_pct = (net / deployed * 100.0) if deployed > 0.0 else 0.0
        return ProfitabilityResult(
            units_per_leg=units,
            order_slices_per_leg=slices,
            executed_order_count=order_count,
            deployed_capital=round(deployed, 2),
            gross_pnl=round(gross, 2),
            transaction_costs=costs,
            slippage=round(slippage, 2),
            projected_net_pnl=round(net, 2),
            projected_return_pct=round(return_pct, 4),
            buffer_passed=(
                net >= value.minimum_net_profit
                and return_pct >= value.minimum_return_pct
            ),
        )
