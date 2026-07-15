from pathlib import Path


def test_startup_task_is_hidden_reversible_and_runs_only_the_web_server():
    launcher = Path("scripts/start_web_app_hidden.ps1").read_text(encoding="utf-8")
    installer = Path("scripts/install_startup_task.ps1").read_text(encoding="utf-8")
    uninstaller = Path("scripts/uninstall_startup_task.ps1").read_text(encoding="utf-8")

    assert "127.0.0.1:8000/api/health" in launcher
    assert "api.app:app" in launcher
    assert "ui.app" not in launcher
    assert "engine/start" not in launcher
    assert "Register-ScheduledTask" in installer
    assert "New-ScheduledTaskTrigger -AtLogOn" in installer
    assert "MultipleInstances IgnoreNew" in installer
    assert "Unregister-ScheduledTask" in uninstaller
