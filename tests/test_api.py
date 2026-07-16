from fastapi.testclient import TestClient

from api.app import create_app


def test_health_and_default_index_universe():
    client = TestClient(create_app())

    health = client.get("/api/health")
    indices = client.get("/api/indices")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    body = indices.json()
    assert body["selection"]["is_all"] is True
    assert body["selection"]["pause_new_entries"] is False
    assert len(body["indices"]) == 5
    assert {row["permission"] for row in body["indices"]} == {
        "TRADABLE", "OBSERVE_ONLY"
    }
    readiness = {row["symbol"]: row["runtime_connected"] for row in body["indices"]}
    assert readiness["NIFTY"] is True
    assert readiness["BANKNIFTY"] is True
    assert readiness["FINNIFTY"] is True
    assert readiness["MIDCPNIFTY"] is True
    assert readiness["NIFTYNXT50"] is True


def test_runtime_selection_supports_one_many_and_pause():
    client = TestClient(create_app())
    initial = client.get("/api/indices").json()["selection"]

    one = client.put(
        "/api/indices/selection",
        json={"symbols": ["BANKNIFTY"], "expected_version": initial["version"]},
    )
    paused = client.put(
        "/api/indices/selection",
        json={"symbols": [], "expected_version": one.json()["version"]},
    )

    assert one.status_code == 200
    assert one.json()["symbols"] == ["BANKNIFTY"]
    assert paused.status_code == 200
    assert paused.json()["pause_new_entries"] is True


def test_stale_or_unknown_selection_is_rejected_without_state_change():
    client = TestClient(create_app())
    initial = client.get("/api/indices").json()["selection"]
    accepted = client.put(
        "/api/indices/selection",
        json={"symbols": ["NIFTY"], "expected_version": initial["version"]},
    )

    stale = client.put(
        "/api/indices/selection",
        json={"symbols": ["FINNIFTY"], "expected_version": initial["version"]},
    )
    unknown = client.put(
        "/api/indices/selection",
        json={"symbols": ["SENSEX"], "expected_version": accepted.json()["version"]},
    )

    assert stale.status_code == 409
    assert unknown.status_code == 422
    current = client.get("/api/indices").json()["selection"]
    assert current["symbols"] == ["NIFTY"]


def test_compiled_web_ui_is_served_without_streamlit(tmp_path):
    frontend = tmp_path / "dist"
    frontend.mkdir()
    (frontend / "index.html").write_text("<title>AutoTrader</title>", encoding="utf-8")
    response = TestClient(create_app(frontend_dir=frontend)).get("/")

    assert response.status_code == 200
    assert "AutoTrader" in response.text
