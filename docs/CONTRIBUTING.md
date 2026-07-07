# Contributing & Development Guide

## Development Setup

```bash
# Clone and setup
git clone https://github.com/pdrevanthstock-max/AutoTrader-alpha.git
cd AutoTrader-alpha
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# Copy env template
cp .env.example .env
# Edit .env with your Dhan credentials
```

## Running Tests

```bash
# Exit flow tests (stop-loss, trailing)
python -m tests.test_exit_flow

# Full lifecycle tests (open → trail → exit → journal → clear)
python -m tests.test_position_lifecycle

# Individual module tests
python -m tests.test_decision_engine
python -m tests.test_market_confirmation
python -m tests.test_pair_generator
python -m tests.test_liquidity_filter
python -m tests.test_normalized_scorer
python -m tests.test_pair_ranker_v2
python -m tests.test_paper_executor
python -m tests.test_trade_planner
```

> **Note (Windows)**: If you see Unicode errors, set the encoding:
> ```powershell
> $env:PYTHONIOENCODING='utf-8'; python -m tests.test_exit_flow
> ```

## Module Guide

### Adding a New Alpha Module

1. Create file in `alpha/` directory
2. Use `@staticmethod` or `@classmethod` pattern (stateless)
3. Input: data from previous pipeline stage
4. Output: transformed data for next stage
5. Add test in `tests/test_<module_name>.py`

### Modifying Risk Parameters

All risk parameters are in two places:

| Parameter | Location |
|-----------|----------|
| Stop loss % | `engine/risk_manager.py` → `STOP_LOSS_PCT` |
| Trail activation | `engine/risk_manager.py` → `TRAIL_ACTIVATION` |
| Trail factor | `engine/risk_manager.py` → `TRAIL_FACTOR` |
| Daily loss limit | `engine/trading_scheduler.py` → `DAILY_LOSS_LIMIT` |
| Market hours | `engine/trading_scheduler.py` → `MONITOR_START` / `TRADE_START` / `MARKET_CLOSE` |

### Switching to Live Mode

```python
# In engine/execution_manager.py
# Change:
MODE = "PAPER"
# To:
MODE = "LIVE"
```

**WARNING**: Only do this after:
1. ✅ Strategy validated on paper trading for at least 2 weeks
2. ✅ Risk parameters confirmed
3. ✅ Dhan API credentials verified
4. ✅ Daily loss cap tested

## Git Workflow

```bash
# Check what changed
git status
git diff --stat

# Stage and commit
git add -A
git commit -m "descriptive message"

# Push
git push origin main
```

## File Naming Conventions

| Directory | Pattern | Example |
|-----------|---------|---------|
| `alpha/` | `<noun>_<noun>.py` | `option_chain.py`, `pair_ranker_v2.py` |
| `engine/` | `<noun>_<noun>.py` | `trade_manager.py`, `exit_manager.py` |
| `tests/` | `test_<module>.py` | `test_exit_flow.py` |
| `database/` | `<noun>_<noun>.py` | `position_store.py` |
