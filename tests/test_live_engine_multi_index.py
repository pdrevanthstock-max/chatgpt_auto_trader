from types import SimpleNamespace

from core.enums import ExecutionMode, SignalType
from core.models import Trade
from data.market_cache import MarketCacheRegistry
from application.position_reservation import PositionReservation
import pytest
from ui.app import LiveEngine


class QueueSpy:
    def __init__(self) -> None:
        self.signals = []

    def enqueue(self, signal) -> None:
        self.signals.append(signal)


def test_multi_index_opportunity_is_enqueued_with_reservation_token_in_paper_only():
    engine = LiveEngine.__new__(LiveEngine)
    engine.session_execution_mode = ExecutionMode.PAPER.value
    engine.config = SimpleNamespace(execution_mode=ExecutionMode.PAPER.value)
    engine.queue = QueueSpy()
    engine.log_activity = lambda _: None
    engine._paper_daily_threshold_active = True
    plan = SimpleNamespace(index_symbol="BANKNIFTY", post_daily_sl=False)
    opportunity = SimpleNamespace(plan=plan)

    accepted = engine._queue_multi_index_entry(
        "BANKNIFTY", opportunity, "reservation-1"
    )

    assert accepted is True
    assert len(engine.queue.signals) == 1
    assert engine.queue.signals[0].type is SignalType.ENTRY
    assert engine.queue.signals[0].trade_plan is plan
    assert engine.queue.signals[0].reservation_token == "reservation-1"
    assert plan.post_daily_sl is True


def test_multi_index_opportunity_fails_closed_outside_paper():
    engine = LiveEngine.__new__(LiveEngine)
    engine.session_execution_mode = ExecutionMode.LIVE.value
    engine.config = SimpleNamespace(execution_mode=ExecutionMode.LIVE.value)
    engine.queue = QueueSpy()
    engine.log_activity = lambda _: None
    engine._paper_daily_threshold_active = False

    accepted = engine._queue_multi_index_entry(
        "NIFTY", SimpleNamespace(plan=object()), "reservation-1"
    )

    assert accepted is False
    assert engine.queue.signals == []


def test_active_trade_uses_its_own_market_cache_and_paper_executor():
    engine = LiveEngine.__new__(LiveEngine)
    engine.market_caches = MarketCacheRegistry.default()
    bank_executor = object()
    engine.paper_executors = {"BANKNIFTY": bank_executor}
    trade = Trade(index_symbol="BANKNIFTY")

    assert engine._cache_for_trade(trade) is engine.market_caches.get("BANKNIFTY")
    assert engine._paper_executor_for_trade(trade) is bank_executor


def test_failed_paper_entry_releases_the_global_position_slot():
    class FailingExecutor:
        def execute_entry(self, *_):
            raise RuntimeError("simulated fill failure")

    engine = LiveEngine.__new__(LiveEngine)
    engine.paper_executors = {"BANKNIFTY": FailingExecutor()}
    engine.position_reservation = PositionReservation()
    token = engine.position_reservation.try_reserve("BANKNIFTY:candidate")
    assert token is not None
    assert engine.position_reservation.activate(token)
    engine._position_reservation_token = token
    plan = SimpleNamespace(index_symbol="BANKNIFTY")

    with pytest.raises(RuntimeError, match="simulated fill failure"):
        engine._execute_paper_plan(plan, None, token)

    assert engine.position_reservation.snapshot().state == "EMPTY"
    assert engine._position_reservation_token is None
