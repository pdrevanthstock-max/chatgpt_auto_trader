import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime, time
from execution.crash_recovery import CrashRecovery

def test_status_recovery_date_and_time_validation(tmp_path):
    # Setup CrashRecovery with a temp filepath
    state_file = tmp_path / "persistent_state.json"
    recovery = CrashRecovery(filepath=state_file)

    # 1. Test case: Starting today, during trading hours (e.g. 10:00 AM)
    mock_now = datetime(2026, 7, 13, 10, 0, 0)
    with patch("execution.crash_recovery.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_now
        mock_datetime.fromisoformat = datetime.fromisoformat
        
        recovery.save_engine_status(True)
        
        # Verify JSON content on disk
        status_file = tmp_path / "engine_status.json"
        assert status_file.exists()
        with open(status_file, "r") as f:
            saved_data = json.load(f)
        assert saved_data["running"] is True
        assert saved_data["last_start_date"] == "2026-07-13"

        # Load back, should be True
        assert recovery.load_engine_status() is True

    # 2. Test case: Page refresh on a DIFFERENT day (e.g. July 14th)
    mock_now_next_day = datetime(2026, 7, 14, 10, 0, 0)
    with patch("execution.crash_recovery.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_now_next_day
        mock_datetime.fromisoformat = datetime.fromisoformat

        # Load status, should detect different day, set to False on disk, and return False
        assert recovery.load_engine_status() is False
        
        with open(status_file, "r") as f:
            saved_data = json.load(f)
        assert saved_data["running"] is False

    # 3. Test case: Page refresh after hours on same day (e.g. 15:30)
    with patch("execution.crash_recovery.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(2026, 7, 13, 10, 0, 0)
        mock_datetime.fromisoformat = datetime.fromisoformat

        recovery.save_engine_status(True)

    mock_now_after_hours = datetime(2026, 7, 13, 15, 30, 0)
    with patch("execution.crash_recovery.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_now_after_hours
        mock_datetime.fromisoformat = datetime.fromisoformat

        assert recovery.load_engine_status() is False

        with open(status_file, "r") as f:
            saved_data = json.load(f)
        assert saved_data["running"] is False


def test_trade_recovery_state_is_isolated_between_paper_and_live(tmp_path):
    recovery = CrashRecovery(filepath=tmp_path / "persistent_state.json")

    recovery.save_state(-12_345.0, None, execution_mode="PAPER")
    recovery.save_state(250.0, None, execution_mode="LIVE")

    assert recovery.load_state(execution_mode="PAPER") == (-12_345.0, None)
    assert recovery.load_state(execution_mode="LIVE") == (250.0, None)


def test_legacy_unscoped_state_is_never_loaded_into_live(tmp_path):
    recovery = CrashRecovery(filepath=tmp_path / "persistent_state.json")
    recovery.save_state(-36_365.35, None)

    assert recovery.load_state(execution_mode="LIVE") == (0.0, None)
    assert recovery.load_state(execution_mode="PAPER") == (-36_365.35, None)
