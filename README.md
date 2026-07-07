# AutoTrader-alpha

**Automated NIFTY Options Trading System** — Connects to the Dhan broker API to analyze, rank, and trade NIFTY options in real-time.

---

## What It Does

AutoTrader downloads the live NIFTY option chain every 30 seconds, analyzes all CE (Call) and PE (Put) pairs around the ATM strike, ranks them by liquidity/volume/OI/spread quality, determines if the market is BULLISH or BEARISH, and automatically opens, monitors, and closes trades.

## Trading Schedule

| Phase | Time (IST) | Behaviour |
|-------|-----------|-----------|
| **Pre-Market** | Before 9:15 | System idle, waiting for market open |
| **Monitoring** | 9:15 – 9:30 | Downloads option chain, observes first-15-min volatility, determines market trend. **No trades placed.** |
| **Trading** | 9:30 – 15:00 | Executes trades based on trend established during monitoring phase |
| **Post-Close** | After 15:00 | Stops scanning for new trades; manages existing open positions until they exit |

## Strategy

### Directional Trading (Active)

> The market is moving in one direction — ride the trend.

- **BULLISH** → Buy Call Option (LONG_CE)
- **BEARISH** → Buy Put Option (LONG_PE)
- **Stop Loss**: 2% below entry price
- **Trailing Stop**: Activates at +1% profit, locks in 90% of unrealised gains
- **No fixed target** — trailing stop handles profit exits
- **Daily loss cap**: 3% of capital → stops trading for the day

### Sideways Trading (Planned — Not Yet Implemented)

> The market is flat — make small profits repeatedly.

- Buy small, take 5% profit, exit, re-enter
- Will be built after directional engine is fully validated

## Quick Start

### Prerequisites

- Python 3.10+
- Dhan trading account with API access
- NIFTY F&O enabled

### Setup

```bash
# Clone the repository
git clone https://github.com/pdrevanthstock-max/AutoTrader-alpha.git
cd AutoTrader-alpha

# Create virtual environment
python -m venv venv
venv\Scripts\activate       # Windows
source venv/bin/activate    # macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the project root:

```env
DHAN_CLIENT_ID=your_client_id
DHAN_ACCESS_TOKEN=your_access_token
```

### Run

```bash
# Paper trading (default — no real orders)
python -m engine.trading_scheduler

# Or run the scheduler directly
python -c "from engine.trading_scheduler import TradingScheduler; TradingScheduler().start()"
```

### Run Tests

```bash
python -m tests.test_exit_flow
python -m tests.test_position_lifecycle
python -m tests.test_trading_engine
```

## Project Structure

```
AutoTrader-alpha/
├── alpha/                    # Intelligence Pipeline (Signal Generation)
│   ├── option_chain.py       # Downloads live NIFTY option chain from Dhan
│   ├── strike_selector.py    # Finds ATM strike and creates strike window
│   ├── dynamic_window.py     # Auto-expands window until enough valid pairs
│   ├── pair_generator.py     # Creates all CE/PE pair combinations
│   ├── liquidity_filter.py   # Removes illiquid options
│   ├── feature_extractor.py  # Extracts distance, OI, volume, spread, Greeks
│   ├── market_statistics.py  # Calculates min/max for normalization
│   ├── normalized_scorer.py  # Scores each pair 0-1 across features
│   ├── pair_ranker_v2.py     # Ranks all pairs by composite score
│   ├── market_confirmation.py# Determines BULLISH/BEARISH/SIDEWAYS from spot vs strikes
│   ├── decision_engine.py    # Maps market signal → trade direction
│   ├── trade_planner.py      # Builds complete trade plan with security IDs
│   ├── paper_executor.py     # Simulates order fill for paper trading
│   ├── broker_executor.py    # Places real orders through Dhan API (inactive)
│   └── market_state.py       # Stores recent market observations
│
├── engine/                   # Execution Engine (Trade Management)
│   ├── trading_engine.py     # Runs one complete scan + trade cycle
│   ├── trading_scheduler.py  # Runs engine continuously during market hours
│   ├── trade_manager.py      # Maintains one active paper position
│   ├── position_decision.py  # Decides ENTRY / HOLD / REVERSE
│   ├── execution_manager.py  # Routes to Paper or Live executor
│   ├── risk_manager.py       # Applies 2% SL, trailing on
│   ├── position_monitor.py   # Updates PnL, checks stop-loss triggers
│   ├── trailing_manager.py   # Ratchets stop-loss upward after +1% profit
│   ├── exit_manager.py       # Finalises position, calculates final PnL
│   └── price_lookup.py       # Finds current option price by security_id
│
├── database/                 # Data Persistence
│   ├── position_store.py     # Saves/loads current_position.json
│   └── trade_journal.py      # Appends completed trades to trade_history.json
│
├── analytics/                # Post-Trade Analysis
│   └── trade_statistics.py   # Win/loss rate, net PnL summary
│
├── broker/                   # Broker Integration
│   ├── dhan_client.py        # Dhan API client wrapper
│   ├── broker_interface.py   # Abstract broker interface
│   └── market_data.py        # Market data fetcher
│
├── config/                   # Configuration
│   ├── constants.py          # Market hours, paths, trading params
│   └── settings.py           # App name, version
│
├── tests/                    # Test Suite
│   ├── test_exit_flow.py     # Stop-loss and trailing exit tests
│   ├── test_position_lifecycle.py # Full trade lifecycle test
│   └── ...                   # Module-level unit tests
│
├── .env                      # API credentials (git-ignored)
├── .gitignore
├── requirements.txt
└── README.md
```

## Risk Management

| Parameter | Value |
|-----------|-------|
| Per-trade stop loss | 2% |
| Trailing activation | +1% profit |
| Trailing lock-in | 90% of unrealised gains |
| Daily loss cap | 3% of capital |
| Max open positions | 1 |
| Default capital | ₹25,000 |

## Execution Modes

| Mode | Status | Description |
|------|--------|-------------|
| **PAPER** | ✅ Active | Simulated order fills — no real money |
| **LIVE** | ⚠️ Coded, not active | Real Dhan API orders — requires manual switch |

To switch to live mode, set `ExecutionManager.MODE = "LIVE"` in `engine/execution_manager.py`. **Only do this after thorough backtesting and paper trading validation.**

## License

Private repository. All rights reserved.
