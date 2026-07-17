from application.system_health import SystemHealthService


def test_system_health_applies_warning_and_critical_thresholds():
    assert SystemHealthService(lambda: (25.0, 40.0)).snapshot().status == "NORMAL"
    assert SystemHealthService(lambda: (75.0, 40.0)).snapshot().status == "WARNING"
    assert SystemHealthService(lambda: (25.0, 85.0)).snapshot().status == "WARNING"
    assert SystemHealthService(lambda: (90.0, 40.0)).snapshot().status == "CRITICAL"
    assert SystemHealthService(lambda: (25.0, 95.0)).snapshot().status == "CRITICAL"


def test_system_health_reports_unavailable_without_fake_percentages():
    def unavailable():
        raise RuntimeError("metrics unavailable")

    snapshot = SystemHealthService(unavailable).snapshot()

    assert snapshot.status == "UNAVAILABLE"
    assert snapshot.cpu_percent is None
    assert snapshot.memory_percent is None
    assert "unavailable" in snapshot.explanation.lower()


def test_system_health_snapshot_has_json_safe_dict():
    snapshot = SystemHealthService(lambda: (76.25, 82.5)).snapshot()

    assert snapshot.as_dict() == {
        "cpu_percent": 76.25,
        "memory_percent": 82.5,
        "status": "WARNING",
        "explanation": "Warning: CPU is at or above 75%.",
    }
