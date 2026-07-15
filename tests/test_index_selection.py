from application.index_selection import IndexSelectionService
from core.index_registry import IndexPermission, IndexRegistry


def test_registry_contains_three_tradable_and_two_observe_only_indices():
    registry = IndexRegistry.default()

    assert registry.symbols == {
        "NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"
    }
    assert registry.get("NIFTY").lot_size == 65
    assert registry.get("BANKNIFTY").lot_size == 30
    assert registry.get("FINNIFTY").lot_size == 60
    assert registry.get("MIDCPNIFTY").permission is IndexPermission.OBSERVE_ONLY
    assert registry.get("NIFTYNXT50").permission is IndexPermission.OBSERVE_ONLY


def test_selection_defaults_to_all_and_supports_one_many_and_pause():
    service = IndexSelectionService(IndexRegistry.default())

    initial = service.snapshot()
    one = service.update({"BANKNIFTY"}, expected_version=initial.version)
    many = service.update(
        {"NIFTY", "FINNIFTY"}, expected_version=one.version
    )
    paused = service.update(set(), expected_version=many.version)

    assert initial.is_all is True
    assert one.symbols == frozenset({"BANKNIFTY"})
    assert many.symbols == frozenset({"NIFTY", "FINNIFTY"})
    assert paused.pause_new_entries is True
    assert paused.symbols == frozenset()


def test_stale_ui_version_cannot_overwrite_newer_selection():
    service = IndexSelectionService(IndexRegistry.default())
    initial = service.snapshot()
    service.update({"NIFTY"}, expected_version=initial.version)

    try:
        service.update({"BANKNIFTY"}, expected_version=initial.version)
    except ValueError as error:
        assert "selection version" in str(error).lower()
    else:
        raise AssertionError("A stale selection update must be rejected.")


def test_unknown_index_is_rejected_and_changes_are_audited():
    service = IndexSelectionService(IndexRegistry.default())
    initial = service.snapshot()

    try:
        service.update({"NIFTY", "SENSEX"}, expected_version=initial.version)
    except ValueError as error:
        assert "SENSEX" in str(error)
    else:
        raise AssertionError("Unknown indices must be rejected.")

    updated = service.update({"NIFTY"}, expected_version=initial.version)
    event = service.audit_events[-1]
    assert event.previous == initial.symbols
    assert event.current == updated.symbols
    assert event.version == updated.version


def test_web_runtime_receives_authoritative_selection_service():
    runtime_source = __import__("pathlib").Path("application/runtime_service.py").read_text(encoding="utf-8")
    engine_source = __import__("pathlib").Path("ui/app.py").read_text(encoding="utf-8")

    assert "index_selection=selection" in runtime_source
    assert "self.index_selection.snapshot()" in engine_source
    assert "selection_snapshot.pause_new_entries" in engine_source
    assert '"NIFTY" not in selection_snapshot.symbols' in engine_source
