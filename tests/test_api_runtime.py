from fastapi.testclient import TestClient

from api.app import create_app
from application.runtime_service import RuntimeService
from tests.test_runtime_service import FakeEngine
from core.models import Trade
from core.enums import TradePhase


def test_engine_api_starts_and_stops_paper_runtime():
    runtime = RuntimeService(lambda: FakeEngine())
    client = TestClient(create_app(runtime=runtime))

    initial = client.get("/api/runtime")
    started = client.post("/api/engine/start")
    stopped = client.post("/api/engine/stop")

    assert initial.json()["state"] == "STOPPED"
    assert started.json()["state"] == "RUNNING"
    assert started.json()["execution_mode"] == "PAPER"
    assert stopped.json()["state"] == "STOPPED"


def test_websocket_publishes_authoritative_runtime_snapshot():
    runtime = RuntimeService(lambda: FakeEngine())
    client = TestClient(create_app(runtime=runtime))

    with client.websocket_connect("/api/events") as socket:
        event = socket.receive_json()

    assert event["type"] == "runtime_snapshot"
    assert event["runtime"]["state"] == "STOPPED"
    assert event["runtime"]["execution_mode"] == "PAPER"
    assert event["diagnostics"]["capturing"] is False


def test_active_position_uses_running_engine_marks_not_stale_database_copy():
    engine = FakeEngine()
    engine.active_trade = Trade(
        id="active", execution_mode="PAPER", quantity=2, lot_size=65,
        strike_ce=24_200, strike_pe=24_200, entry_ce_price=100.0,
        entry_pe_price=100.0, ce_current_price=104.0, pe_current_price=99.0,
        phase=TradePhase.PHASE_1_BOTH_LEGS,
    )
    runtime = RuntimeService(lambda: engine)
    client = TestClient(create_app(runtime=runtime))
    client.post("/api/engine/start")

    position = client.get("/api/positions/active?mode=PAPER").json()

    assert position["trade_id"] == "active"
    assert position["mark_to_market_available"] is True
    assert position["ce_current"] == 104.0
    assert position["units_per_leg"] == 130
