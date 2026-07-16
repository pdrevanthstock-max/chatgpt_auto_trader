from datetime import datetime

import pytest

from core.enums import (
    ExitReason,
    MarketRegime,
    OrderType,
    TradeDirection,
    TradePhase,
)
from core.exceptions import PartialFillError
from core.models import ScoredCandidate, Trade, TradePlan
from data.market_cache import market_cache
from execution.paper_executor import PaperExecutor


def _quote(bid: float, ask: float, last: float) -> dict:
    return {
        "bid": bid,
        "ask": ask,
        "last": last,
        "open": last,
        "timestamp": datetime.now(),
    }


def _plan(
    order_type: OrderType = OrderType.MARKET,
    ce_limit_price: float | None = None,
    pe_limit_price: float | None = None,
    quantity: int = 1,
) -> TradePlan:
    candidate = ScoredCandidate(
        ce_strike=24300,
        pe_strike=24300,
        ce_velocity=2.0,
        pe_velocity=1.0,
        divergence=1.0,
        winning_leg="CE",
        projected_net_profit=500.0,
        confidence=0.8,
    )
    return TradePlan(
        scored_candidate=candidate,
        regime=MarketRegime.DIRECTIONAL,
        order_type=order_type,
        quantity=quantity,
        lot_size=65,
        ce_limit_price=ce_limit_price,
        pe_limit_price=pe_limit_price,
    )


def _open_trade() -> Trade:
    return Trade(
        direction=TradeDirection.LONG_CE,
        strike_ce=24300,
        strike_pe=24300,
        entry_ce_price=100.0,
        entry_pe_price=200.0,
        quantity=1,
        lot_size=65,
        entry_time=datetime.now(),
        regime_at_entry=MarketRegime.DIRECTIONAL,
        phase=TradePhase.PHASE_1_BOTH_LEGS,
        ce_current_price=100.0,
        pe_current_price=200.0,
    )


def _populate_quotes() -> None:
    market_cache.clear()
    market_cache.update_option(24300, "CE", _quote(99.0, 101.0, 100.0))
    market_cache.update_option(24300, "PE", _quote(198.0, 202.0, 200.0))


def test_market_entry_buys_both_legs_at_ask():
    _populate_quotes()

    trade = PaperExecutor().execute_entry(_plan(), datetime.now())

    assert trade.entry_ce_price == 101.0
    assert trade.entry_pe_price == 202.0


def test_dynamic_quantity_is_shared_by_both_paper_legs():
    _populate_quotes()

    trade = PaperExecutor().execute_entry(
        _plan(quantity=179),
        datetime.now(),
    )

    assert trade.quantity == 179
    assert trade.units_per_leg == 11_635


def test_paper_entry_preserves_index_identity_and_lot_size_from_plan():
    _populate_quotes()
    plan = _plan()
    plan.index_symbol = "BANKNIFTY"
    plan.lot_size = 30

    trade = PaperExecutor().execute_entry(plan, datetime.now())

    assert trade.index_symbol == "BANKNIFTY"
    assert trade.lot_size == 30


def test_limit_entry_receives_ask_price_improvement_when_marketable():
    _populate_quotes()

    trade = PaperExecutor().execute_entry(
        _plan(
            order_type=OrderType.LIMIT,
            ce_limit_price=102.0,
            pe_limit_price=203.0,
        ),
        datetime.now(),
    )

    assert trade.entry_ce_price == 101.0
    assert trade.entry_pe_price == 202.0


def test_limit_entry_fails_atomically_when_either_ask_exceeds_limit():
    _populate_quotes()

    with pytest.raises(PartialFillError, match="CE buy limit"):
        PaperExecutor(limit_fill_timeout_seconds=0.0).execute_entry(
            _plan(
                order_type=OrderType.LIMIT,
                ce_limit_price=100.0,
                pe_limit_price=203.0,
            ),
            datetime.now(),
        )


def test_limit_entry_waits_for_both_legs_to_cross_in_one_snapshot():
    clock = [0.0]
    snapshots = [
        {
            24300: {
                "CE": _quote(99.0, 101.0, 100.0),
                "PE": _quote(198.0, 202.0, 200.0),
            }
        },
        {
            24300: {
                "CE": _quote(99.0, 100.0, 99.5),
                "PE": _quote(198.0, 202.0, 200.0),
            }
        },
    ]

    def chain_provider():
        return snapshots.pop(0) if len(snapshots) > 1 else snapshots[0]

    executor = PaperExecutor(
        chain_provider=chain_provider,
        limit_fill_timeout_seconds=2.0,
        limit_fill_poll_seconds=1.0,
        monotonic=lambda: clock[0],
        sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )

    trade = executor.execute_entry(
        _plan(
            order_type=OrderType.LIMIT,
            ce_limit_price=100.0,
            pe_limit_price=202.0,
        ),
        datetime.now(),
    )

    assert trade.entry_ce_price == 100.0
    assert trade.entry_pe_price == 202.0
    assert clock[0] == 1.0


def test_limit_entry_times_out_without_creating_a_partial_trade():
    clock = [0.0]
    snapshot = {
        24300: {
            "CE": _quote(99.0, 101.0, 100.0),
            "PE": _quote(198.0, 202.0, 200.0),
        }
    }
    executor = PaperExecutor(
        chain_provider=lambda: snapshot,
        limit_fill_timeout_seconds=2.0,
        limit_fill_poll_seconds=1.0,
        monotonic=lambda: clock[0],
        sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )

    with pytest.raises(PartialFillError, match="timed out"):
        executor.execute_entry(
            _plan(
                order_type=OrderType.LIMIT,
                ce_limit_price=100.0,
                pe_limit_price=202.0,
            ),
            datetime.now(),
        )

    assert clock[0] == 2.0


def test_exit_both_sells_both_legs_at_bid():
    _populate_quotes()
    trade = _open_trade()

    PaperExecutor().execute_exit_both(trade, datetime.now(), ExitReason.MANUAL)

    assert trade.exit_ce_price == 99.0
    assert trade.exit_pe_price == 198.0
    assert trade.phase == TradePhase.CLOSED


def test_exit_both_fails_closed_when_an_executable_bid_is_missing():
    market_cache.clear()
    market_cache.update_option(
        24300,
        "CE",
        {"ask": 101.0, "last": 100.0, "open": 100.0},
    )
    market_cache.update_option(24300, "PE", _quote(198.0, 202.0, 200.0))
    trade = _open_trade()

    with pytest.raises(PartialFillError, match="CE exit bid"):
        PaperExecutor().execute_exit_both(
            trade,
            datetime.now(),
            ExitReason.MANUAL,
        )

    assert trade.phase == TradePhase.PHASE_1_BOTH_LEGS
    assert trade.exit_ce_price is None
    assert trade.exit_pe_price is None


def test_hedge_cut_sells_losing_leg_at_bid():
    _populate_quotes()
    trade = _open_trade()

    PaperExecutor().execute_hedge_cut(trade, datetime.now())

    assert trade.losing_leg == "PE"
    assert trade.losing_leg_exit_price == 198.0
    assert trade.phase == TradePhase.PHASE_2_SINGLE_LEG


def test_single_leg_exit_sells_winning_leg_at_bid():
    _populate_quotes()
    trade = _open_trade()
    PaperExecutor().execute_hedge_cut(trade, datetime.now())

    PaperExecutor().execute_single_leg_exit(
        trade,
        datetime.now(),
        ExitReason.TARGET_HIT,
    )

    assert trade.winning_leg == "CE"
    assert trade.exit_ce_price == 99.0
    assert trade.phase == TradePhase.CLOSED
