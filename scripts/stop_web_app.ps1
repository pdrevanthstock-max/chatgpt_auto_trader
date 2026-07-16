$ErrorActionPreference = "Stop"
$taskName = "AutoTrader Web UI"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $projectRoot "logs\web-app.pid"
$expectedPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

function Test-ManagedCommand([object]$process) {
    $command = [string]$process.CommandLine
    return $command.Contains($expectedPython) -and `
        $command.Contains("-m uvicorn") -and `
        $command.Contains("api.app:app") -and `
        $command.Contains("--port 8000")
}

function Get-VerifiedDescendants([int]$ParentProcessId) {
    $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $ParentProcessId" -ErrorAction SilentlyContinue)
    foreach ($child in $children) {
        # Windows may attach a console host to the hidden venv launcher. It
        # carries no trading command and exits when its parent exits.
        if ([string]$child.Name -ieq "conhost.exe") {
            continue
        }
        if (-not (Test-ManagedCommand $child)) {
            throw "Refusing to stop unexpected child PID $($child.ProcessId) of managed PID $ParentProcessId."
        }
        Get-VerifiedDescendants -ParentProcessId $child.ProcessId
        $child
    }
}

# Stop the supervisor first so it cannot replace the child while this script
# is validating and stopping it.
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($task) {
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

if (-not (Test-Path -LiteralPath $pidFile)) {
    Write-Output "AutoTrader supervisor stopped. No managed Uvicorn PID file was present."
    exit 0
}

$servicePid = [int](Get-Content -LiteralPath $pidFile -Raw).Trim()
$managed = Get-CimInstance Win32_Process -Filter "ProcessId = $servicePid" -ErrorAction SilentlyContinue
if (-not $managed) {
    Remove-Item -LiteralPath $pidFile -Force
    Write-Output "AutoTrader supervisor stopped. Recorded Uvicorn process was already absent."
    exit 0
}

if (-not (Test-ManagedCommand $managed)) {
    throw "Refusing to stop PID $servicePid because its command line is not the managed AutoTrader Uvicorn service."
}

$descendants = @(Get-VerifiedDescendants -ParentProcessId $servicePid)
foreach ($descendant in $descendants) {
    Stop-Process -Id $descendant.ProcessId -Force -ErrorAction SilentlyContinue
}
Stop-Process -Id $servicePid -Force
Remove-Item -LiteralPath $pidFile -Force
Write-Output "AutoTrader Web UI service stopped (PID $servicePid)."
