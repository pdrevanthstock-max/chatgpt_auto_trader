# AutoTrader v6.0.0

## New modular web UI (PAPER validation build)

The replacement UI runs independently of Streamlit and binds to localhost:

```powershell
.\run_web_app.bat
```

Open `http://127.0.0.1:8000`. This FastAPI/React application is the authoritative UI for PAPER validation. It provides engine controls, runtime index selection, period P&L, active-position quantity and marks, diagnostics capture/downloads, activity streaming, journal history, and audited PAPER capital adjustments.

The Streamlit application remains available only as a legacy compatibility surface. Do not run both UIs during normal PAPER testing because the FastAPI process owns the server-authoritative web runtime. Streamlit retirement requires a separate user-approved decommission decision.

### Start automatically after Windows sign-in

Install the current-user scheduled task once from PowerShell:

```powershell
.\scripts\install_startup_task.ps1
```

The task is named `AutoTrader Web UI`, starts after this user's Windows logon, and keeps the local service available at `http://127.0.0.1:8000`. It starts only FastAPI/React: the trading engine remains stopped, LIVE remains disabled, and no broker order is submitted automatically.

Remove the automatic-start task with:

```powershell
.\scripts\uninstall_startup_task.ps1
```

Latest launcher logs are stored under `logs/web-app-launcher.log`, `logs/web-app-service.log`, and `logs/web-app-service-error.log`.

Manual service controls from PowerShell:

```powershell
Start-ScheduledTask -TaskName "AutoTrader Web UI"
.\scripts\stop_web_app.ps1
Get-ScheduledTask -TaskName "AutoTrader Web UI"
Get-ScheduledTaskInfo -TaskName "AutoTrader Web UI"
```

The guarded stop script terminates both the task supervisor and its verified Uvicorn child. It therefore stops risk
monitoring. Never run it while the dashboard reports an active position. Use the dashboard's **Stop engine** control
first; that control refuses to stop while a position is open. For a copyable engine trace, use:

```powershell
Get-Content .\logs\engine-activity.log -Tail 200 -Wait
Get-Content .\logs\web-app-service-error.log -Tail 200 -Wait
```

The launcher supervises unexpected Uvicorn exits and retries after five seconds. It deliberately does **not**
automatically restart the trading engine: after a backend crash, inspect recovery state and explicitly start the PAPER
engine from the UI. If only the browser fails while the API remains healthy, the backend continues running; validate
it with `Invoke-RestMethod http://127.0.0.1:8000/api/runtime`.

### PAPER market-day phases

- Before `09:05` IST: premarket idle, with a status heartbeat no more than once per ten minutes.
- `09:05`–`09:15`: startup countdown.
- `09:15`–`09:30`: feed and completed-candle observation warm-up; new entries remain disabled.
- `09:30`–`15:10`: entry window; scans remain limited to completed candles and the configured 60-second interval.
- After `15:10`: no new entries. Open-position risk and exits continue on the one-second loop through square-off.

The production entry adapter currently trades only NIFTY. BANKNIFTY and FINNIFTY are approved registry targets but
their feeds are not connected; MIDCPNIFTY and NIFTYNXT50 are observe-only and also feed-pending. Checkbox selection
does not override those runtime boundaries.

**Adaptive Option Pair Divergence Capture System for NIFTY**

> **Current engineering handoff:** See [`docs/SYSTEM_EVOLUTION_AND_CURRENT_ARCHITECTURE_2026-07-13_TO_2026-07-14.md`](docs/SYSTEM_EVOLUTION_AND_CURRENT_ARCHITECTURE_2026-07-13_TO_2026-07-14.md) for the July 13–14 change history, current requirement precedence, pair-selection rules, execution safeguards, capital controls, test evidence, and unresolved LIVE blockers.

AutoTrader v6.0.0 is a strictly modular algorithmic trading system built to capture pricing divergence between NIFTY options contracts. Rather than trying to predict market direction, the system scans the cross-strike options matrix, identifies structural imbalances, and dynamically opens, rotates, and exits hedge pairs in real-time.

---

## Architecture & Data Flow

```
Dhan WebSocket Feed (ticks) 
  └─► MarketCache (In-Memory Database)
        ├─► Spot / ATM Strike
        ├─► Option Chain / Bid-Ask Spreads
        └─► Greeks / IV Percentiles
              │
        ┌─────┴────────────────────────────────────────┐
        ▼                                              ▼
  Backtest Replay Engine                       Live / Paper Loop (Stoppable)
        │                                              │
        └──────────────┬───────────────────────────────┘
                       ▼
             Pair Candidate Generator (ATM ± 10 Strikes)
                       ▼
             Liquidity Filter (Volume, OI, and Spreads)
                       ▼
             Divergence Velocity Scanner
                       ▼
             Entry Signal Gating (2-Conditions check)
                       ▼
             Pair Ranker (Projected Net Profit)
                       ▼
             Trade Planner & Position Sizer (Nifty lot size = 65)
                       ▼
             Execution Validator & serialized FIFO Queue
                       ▼
             Executors (Paper Simulation / Broker orders via asyncio)
```

---

## Strategy Rules

### 1. Market Hours & Timing
- **Trading Window**: `09:30` to `15:20` IST.
- **Entry Cutoff**: `15:10` IST (No entries allowed after this).
- **EOD Flatten**: `15:20` IST (Force close all open positions).

### 2. Scanning & Candidate Generation
- **Scope**: ATM ±10 strikes.
- **Cartesian Space**: 21 CEs × 21 PEs = 441 candidate combinations scanned every cycle.
- **Liquidity Filter**: Applied *before* candidate building to reject illiquid strikes:
  - Volume (last 10 candles) ≥ 100 contracts.
  - Open Interest (OI) ≥ 1000 contracts.
  - Bid-Ask Spread ≤ ₹0.50 or 2% of mid-price.

### 3. Entry Signal Conditions
Both rules must pass simultaneously:
1. **Divergence Band**: Absolute difference in CE & PE percentage velocity falls within configured band (1% to 5% default, up to 15% via slider).
2. **Directional Consistency**:
   - Spot up → CE velocity ≥ PE velocity.
   - Spot down → PE velocity ≥ CE velocity.
   - Spot sideways → no bias required.

### 4. Sizing & Lot Size
- Lot count is calculated dynamically based on capital (default ₹30,000) and combined premium.
- Lot size is locked to Nifty's contract size: **65**.

### 5. Exits & Hedge Cut (Directional Phase 2)
- **Giveback stop**: 10% peak profit giveback trailing rule applied to combined positions.
- **Dynamic profit target (Sideways only)**: Target scaled by ATM IV percentile (0.04 to 0.06 factor) + round-trip brokerage. Targets scale by 1.5x during the pre-close window (15:00 - 15:20) to handle wider spreads.
- **Hedge-cut (Directional only)**: Drop the losing leg when combined profit crosses the threshold (₹300 flat if winning leg value < ₹10K; 2.5% of winning value if ≥ ₹10K) and trail the winning leg under Phase 2 single-leg giveback.

### 6. Rotation Engine
Positions rotate to higher-scoring pairs if all five criteria are met:
1. Higher score (hysteresis ≥ +0.30 points to prevent churn).
2. Faster divergence velocity.
3. Banked minimum profit floor (Rs 103).
4. Liquid targets.
5. Sufficient time remaining (> 60s before EOD).
- *Cooldown*: Rotated strikes are barred from re-entry for 3 candles.

---

## Folder Layout

The codebase has been refactored to align with a strict Separation of Concerns (SoC) model:

- `core/` — Domain data dataclasses ([models.py](file:///c:/Users/LENOVO/Desktop/New%20folder%20(3)/AutoTrader-alpha/core/models.py)), enums ([enums.py](file:///c:/Users/LENOVO/Desktop/New%20folder%20(3)/AutoTrader-alpha/core/enums.py)), and exception definitions.
- `config/` — Configuration settings and JSON load/save operations ([settings.py](file:///c:/Users/LENOVO/Desktop/New%20folder%20(3)/AutoTrader-alpha/config/settings.py)).
- `data/` — Data fetchers and thread-locked cache database ([market_cache.py](file:///c:/Users/LENOVO/Desktop/New%20folder%20(3)/AutoTrader-alpha/data/market_cache.py)).
- `strategy/` — Single-responsibility strategy files (candidates, liquidity, scanner, entry signals, ranker, decision memory, exit managers, and rotation).
- `execution/` — Orders, serialized FIFO queue, state crash-recovery.
- `monitoring/` — Gating health checks for system latency, spreads, memory and CPU usage.
- `reporting/` — Professional 3-sheet Excel report builders.
- `ui/` — Interactive dashboard control panel with Start/Stop controls.
- `tests/` — Component-level unit test suites.

---

## How to Get Started

### 1. Requirements Installation
Ensure Python 3.10+ is installed, then run:
```bash
pip install -r requirements.txt
```

### 2. Configure Credentials
Add your Dhan API details to the `.env` file in the project root:
```env
DHAN_CLIENT_ID=your_id
DHAN_ACCESS_TOKEN=your_token
```

### 3. Launch the authoritative PAPER dashboard

Run:

```powershell
.\run_web_app.bat
```

Then open `http://127.0.0.1:8000`. The legacy Streamlit UI is not the normal operational entry point.

### 4. Run Test Suite
Validate strategy math and queue routines:
```bash
python -m pytest tests/ -v
```
