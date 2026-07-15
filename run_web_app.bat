@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=python"
if exist ".venv\Scripts\python.exe" set "PYTHON=.venv\Scripts\python.exe"

"%PYTHON%" -c "import fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
  echo Installing Python backend dependencies into %PYTHON%...
  "%PYTHON%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Failed to install Python backend dependencies.
    exit /b 1
  )
)

"%PYTHON%" -c "import fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
  echo FastAPI backend dependencies are still unavailable in %PYTHON%.
  exit /b 1
)

if not exist "webui\node_modules" (
  echo Installing web UI dependencies...
  call npm.cmd install --prefix webui
  if errorlevel 1 exit /b 1
)

if not exist "webui\dist\index.html" (
  echo Building web UI...
  call npm.cmd run build --prefix webui
  if errorlevel 1 exit /b 1
)

echo Starting AutoTrader at http://127.0.0.1:8000
"%PYTHON%" -m uvicorn api.app:app --host 127.0.0.1 --port 8000
