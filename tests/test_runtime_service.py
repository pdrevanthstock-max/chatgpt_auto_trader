import pytest
from datetime import datetime

from application.diagnostic_capture import DiagnosticCaptureService
from application.runtime_service import RuntimeService
from core.models import Trade


class FakeEngine:
    def __init__(self, mode="PAPER"):
        self.running = False
        self.session_execution_mode = None
        self.mode = mode
        self.active_trade = None
        self.activity_log = []

    def start(self):
        self.running = True
        self.session_execution_mode = self.mode
        self.activity_log.append("started")

    def stop(self):
        self.running = False
        self.activity_log.append("stopped")


def test_runtime_starts_and_stops_one_paper_engine_instance():
    engines = []
    runtime = RuntimeService(lambda: engines.append(FakeEngine()) or engines[-1])

    assert runtime.snapshot().state == "STOPPED"
    assert runtime.start().state == "RUNNING"
    assert runtime.start().state == "RUNNING"
    assert len(engines) == 1
    assert runtime.stop().state == "STOPPED"


def test_runtime_fails_closed_if_engine_does_not_confirm_paper_mode():
    engine = FakeEngine(mode="LIVE")
    runtime = RuntimeService(lambda: engine)

    with pytest.raises(RuntimeError, match="PAPER mode"):
        runtime.start()

    assert engine.running is False


def test_runtime_cannot_stop_while_any_position_needs_risk_monitoring():
    engine = FakeEngine()
    engine.active_trade = Trade(execution_mode="PAPER")
    runtime = RuntimeService(lambda: engine)
    runtime.start()

    with pytest.raises(RuntimeError, match="active position"):
        runtime.stop()

    assert engine.running is True


def test_production_paper_factory_locks_legacy_engine_to_paper():
    source = __import__("pathlib").Path("application/runtime_service.py").read_text(encoding="utf-8")
    assert 'execution_mode_lock="PAPER"' in source
    assert "BrokerExecutor" not in source


def test_runtime_snapshot_exposes_server_authoritative_market_phase():
    runtime = RuntimeService(
        lambda: FakeEngine(),
        now_provider=lambda: datetime(2026, 7, 16, 9, 20),
    )

    snapshot = runtime.snapshot()

    assert snapshot.market_phase == "OBSERVATION_WARMUP"
    assert snapshot.seconds_to_next_phase == 600
    assert "entries begin at 09:30" in snapshot.market_status
