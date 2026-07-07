# Requirements & Specifications

## Functional Requirements

### FR-1: Market Data Ingestion
- **FR-1.1**: Download live NIFTY option chain from Dhan API
- **FR-1.2**: Extract spot price, CE/PE data for all strikes
- **FR-1.3**: Refresh data every 30 seconds during trading hours

### FR-2: Option Pair Analysis
- **FR-2.1**: Select ATM strike and create a window of nearby strikes
- **FR-2.2**: Generate all valid CE/PE pair combinations
- **FR-2.3**: Filter out illiquid options (low volume, wide spreads)
- **FR-2.4**: Score pairs by: distance from ATM, OI, volume, bid-ask spread, IV
- **FR-2.5**: Rank pairs by composite score (normalised 0–1)

### FR-3: Market Direction
- **FR-3.1**: Determine market direction (BULLISH / BEARISH / SIDEWAYS)
- **FR-3.2**: Use spot price vs CE/PE strike comparison (`MarketConfirmation`)
- **FR-3.3**: Monitor first 15 minutes (9:15–9:30) before trading
- **FR-3.4**: Map direction to trade: BULLISH → LONG_CE, BEARISH → LONG_PE

### FR-4: Trade Execution
- **FR-4.1**: Paper mode (default) — simulate order fills
- **FR-4.2**: Live mode (coded, inactive) — real Dhan API orders
- **FR-4.3**: One position at a time (no concurrent trades)
- **FR-4.4**: Position persistence in `current_position.json`

### FR-5: Risk Management
- **FR-5.1**: Per-trade stop loss: 2% below entry
- **FR-5.2**: Trailing stop: activates at +1% profit, locks 90% of gains
- **FR-5.3**: Trailing stop only moves UP, never down
- **FR-5.4**: No fixed target — trailing stop handles all profit exits
- **FR-5.5**: Daily loss cap: 3% of capital → stops all trading

### FR-6: Position Management
- **FR-6.1**: Monitor open position every 30 seconds
- **FR-6.2**: Update PnL with current market price
- **FR-6.3**: Check stop-loss trigger on every update
- **FR-6.4**: Apply trailing stop adjustments
- **FR-6.5**: On exit: finalise PnL, journal trade, clear position file

### FR-7: Trade History
- **FR-7.1**: Record all completed trades in `trade_history.json`
- **FR-7.2**: Calculate win/loss stats and net PnL
- **FR-7.3**: Display daily statistics after each exit

### FR-8: Scheduling
- **FR-8.1**: Pre-market (before 9:15): system idle
- **FR-8.2**: Monitor phase (9:15–9:30): observe market, no trades
- **FR-8.3**: Trading phase (9:30–15:00): execute trades
- **FR-8.4**: Post-close (after 15:00): manage existing positions only
- **FR-8.5**: Graceful shutdown on Ctrl+C

---

## Non-Functional Requirements

### NFR-1: Reliability
- System must handle API failures gracefully (retry or skip cycle)
- Position file must survive process restart
- Trade journal must be append-only (no data loss)

### NFR-2: Performance
- Each trading cycle must complete within 10 seconds
- Option chain download is the bottleneck (~2-3s)

### NFR-3: Safety
- Paper mode by default — live mode requires explicit code change
- Daily loss cap prevents catastrophic losses
- Single position limit prevents overexposure

### NFR-4: Testability
- All alpha pipeline modules are stateless and testable in isolation
- Engine modules use dependency injection for testability
- Test suite uses temporary files (never touches production data)

---

## Technical Requirements

### Environment
- Python 3.10+
- Windows / macOS / Linux
- Dhan trading account with F&O enabled

### Dependencies
- `dhanhq` — Dhan broker API client
- `loguru` — Structured logging
- `python-dotenv` — Environment variable management
- `pandas` / `numpy` — Data processing
- `schedule` — Job scheduling

### Data Files
- `database/current_position.json` — Active position (transient)
- `database/trade_history.json` — Completed trades (persistent)
- `security_id_list.csv` — Dhan security ID reference (~28MB)
- `.env` — API credentials (git-ignored)
