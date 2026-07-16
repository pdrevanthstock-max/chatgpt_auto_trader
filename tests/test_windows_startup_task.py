from pathlib import Path


def test_startup_task_is_hidden_reversible_and_runs_only_the_web_server():
    launcher = Path("scripts/start_web_app_hidden.ps1").read_text(encoding="utf-8")
    installer = Path("scripts/install_startup_task.ps1").read_text(encoding="utf-8")
    uninstaller = Path("scripts/uninstall_startup_task.ps1").read_text(encoding="utf-8")
    stopper = Path("scripts/stop_web_app.ps1").read_text(encoding="utf-8")

    assert "127.0.0.1:8000/api/health" in launcher
    assert "api.app:app" in launcher
    assert "ui.app" not in launcher
    assert "engine/start" not in launcher
    assert "Invoke-RestMethod" not in launcher
    assert "System.Net.Sockets.TcpClient" in launcher
    assert "ConnectAsync" in launcher
    assert ".Wait(1000)" in launcher
    assert "Starting AutoTrader web service" in launcher
    assert '$ErrorActionPreference = "Continue"' in launcher
    assert "if ($exitCode -eq 0)" in launcher
    assert "Start-Process" in launcher
    assert "RedirectStandardOutput" in launcher
    assert "RedirectStandardError" in launcher
    assert "& $python -m uvicorn" not in launcher
    assert "while ($true)" in launcher
    assert "Start-Sleep -Seconds 5" in launcher
    assert "Restarting Uvicorn after unexpected exit" in launcher
    assert "web-app.pid" in launcher
    assert "Set-Content" in launcher
    assert "web-app.pid" in stopper
    assert "api.app:app" in stopper
    assert "--port 8000" in stopper
    assert "Refusing to stop" in stopper
    assert "Stop-ScheduledTask" in stopper
    assert "Stop-Process" in stopper
    assert "ParentProcessId" in stopper
    assert "Get-VerifiedDescendants" in stopper
    assert "conhost.exe" in stopper
    assert "Register-ScheduledTask" in installer
    assert "New-ScheduledTaskTrigger -AtLogOn" in installer
    assert "MultipleInstances IgnoreNew" in installer
    assert "Unregister-ScheduledTask" in uninstaller
