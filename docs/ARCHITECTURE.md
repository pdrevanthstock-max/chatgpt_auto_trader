# Architecture

## System Overview

AutoTrader-alpha is a modular automated trading system with a clear separation between **signal generation** (alpha) and **trade execution** (engine). The system operates on a scheduler loop that runs every 30 seconds during market hours.

```
┌──────────────────────────────────────────────────────────────────┐
│                     TRADING SCHEDULER                           │
│                                                                  │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────────────┐    │
│  │ Pre-Market  │──>│  Monitor    │──>│     Trading Phase    │    │
│  │  (< 9:15)   │   │ (9:15-9:30) │   │    (9:30-15:00)     │    │
│  └─────────────┘   └─────────────┘   └─────────────────────┘    │
│                                              │                    │
│                         ┌────────────────────┴──────────┐        │
│                         │                               │        │
│                  ┌──────▼──────┐              ┌─────────▼──────┐ │
│                  │ search_trade│              │manage_position │ │
│                  │ (no position│              │(has position)  │ │
│                  └──────┬──────┘              └─────────┬──────┘ │
│                         │                               │        │
└─────────────────────────┼───────────────────────────────┼────────┘
                          │                               │
           ALPHA PIPELINE │                   ENGINE CORE │
                          ▼                               ▼
```

## Module Architecture

### Layer 1: Alpha Pipeline (Signal Generation)

The alpha pipeline processes raw market data into a ranked trading signal. Each module is stateless and testable independently.

```
OptionChain.download()
    │
    ▼
StrikeSelector.get_window()
    │
    ▼
PairGenerator.generate()         → All CE/PE combinations
    │
    ▼
LiquidityFilter.filter()        → Remove illiquid options
    │
    ▼
PairRankerV2.rank()              → Score & rank by composite
    │                               (volume, OI, spread, distance)
    ▼
MarketConfirmation.confirm()     → BULLISH / BEARISH / SIDEWAYS
    │
    ▼
DecisionEngine.decide()          → LONG_CE / LONG_PE / None
    │
    ▼
TradePlanner.build()             → Complete trade plan
    │
    ▼
RiskManager.apply()              → Add SL, trailing params
```

### Layer 2: Engine Core (Trade Management)

The engine maintains position state and handles the trade lifecycle.

```
TradingEngine.run()
    │
    ├── No position? → search_trade()
    │       │
    │       ├── Run alpha pipeline
    │       ├── PositionDecision.decide() → ENTRY / HOLD / REVERSE
    │       └── TradeManager.open() → PaperExecutor / BrokerExecutor
    │
    └── Has position? → manage_position()
            │
            ├── PriceLookup.get_price()    → Current market price
            ├── PositionMonitor.update()   → PnL + stop-loss check
            ├── TrailingManager.update()   → Ratchet SL upward
            │
            ├── Exit triggered?
            │       ├── ExitManager.close()    → Finalise PnL
            │       ├── TradeJournal.append()  → Record to history
            │       └── TradeManager.clear()   → Delete position file
            │
            └── No exit → save position, continue
```

### Layer 3: Data Persistence

```
database/
├── current_position.json    → Active position (deleted after exit)
└── trade_history.json       → All completed trades (append-only)
```

### Layer 4: Broker Integration

```
ExecutionManager
├── MODE = "PAPER"  →  PaperExecutor  (simulated fills)
└── MODE = "LIVE"   →  BrokerExecutor (Dhan API orders)
```

## Data Flow: Complete Trade Cycle

```
1. ENTRY CYCLE
   OptionChain → StrikeSelector → PairGenerator → LiquidityFilter
   → PairRankerV2 → MarketConfirmation → DecisionEngine
   → TradePlanner → RiskManager → PaperExecutor
   → PositionStore.save()

2. MANAGE CYCLE (every 30s)
   OptionChain → PriceLookup → PositionMonitor → TrailingManager
   → (if SL hit) → ExitManager → TradeJournal → PositionStore.clear()

3. DAILY RISK
   TradingScheduler reads trade_history.json
   → Sums today's PnL
   → If loss > 3% of capital → stop trading
```

## Key Design Decisions

### 1. No Fixed Target — Trailing Stop Only

Traditional SL/Target exits leave money on the table during strong trends. The trailing stop:
- Activates at +1% profit (avoids false triggers)
- Locks in 90% of unrealised gains
- Only moves UP, never down
- Results in larger winners, bounded losers

### 2. Monitor-First Approach (9:15–9:30)

The first 15 minutes of Indian market open are the most volatile. Instead of trading into chaos:
- System downloads option chain during 9:15–9:30
- Tracks spot price movement and ATM shifts
- Builds a trend picture BEFORE placing any order
- Trading starts at 9:30 with an informed view

### 3. Single Position at a Time

Complexity scales quadratically with position count. One position means:
- Clear risk management (2% SL = known max loss)
- No hedging conflicts
- Simple state machine: ENTRY → MANAGE → EXIT

### 4. Paper-First Execution

`ExecutionManager.MODE = "PAPER"` by default. The system must prove itself on simulated fills before touching real money.

## Configuration Reference

| Constant | Value | File |
|----------|-------|------|
| `MARKET_OPEN` | 09:15 | `config/constants.py` |
| `MARKET_CLOSE` | 15:00 | `config/constants.py` |
| `DEFAULT_CAPITAL` | ₹25,000 | `config/constants.py` |
| `STOP_LOSS_PCT` | 2% | `engine/risk_manager.py` |
| `TRAIL_ACTIVATION` | 1% | `engine/risk_manager.py` |
| `TRAIL_FACTOR` | 90% | `engine/risk_manager.py` |
| `DAILY_LOSS_LIMIT` | 3% | `engine/trading_scheduler.py` |
| `MONITOR_START` | 09:15 | `engine/trading_scheduler.py` |
| `TRADE_START` | 09:30 | `engine/trading_scheduler.py` |
