from types import SimpleNamespace

from core.enums import ExecutionMode, MarketRegime, OrderType, SignalType, TradePhase
from core.index_registry import IndexRegistry
from core.models import ExecutionSignal, ScoredCandidate, Trade, TradePlan
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


def test_paper_strategy_equity_uses_the_dashboard_authoritative_balance():
    """The scanner must size from exactly the PAPER money shown in the web UI."""
    engine = LiveEngine.__new__(LiveEngine)
    engine.session_execution_mode = ExecutionMode.PAPER.value
    engine.config = SimpleNamespace(
        execution_mode=ExecutionMode.PAPER.value,
        total_capital=45_000.0,
    )
    engine.session_allocated_capital = 8_634.65
    engine.realized_pnl = -122.03
    engine.capital_ledger = SimpleNamespace(
        paper_equity=lambda **_: 44_877.97,
    )
    engine.paper_equity_provider = lambda: 81_243.32

    assert engine.current_strategy_equity() == 81_243.32


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


def test_successful_paper_exit_releases_global_slot_for_next_entry():
    class ClosingExecutor:
        def execute_exit_both(self, trade, now, reason):
            trade.exit_ce_price = trade.ce_current_price
            trade.exit_pe_price = trade.pe_current_price
            trade.exit_time = now
            trade.exit_reason = reason
            trade.phase = TradePhase.CLOSED

    sink = SimpleNamespace(
        record_trade_pnl=lambda *_: None,
        save_trade=lambda *_: None,
        save_state=lambda *_ , **__: None,
        log_exit=lambda *_: None,
    )
    engine = LiveEngine.__new__(LiveEngine)
    engine.session_execution_mode = ExecutionMode.PAPER.value
    engine.config = SimpleNamespace(execution_mode=ExecutionMode.PAPER.value)
    engine.realized_pnl = 0.0
    engine.capital_ledger = sink
    engine.store = sink
    engine.recovery = sink
    engine.decision_memory = sink
    engine.log_activity = lambda *_: None
    engine.paper_executors = {"NIFTY": ClosingExecutor()}
    engine.position_reservation = PositionReservation()
    token = engine.position_reservation.try_reserve("NIFTY:candidate")
    assert token is not None
    assert engine.position_reservation.activate(token)
    engine._position_reservation_token = token
    engine.active_trade = Trade(
        execution_mode=ExecutionMode.PAPER.value,
        index_symbol="NIFTY",
        strike_ce=24_100,
        strike_pe=24_150,
        entry_ce_price=100.0,
        entry_pe_price=100.0,
        ce_current_price=104.0,
        pe_current_price=103.0,
        quantity=1,
        lot_size=65,
    )

    engine._execute_signal(ExecutionSignal(
        type=SignalType.EXIT_BOTH,
        trade_id=engine.active_trade.id,
        reason="MANUAL",
    ))

    assert engine.active_trade is None
    assert engine.position_reservation.snapshot().state == "EMPTY"
    assert engine._position_reservation_token is None
    assert engine.position_reservation.try_reserve("NIFTY:next") is not None


def test_global_rotation_compares_indices_and_passes_active_index_economics():
    candidate = ScoredCandidate(
        ce_strike=57_900,
        pe_strike=58_100,
        ce_velocity=5.0,
        pe_velocity=-1.0,
        divergence=6.0,
        winning_leg="CE",
        projected_net_profit=500.0,
        confidence=85.0,
    )
    plan = TradePlan(
        scored_candidate=candidate,
        regime=MarketRegime.DIRECTIONAL,
        order_type=OrderType.MARKET,
        quantity=1,
        lot_size=60,
        index_symbol="FINNIFTY",
    )
    calls = []
    queued = []
    engine = LiveEngine.__new__(LiveEngine)
    engine.session_execution_mode = ExecutionMode.PAPER.value
    engine._last_rotation_scan_at = None
    engine.multi_index_runtime = SimpleNamespace(
        scan_for_rotation=lambda **_: SimpleNamespace(
            winner=SimpleNamespace(
                index_symbol="FINNIFTY",
                candidate=SimpleNamespace(scored_candidate=candidate, plan=plan),
            )
        )
    )
    engine.market_caches = MarketCacheRegistry.default()
    engine.market_caches.get("BANKNIFTY").update_spot(58_000.0, None)
    engine.index_registry = IndexRegistry.default()
    engine.config = SimpleNamespace(
        execution_mode=ExecutionMode.PAPER.value,
        scan_interval_seconds=60,
    )
    engine.current_strategy_equity = lambda: 45_000.0
    engine.active_trade = Trade(index_symbol="BANKNIFTY", lot_size=30, quantity=1)
    engine.realized_pnl = 0.0
    engine.queue = SimpleNamespace(enqueue=queued.append)
    engine.rotation_engine = SimpleNamespace(
        should_rotate=lambda *args, **kwargs: (calls.append(kwargs) or (True, "better"))
    )

    engine._check_rotation_live(
        MarketRegime.DIRECTIONAL,
        ce_p=100.0,
        pe_p=100.0,
        index_symbol="BANKNIFTY",
    )

    assert calls[0]["cache"] is engine.market_caches.get("BANKNIFTY")
    assert calls[0]["lot_size"] == 30
    assert queued[0].type == SignalType.ROTATION
    assert queued[0].trade_plan.index_symbol == "FINNIFTY"

    # The risk loop can call every second, but replacement scans stay on the
    # completed-candle cadence.
    engine._check_rotation_live(
        MarketRegime.DIRECTIONAL,
        ce_p=100.0,
        pe_p=100.0,
        index_symbol="BANKNIFTY",
    )
    assert len(queued) == 1
