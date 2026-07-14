import asyncio
from datetime import datetime

import pytest

from core.enums import ExitReason, MarketRegime, TradeDirection, TradePhase
from core.exceptions import PartialFillError
from core.models import Trade
from core.models import ScoredCandidate, TradePlan
from core.enums import OrderType
from data.market_cache import market_cache
from execution.broker_executor import BrokerExecutor
from execution.capital_firewall import LiveCapitalFirewall


class FakeBrokerClient:
    def __init__(self, order_states, available_balance=100_000.0):
        self.order_states = order_states
        self.placed = []
        self.available_balance = available_balance
        self.cancelled = []

    def place_order(self, details):
        self.placed.append(details)
        return f"order-{len(self.placed)}"

    def get_order_by_id(self, order_id):
        return self.order_states[order_id]

    def get_fund_limits(self):
        return {"available_balance": self.available_balance}

    def cancel_order(self, order_id):
        self.cancelled.append(order_id)
        return True


class OneLegPlacementFailureClient(FakeBrokerClient):
    def place_order(self, details):
        self.placed.append(details)
        if len(self.placed) == 2:
            raise RuntimeError("second leg placement failed")
        return "order-1"


def _executor(states):
    executor = BrokerExecutor.__new__(BrokerExecutor)
    executor.client = FakeBrokerClient(states)
    executor.FILL_TIMEOUT_SECONDS = 0.1
    executor.FILL_POLL_SECONDS = 0.0
    executor.capital_firewall = LiveCapitalFirewall(40_000.0, reserve_pct=0.10)
    return executor


def _trade():
    market_cache.clear()
    market_cache.set_security_id(24_300, "CE", 101)
    market_cache.set_security_id(24_300, "PE", 102)
    return Trade(
        direction=TradeDirection.LONG_CE,
        strike_ce=24_300,
        strike_pe=24_300,
        entry_ce_price=100.0,
        entry_pe_price=100.0,
        quantity=1,
        lot_size=65,
        entry_time=datetime.now(),
        regime_at_entry=MarketRegime.DIRECTIONAL,
        phase=TradePhase.PHASE_1_BOTH_LEGS,
        ce_current_price=95.0,
        pe_current_price=96.0,
        ce_open_units=65,
        pe_open_units=65,
    )


def _plan(quantity=1):
    return TradePlan(
        scored_candidate=ScoredCandidate(
            ce_strike=24_300,
            pe_strike=24_300,
            ce_velocity=2.0,
            pe_velocity=1.0,
            divergence=1.0,
            winning_leg="CE",
            projected_net_profit=500.0,
            confidence=80.0,
        ),
        regime=MarketRegime.DIRECTIONAL,
        order_type=OrderType.MARKET,
        quantity=quantity,
        lot_size=65,
    )


def _populate_entry_quotes():
    now = datetime.now()
    for option_type in ("CE", "PE"):
        market_cache.update_option(
            24_300,
            option_type,
            {"bid": 99.0, "ask": 100.0, "last": 99.5, "timestamp": now},
        )


def test_live_entry_is_rejected_before_order_placement_when_allocation_is_exceeded():
    market_cache.clear()
    market_cache.set_security_id(24_300, "CE", 101)
    market_cache.set_security_id(24_300, "PE", 102)
    now = datetime.now()
    for option_type in ("CE", "PE"):
        market_cache.update_option(
            24_300,
            option_type,
            {
                "bid": 99.0,
                "ask": 100.0,
                "last": 99.5,
                "timestamp": now,
            },
        )
    executor = _executor({})

    with pytest.raises(PartialFillError, match="deployable allocation"):
        asyncio.run(executor.execute_entry(_plan(quantity=3), datetime.now()))

    assert executor.client.placed == []


def test_live_entry_uses_confirmed_average_prices_and_quantities():
    market_cache.clear()
    market_cache.set_security_id(24_300, "CE", 101)
    market_cache.set_security_id(24_300, "PE", 102)
    _populate_entry_quotes()
    executor = _executor({
        "order-1": {"orderStatus": "TRADED", "filledQty": 65, "averageTradedPrice": 101.25},
        "order-2": {"orderStatus": "TRADED", "filledQty": 65, "averageTradedPrice": 99.75},
    })

    trade = asyncio.run(executor.execute_entry(_plan(), datetime.now()))

    assert trade.entry_ce_price == 101.25
    assert trade.entry_pe_price == 99.75
    assert trade.ce_open_units == 65
    assert trade.pe_open_units == 65


def test_live_entry_unwinds_confirmed_leg_when_other_leg_is_rejected():
    market_cache.clear()
    market_cache.set_security_id(24_300, "CE", 101)
    market_cache.set_security_id(24_300, "PE", 102)
    _populate_entry_quotes()
    executor = _executor({
        "order-1": {"orderStatus": "TRADED", "filledQty": 65, "averageTradedPrice": 101.25},
        "order-2": {"orderStatus": "REJECTED", "filledQty": 0, "averageTradedPrice": 0.0},
        "order-3": {"orderStatus": "TRADED", "filledQty": 65, "averageTradedPrice": 101.0},
    })

    with pytest.raises(PartialFillError, match="unwound"):
        asyncio.run(executor.execute_entry(_plan(), datetime.now()))

    assert len(executor.client.placed) == 3
    assert executor.client.placed[-1]["transaction_type"] == "SELL"


def test_live_entry_cancels_accepted_pending_leg_when_other_placement_fails():
    market_cache.clear()
    market_cache.set_security_id(24_300, "CE", 101)
    market_cache.set_security_id(24_300, "PE", 102)
    _populate_entry_quotes()
    executor = _executor({
        "order-1": {
            "orderStatus": "PENDING",
            "filledQty": 0,
            "remainingQuantity": 65,
            "averageTradedPrice": 0.0,
        },
    })
    executor.client = OneLegPlacementFailureClient(
        executor.client.order_states,
        available_balance=100_000.0,
    )

    with pytest.raises(PartialFillError, match="contained"):
        asyncio.run(executor.execute_entry(_plan(), datetime.now()))

    assert executor.client.cancelled == ["order-1"]


def test_live_entry_cancels_and_unwinds_partially_filled_leg():
    market_cache.clear()
    market_cache.set_security_id(24_300, "CE", 101)
    market_cache.set_security_id(24_300, "PE", 102)
    _populate_entry_quotes()
    executor = _executor({
        "order-1": {
            "orderStatus": "PART_TRADED",
            "filledQty": 20,
            "remainingQuantity": 45,
            "averageTradedPrice": 101.25,
        },
        "order-2": {
            "orderStatus": "REJECTED",
            "filledQty": 0,
            "remainingQuantity": 65,
            "averageTradedPrice": 0.0,
        },
        "order-3": {
            "orderStatus": "TRADED",
            "filledQty": 20,
            "remainingQuantity": 0,
            "averageTradedPrice": 101.0,
        },
    })

    with pytest.raises(PartialFillError, match="unwound"):
        asyncio.run(executor.execute_entry(_plan(), datetime.now()))

    assert executor.client.cancelled == ["order-1"]
    assert executor.client.placed[-1]["transaction_type"] == "SELL"
    assert executor.client.placed[-1]["quantity"] == 20


def test_live_exit_closes_only_after_both_full_fills_are_confirmed():
    executor = _executor({
        "order-1": {"orderStatus": "TRADED", "filledQty": 65, "averageTradedPrice": 95.0},
        "order-2": {"orderStatus": "TRADED", "filledQty": 65, "averageTradedPrice": 96.0},
    })
    trade = _trade()

    asyncio.run(executor.execute_exit_both(trade, datetime.now(), ExitReason.HARD_STOP))

    assert trade.phase is TradePhase.CLOSED
    assert trade.ce_open_units == 0
    assert trade.pe_open_units == 0
    assert trade.exit_ce_price == 95.0
    assert trade.exit_pe_price == 96.0


def test_live_exit_keeps_failed_leg_open_and_never_marks_trade_closed():
    executor = _executor({
        "order-1": {"orderStatus": "TRADED", "filledQty": 65, "averageTradedPrice": 95.0},
        "order-2": {"orderStatus": "REJECTED", "filledQty": 0, "averageTradedPrice": 0.0},
    })
    trade = _trade()

    with pytest.raises(PartialFillError):
        asyncio.run(executor.execute_exit_both(trade, datetime.now(), ExitReason.HARD_STOP))

    assert trade.phase is TradePhase.PARTIAL_EXIT
    assert trade.ce_open_units == 0
    assert trade.pe_open_units == 65
    assert trade.exit_time is None


def test_live_exit_cancels_partial_remainder_and_tracks_only_units_still_open():
    executor = _executor({
        "order-1": {
            "orderStatus": "PART_TRADED",
            "filledQty": 20,
            "remainingQuantity": 45,
            "averageTradedPrice": 95.0,
        },
        "order-2": {
            "orderStatus": "REJECTED",
            "filledQty": 0,
            "remainingQuantity": 65,
            "averageTradedPrice": 0.0,
        },
    })
    trade = _trade()

    with pytest.raises(PartialFillError):
        asyncio.run(executor.execute_exit_both(trade, datetime.now(), ExitReason.HARD_STOP))

    assert executor.client.cancelled == ["order-1"]
    assert trade.phase is TradePhase.PARTIAL_EXIT
    assert trade.ce_open_units == 45
    assert trade.pe_open_units == 65
    assert trade.exit_time is None


def test_live_single_leg_exit_tracks_partial_fill_before_retry():
    executor = _executor({
        "order-1": {
            "orderStatus": "PART_TRADED",
            "filledQty": 20,
            "remainingQuantity": 45,
            "averageTradedPrice": 95.0,
        },
    })
    trade = _trade()
    trade.phase = TradePhase.PHASE_2_SINGLE_LEG
    trade.pe_open_units = 0

    with pytest.raises(PartialFillError):
        asyncio.run(
            executor.execute_single_leg_exit(
                trade, datetime.now(), ExitReason.HARD_STOP
            )
        )

    assert executor.client.cancelled == ["order-1"]
    assert trade.phase is TradePhase.PARTIAL_EXIT
    assert trade.ce_open_units == 45
