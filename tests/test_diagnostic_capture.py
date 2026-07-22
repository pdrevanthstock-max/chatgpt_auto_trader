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


def test_top_n_is_retained_per_index_and_cycle_regardless_of_scan_order():
    capture = DiagnosticCaptureService(max_rows=100)
    capture.start(5)
    rows = []
    for rank in range(1, 7):
        rows.extend([
            {"cycle_id": "cycle-1", "index": "BANKNIFTY", "rank": rank},
            {"cycle_id": "cycle-1", "index": "NIFTY", "rank": rank},
        ])

    capture.record(reversed(rows))

    visible = capture.snapshot().rows
    assert {
        symbol: sorted(row["rank"] for row in visible if row["index"] == symbol)
        for symbol in ("NIFTY", "BANKNIFTY")
    } == {
        "NIFTY": [1, 2, 3, 4, 5, 6],
        "BANKNIFTY": [1, 2, 3, 4, 5, 6],
    }
    assert len(json.loads(capture.to_json())) == 12


def test_capture_bounds_full_history_independently_per_index():
    capture = DiagnosticCaptureService(max_rows=2)
    capture.start(5)
    capture.record([
        {"cycle_id": "c1", "index": "NIFTY", "rank": 1},
        {"cycle_id": "c1", "index": "BANKNIFTY", "rank": 1},
        {"cycle_id": "c2", "index": "NIFTY", "rank": 1},
        {"cycle_id": "c2", "index": "BANKNIFTY", "rank": 1},
        {"cycle_id": "c3", "index": "NIFTY", "rank": 1},
    ])

    exported = json.loads(capture.to_json())
    assert [(row["index"], row["cycle_id"]) for row in exported] == [
        ("BANKNIFTY", "c1"),
        ("NIFTY", "c2"),
        ("BANKNIFTY", "c2"),
        ("NIFTY", "c3"),
    ]


def test_live_snapshot_keeps_only_latest_cycle_per_index_but_exports_history():
    capture = DiagnosticCaptureService(max_rows=100)
    capture.start(5)
    capture.record([
        {"cycle_id": "nifty-old", "index": "NIFTY", "rank": 1, "pair": "old"},
        {"cycle_id": "bank-current", "index": "BANKNIFTY", "rank": 2, "pair": "bank-2"},
        {"cycle_id": "bank-current", "index": "BANKNIFTY", "rank": 1, "pair": "bank-1"},
        {"cycle_id": "nifty-current", "index": "NIFTY", "rank": 2, "pair": "nifty-2"},
        {"cycle_id": "nifty-current", "index": "NIFTY", "rank": 1, "pair": "nifty-1"},
    ])

    visible = capture.snapshot().rows

    assert [(row["index"], row["cycle_id"], row["rank"]) for row in visible] == [
        ("BANKNIFTY", "bank-current", 1),
        ("BANKNIFTY", "bank-current", 2),
        ("NIFTY", "nifty-current", 1),
        ("NIFTY", "nifty-current", 2),
    ]
    assert len(capture.snapshot().full_rows) == 5
    assert len(json.loads(capture.to_json())) == 5


def test_latest_cycle_prefers_ranked_pairs_over_wait_record():
    capture = DiagnosticCaptureService(max_rows=100)
    capture.start(5)
    capture.record([
        {"cycle_id": "c1", "index": "NIFTY", "result": "WAIT", "reason": "CANDLES_PENDING"},
        {"cycle_id": "c1", "index": "NIFTY", "rank": 2, "result": "FAIL"},
        {"cycle_id": "c1", "index": "NIFTY", "rank": 1, "result": "PASS"},
    ])

    assert [row.get("rank") for row in capture.snapshot().rows] == [1, 2]


def test_live_snapshot_exposes_ten_rows_even_when_capture_started_at_top_five():
    capture = DiagnosticCaptureService(max_rows=100)
    capture.start(5)
    capture.record([
        {"cycle_id": "c1", "index": "NIFTY", "rank": rank, "pair": f"pair-{rank}"}
        for rank in range(1, 11)
    ])

    snapshot = capture.snapshot()

    assert snapshot.top_count == 5
    assert [row["rank"] for row in snapshot.rows] == list(range(1, 11))
