import pytest
from datetime import datetime
from core.models import Trade
from core.enums import TradeDirection, TradePhase
from data.dhan_client import DhanClient
from unittest.mock import MagicMock

def test_trade_pnl_and_transaction_costs():
    # Setup trade with 2 lots (lot size = 65)
    # Entry premium sum: CE (100) + PE (100) = 200
    # Current premium sum: CE (110) + PE (105) = 215
    # Gross profit: (215 - 200) * 2 * 65 = 15 * 130 = ₹1950.00
    # Estimated round-trip costs use four orders plus turnover-based levies.
    # Net profit deducts that all-in estimate from gross P&L.
    trade = Trade(
        direction=TradeDirection.LONG_CE,
        strike_ce=24300,
        strike_pe=24300,
        entry_ce_price=100.0,
        entry_pe_price=100.0,
        quantity=2,
        lot_size=65,
        entry_time=datetime.now(),
        phase=TradePhase.PHASE_1_BOTH_LEGS,
        ce_current_price=110.0,
        pe_current_price=105.0
    )

    assert trade.gross_pnl == 1950.00
    assert trade.transaction_cost_breakdown.brokerage == 80.00
    assert trade.transaction_costs == 159.78
    assert trade.net_pnl == 1790.22


def test_screenshot_trade_costs_use_orders_and_turnover_not_lot_count():
    trade = Trade(
        direction=TradeDirection.LONG_CE,
        strike_ce=24200,
        strike_pe=23950,
        entry_ce_price=13.60,
        entry_pe_price=12.65,
        quantity=26,
        lot_size=65,
        entry_time=datetime.now(),
        phase=TradePhase.CLOSED,
        exit_ce_price=15.80,
        exit_pe_price=10.60,
    )

    assert trade.gross_pnl == 253.50
    assert trade.transaction_cost_breakdown.brokerage == 80.00
    assert trade.transaction_costs == 200.05
    assert trade.net_pnl == 53.45


def test_trade_exposes_units_per_leg_for_dynamic_179_lot_position():
    trade = Trade(quantity=179, lot_size=65)

    assert trade.quantity == 179
    assert trade.units_per_leg == 11_635


def test_dhan_client_validate_credentials_success():
    client = DhanClient()
    # Mock self.client.get_positions to return success
    client.client = MagicMock()
    client.client.get_positions.return_value = {"status": "success", "data": []}

    assert client.validate_credentials() is True


def test_dhan_client_validate_credentials_failure():
    client = DhanClient()
    client.client = MagicMock()
    client.client.get_positions.return_value = {
        "status": "failure",
        "remarks": {
            "error_code": "DH-901",
            "error_type": "Invalid_Authentication",
            "error_message": "Access token expired"
        }
    }

    with pytest.raises(ValueError, match="Dhan Access Token expired or invalid"):
        client.validate_credentials()
