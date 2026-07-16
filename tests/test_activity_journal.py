from application.activity_journal import ActivityJournal


def test_activity_journal_persists_copyable_engine_messages(tmp_path):
    path = tmp_path / "engine-activity.log"
    journal = ActivityJournal(path=path, max_bytes=10_000, backup_count=2)

    journal.append("[2026-07-16 09:05:00] Startup countdown active.")

    assert path.read_text(encoding="utf-8") == (
        "[2026-07-16 09:05:00] Startup countdown active.\n"
    )
