import pytest

from strategy.profitability import ProfitabilityCalculator, ProfitabilityInput


def test_profitability_is_quantity_aware_and_counts_freeze_order_slices():
    result = ProfitabilityCalculator.calculate(ProfitabilityInput(
        entry_ce_ask=100.0, entry_pe_ask=100.0,
        projected_ce_bid=104.0, projected_pe_bid=102.0,
        lots=30, lot_size=65, freeze_units=1_800,
        slippage_per_unit_per_fill=0.05,
        minimum_net_profit=100.0, minimum_return_pct=0.25,
    ))

    assert result.units_per_leg == 1_950
    assert result.order_slices_per_leg == 2
    assert result.executed_order_count == 8
    assert result.gross_pnl == 11_700.0
    assert result.transaction_costs.brokerage == 160.0
    assert result.slippage == 390.0
    assert result.projected_net_pnl > 0
    assert result.buffer_passed is True


def test_small_gross_edge_is_rejected_after_costs_slippage_and_buffer():
    result = ProfitabilityCalculator.calculate(ProfitabilityInput(
        entry_ce_ask=100.0, entry_pe_ask=100.0,
        projected_ce_bid=100.5, projected_pe_bid=100.2,
        lots=1, lot_size=65, freeze_units=1_800,
        slippage_per_unit_per_fill=0.05,
        minimum_net_profit=100.0, minimum_return_pct=0.25,
    ))

    assert result.projected_net_pnl < 0
    assert result.buffer_passed is False
