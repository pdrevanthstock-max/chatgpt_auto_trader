# Changelog

All notable changes to the AutoTrader-alpha project.

---

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
