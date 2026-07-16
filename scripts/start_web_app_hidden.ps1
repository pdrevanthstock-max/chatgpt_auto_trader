$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$logDirectory = Join-Path $projectRoot "logs"
$launcherLog = Join-Path $logDirectory "web-app-launcher.log"
$outputLog = Join-Path $logDirectory "web-app-service.log"
$errorLog = Join-Path $logDirectory "web-app-service-error.log"
$pidFile = Join-Path $logDirectory "web-app.pid"
$healthUrl = "http://127.0.0.1:8000/api/health"

Set-Location -LiteralPath $projectRoot
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null

function Test-LocalPort {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $connect = $client.ConnectAsync("127.0.0.1", 8000)
        return $connect.Wait(1000) -and $client.Connected
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

if (Test-LocalPort) {
    "[$(Get-Date -Format o)] Port 8000 is already accepting connections; launcher exited without starting a duplicate." | Add-Content -LiteralPath $launcherLog
    exit 0
}

if (-not (Test-Path -LiteralPath $python)) {
    "[$(Get-Date -Format o)] Missing virtual-environment Python: $python" | Add-Content -LiteralPath $errorLog
    exit 1
}

"[$(Get-Date -Format o)] Starting AutoTrader web service. Health endpoint: $healthUrl" | Add-Content -LiteralPath $launcherLog
while ($true) {
    try {
        # Start-Process keeps Uvicorn's normal stderr out of PowerShell's error
        # stream. Windows PowerShell 5.1 otherwise wraps INFO lines as a false
        # NativeCommandError when ErrorActionPreference is Stop.
        $ErrorActionPreference = "Continue"
        $uvicorn = Start-Process `
            -FilePath $python `
            -ArgumentList @("-m", "uvicorn", "api.app:app", "--host", "127.0.0.1", "--port", "8000") `
            -WorkingDirectory $projectRoot `
            -WindowStyle Hidden `
            -RedirectStandardOutput $outputLog `
            -RedirectStandardError $errorLog `
            -PassThru
        $uvicorn.Id | Set-Content -LiteralPath $pidFile -Encoding ascii
        $uvicorn.WaitForExit()
        $exitCode = $uvicorn.ExitCode
        if ((Test-Path -LiteralPath $pidFile) -and ((Get-Content -LiteralPath $pidFile -Raw).Trim() -eq [string]$uvicorn.Id)) {
            Remove-Item -LiteralPath $pidFile -Force
        }
        $ErrorActionPreference = "Stop"
        if ($exitCode -eq 0) {
            "[$(Get-Date -Format o)] Uvicorn exited cleanly; supervisor stopped." | Add-Content -LiteralPath $launcherLog
            exit 0
        }
        "[$(Get-Date -Format o)] Uvicorn exited with code $exitCode. Restarting Uvicorn after unexpected exit in 5 seconds." | Add-Content -LiteralPath $errorLog
    } catch {
        $ErrorActionPreference = "Stop"
        "[$(Get-Date -Format o)] Launcher exception: $($_.Exception.Message). Restarting Uvicorn after unexpected exit in 5 seconds." | Add-Content -LiteralPath $errorLog
    }
    Start-Sleep -Seconds 5
}
