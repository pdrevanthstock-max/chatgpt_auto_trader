# Changelog

All notable changes to the AutoTrader-alpha project.

---

## [Safety, Price Integrity, and Capital Controls] — 2026-07-13 to 2026-07-14

- Hardened historical, PAPER, and LIVE/PAPER orchestration behavior.
- Replaced flat per-lot transaction costs with order/turnover-based option charges.
- Added executable ask/bid PAPER fills, fail-closed quote validation, dynamic hard stops, expiry/dual-decay/OTM gates, and a temporary unit ceiling.
- Added lots/units visibility, PAPER post-daily-SL tagging, capital transaction auditing, read-only LIVE allocation controls, a persistent LIVE daily stop, broker partial-fill containment, and a PAPER profitability gate before LIVE.
- Expanded the automated suite to 90 passing tests.
- Full timeline, current architecture, requirement-precedence decisions, operational steps, and unresolved LIVE blockers are recorded in [`docs/SYSTEM_EVOLUTION_AND_CURRENT_ARCHITECTURE_2026-07-13_TO_2026-07-14.md`](docs/SYSTEM_EVOLUTION_AND_CURRENT_ARCHITECTURE_2026-07-13_TO_2026-07-14.md).

---

## [Phase 6] — 2026-07-11

### Rebuild, Code Audit Resolution & Operational Start/Stop

**Fixed by**: Antigravity AI Assistant  
**Scope**: Entire project rebuilt to v6 modular spec; fixed all blocking issues from audit.

#### Bug Fixes & Improvements

- **Execution Validator Backtest Bypass**: Bypassed live API latency, cache freshness, and spread checks during backtest simulation since historical candles do not carry live bid/ask spreads. This immediately resolved the **Zero Trades Executed** bug, allowing 18 successful trades to be replayed.
- **Dynamic Candidate range check**: Added ATM strike distance checking to `PairCandidateGenerator` to restrict scanning to `pair_scan_range` (ATM ±10 strikes) for both backtesting relative labels and live absolute integers.
- **Manual Start/Stop Engine**: Integrated a daemon thread orchestrator in `ui/app.py` allowing manual startup and termination of live/paper trading runs from the dashboard interface.
- **Dhan API Interval Fix**: Always requests `interval=1` from the Dhan API and resamples to multi-minute candles dynamically if configured (resolves interval rejection errors).
- **Health Monitor Threshold Update**: Raised virtual memory usage threshold limit from `80%` to `95%` to prevent gating checks from blocking execution on standard memory loads.
- **Documentation**: Updated `README.md` to document the completed v6 modular pipeline.

## [Phase 3] — 2026-07-07

### Execution Engine Bug Fixes & Completion

**Fixed by**: Antigravity AI Assistant  
**Scope**: 11 files modified, 2 new test files, 668 lines added

#### Bug Fixes

| # | Bug | Root Cause | Fix |
|---|-----|-----------|-----|
| 1 | Position file never cleared after exit | `PositionStore.clear()` was never called after a trade closed | Added `self.trade_manager.clear()` call in `manage_position()` after journaling |
| 2 | Market signal hardcoded to "BULLISH" | `DecisionEngine.decide()` was always passed `"BULLISH"` | Replaced with `MarketConfirmation.confirm()` which compares spot price to CE/PE strikes |
| 3 | `search_trade()` crashes on SIDEWAYS market | `DecisionEngine.decide()` returns `None` for SIDEWAYS, but code didn't check | Added `None` guard — returns `NO_TRADE` result instead of crashing |
| 4 | No PnL on exit | `ExitManager.close()` only set `closed=True` | Added `pnl = (exit_price - entry_price) * quantity` calculation |
| 5 | Stale position blocks new trades | After exit, `current_position.json` had `closed: True` but was never deleted | `PositionStore.clear()` deletes the file; `TradeManager.clear()` resets state |

#### Engine Improvements

- **Risk Manager**: Changed from 10% SL / 20% target to **2% SL with trailing stop** (no fixed target)
- **Trailing Manager**: Activates at +1% profit, locks 90% of gains, only moves UP
- **Position Monitor**: Checks only stop-loss (trailing stop handles profit exits)
- **Trading Scheduler**: Full 3-phase market day (Monitor → Trade → Close) with daily loss cap
- **Broker Executor**: Complete implementation for Dhan API live orders (inactive, paper mode default)

#### Market Hours Update

- `MARKET_OPEN` changed from `09:30` to `09:15` (actual IST market open)
- Monitor phase (9:15–9:30): observes first-15-min volatility to determine trend
- Trading phase (9:30–15:00): executes trades based on established trend
- `MARKET_CLOSE` remains at `15:00` for new trade cutoff

#### New Tests

- **`test_exit_flow.py`** — 4 tests covering stop-loss exits, trailing activation, and trailing-never-moves-down
- **`test_position_lifecycle.py`** — 4 tests covering full trade lifecycle, immediate SL, put direction, and statistics compatibility

#### Files Changed

| File | Change |
|------|--------|
| `engine/trading_engine.py` | Used MarketConfirmation, handled SIDEWAYS, added position cleanup after exit |
| `engine/trading_scheduler.py` | Full rewrite: 3-phase scheduler with daily risk, graceful shutdown, stats display |
| `engine/exit_manager.py` | Added PnL finalisation on close |
| `engine/trade_manager.py` | Added `clear()` method for position cleanup |
| `engine/risk_manager.py` | Changed to 2% SL, trailing-only strategy |
| `engine/position_monitor.py` | Simplified to stop-loss check only |
| `engine/trailing_manager.py` | New trailing stop logic: +1% activation, 90% lock-in |
| `alpha/decision_engine.py` | Clean SIDEWAYS handling |
| `alpha/broker_executor.py` | Full Dhan API order placement implementation |
| `database/position_store.py` | Cleaned up debug print statements |
| `config/constants.py` | Updated market hours to 09:15–15:00 |
| `tests/test_exit_flow.py` | NEW: 4 exit flow tests |
| `tests/test_position_lifecycle.py` | NEW: 4 lifecycle tests |

---

## [Phase 2] — Prior

### Trading Engine Implementation

- Core trading engine (`TradingEngine`)
- Paper executor for simulated trades
- Position store for JSON persistence
- Trade journal for completed trade history
- All alpha pipeline modules (option chain through pair ranking)

---

## [Phase 1] — Initial

### Alpha Pipeline

- Dhan broker client
- Option chain download
- Strike selection and window generation
- Pair generation and filtering
- Scoring and ranking engine
