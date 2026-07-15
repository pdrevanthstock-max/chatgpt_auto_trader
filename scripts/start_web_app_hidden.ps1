$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$logDirectory = Join-Path $projectRoot "logs"
$outputLog = Join-Path $logDirectory "web-app-service.log"
$errorLog = Join-Path $logDirectory "web-app-service-error.log"

Set-Location -LiteralPath $projectRoot
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null

try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 2
    if ($health.status -eq "ok") {
        exit 0
    }
} catch {
    # No healthy existing instance; this task becomes the foreground server owner.
}

if (-not (Test-Path -LiteralPath $python)) {
    "[$(Get-Date -Format o)] Missing virtual-environment Python: $python" | Add-Content -LiteralPath $errorLog
    exit 1
}

& $python -m uvicorn api.app:app --host 127.0.0.1 --port 8000 1>> $outputLog 2>> $errorLog
exit $LASTEXITCODE
