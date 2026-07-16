$ErrorActionPreference = "Stop"
$taskName = "AutoTrader Web UI"

& (Join-Path $PSScriptRoot "stop_web_app.ps1")

$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($null -ne $task) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}
