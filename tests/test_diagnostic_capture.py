import json

import pytest

from application.diagnostic_capture import DiagnosticCaptureService


def test_capture_is_off_by_default_and_records_only_while_enabled():
    capture = DiagnosticCaptureService(max_rows=10)
    capture.record([{"symbol": "NIFTY", "score": 1}])

    capture.start(5)
    capture.record([{"symbol": "NIFTY", "score": 2}])
    capture.stop()
    capture.record([{"symbol": "BANKNIFTY", "score": 3}])

    snapshot = capture.snapshot()
    assert snapshot.capturing is False
    assert snapshot.top_count == 5
    assert snapshot.rows == ({"symbol": "NIFTY", "score": 2},)


def test_capture_accepts_only_top_five_or_ten_and_bounds_retention():
    capture = DiagnosticCaptureService(max_rows=2)
    with pytest.raises(ValueError, match="5 or 10"):
        capture.start(7)

    capture.start(10)
    capture.record([{"rank": 1}, {"rank": 2}, {"rank": 3}])

    assert capture.snapshot().rows == ({"rank": 2}, {"rank": 3})


def test_exports_are_deterministic_for_ui_downloads():
    capture = DiagnosticCaptureService()
    capture.start(5)
    capture.record([{"symbol": "NIFTY", "result": "FAIL"}])

    assert json.loads(capture.to_json())[0]["symbol"] == "NIFTY"
    assert capture.to_csv().splitlines() == ["result,symbol", "FAIL,NIFTY"]
