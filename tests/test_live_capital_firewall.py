import pytest

from core.exceptions import DataFetchError
from data.dhan_client import DhanClient
from execution.capital_firewall import LiveCapitalFirewall


def test_dhan_client_rejects_order_writes_when_orders_are_not_explicitly_enabled():
    class FakeSDK:
        calls = 0

        def place_order(self, **_details):
            self.calls += 1
            return {"status": "success", "data": {"orderId": "unsafe"}}

    client = DhanClient.__new__(DhanClient)
    client.client = FakeSDK()
    client.orders_enabled = False

    with pytest.raises(DataFetchError, match="disabled"):
        client.place_order({"security_id": "1"})

    assert client.client.calls == 0


def test_live_firewall_uses_strategy_allocation_not_full_broker_balance():
    firewall = LiveCapitalFirewall(allocation_limit=40_000.0, reserve_pct=0.10)

    firewall.authorize_entry(required_funds=35_000.0, broker_available_funds=100_000.0)

    with pytest.raises(ValueError, match="strategy allocation"):
        firewall.authorize_entry(
            required_funds=40_001.0,
            broker_available_funds=100_000.0,
        )


def test_live_firewall_fails_closed_without_confirmed_broker_funds():
    firewall = LiveCapitalFirewall(allocation_limit=40_000.0, reserve_pct=0.10)

    with pytest.raises(ValueError, match="broker-confirmed"):
        firewall.authorize_entry(required_funds=10_000.0, broker_available_funds=None)


def test_live_firewall_reserves_ten_percent_of_allocation_for_costs_and_slippage():
    firewall = LiveCapitalFirewall(allocation_limit=40_000.0, reserve_pct=0.10)

    assert firewall.deployable_limit == 36_000.0
    with pytest.raises(ValueError, match="deployable"):
        firewall.authorize_entry(36_000.01, 100_000.0)
