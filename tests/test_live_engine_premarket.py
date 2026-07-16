from datetime import datetime
from pathlib import Path


def test_engine_has_throttled_session_status_before_multi_index_scan():
    source = Path("ui/app.py").read_text(encoding="utf-8")

    session_gate = source.index("session_status = self.market_schedule.at(now)")
    runtime_scan = source.index("cycle = self.multi_index_runtime.scan(")
    assert session_gate < runtime_scan
    assert "not session_status.entries_allowed" in source
    assert "_log_activity_throttled(" in source
    assert "session_status.status_interval_seconds" in source


def test_activity_log_is_persisted_by_the_engine():
    source = Path("ui/app.py").read_text(encoding="utf-8")

    assert "ActivityJournal" in source
    assert "self.activity_journal.append(formatted)" in source
