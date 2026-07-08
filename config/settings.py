"""
Application Settings — Single Source of Truth
───────────────────────────────────────────────
§6: All configurable parameters live here.
     No constants.py, no magic numbers scattered across files.

Secrets (.env):       DHAN_CLIENT_ID, DHAN_ACCESS_TOKEN
Trading params:       config.json (UI-editable)
Everything else:      Derived from the above two sources.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = PROJECT_ROOT / "config.json"
DATABASE_DIR = PROJECT_ROOT / "database"
REPORTS_DIR = PROJECT_ROOT / "reports"
CACHE_DIR = PROJECT_ROOT / "cache"

# Ensure directories exist
DATABASE_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────
# Secrets (from .env only — never in config.json)
# ─────────────────────────────────────────────

DHAN_CLIENT_ID: str = os.getenv("DHAN_CLIENT_ID", "")
DHAN_ACCESS_TOKEN: str = os.getenv("DHAN_ACCESS_TOKEN", "")


# ─────────────────────────────────────────────
# Trading Configuration (UI-editable)
# ─────────────────────────────────────────────

@dataclass
class TradingConfig:
    """
    Every tunable parameter in the system.
    Saved to / loaded from config.json.
    UI edits this, code reads this. One source of truth.
    """

    # ── Capital (§6) ──
    total_capital: float = 30_000.0

    # ── Entry Signal (§4 / user's velocity approach) ──
    divergence_min_pct: float = 1.0     # lower band of entry window
    divergence_max_pct: float = 1.5     # upper band of entry window
    candle_interval_minutes: int = 2    # aggregate 1-min into N-min candles
    scan_matrix_range: int = 5          # ATM ± N strikes (5-10, per user)

    # ── Per-trade exit (§5.1) ──
    per_trade_stop_pct: float = 0.02    # 2% of allocated capital

    # ── Trailing stop (§2.1 / user: 85% lock-in) ──
    trail_lock_factor: float = 0.85     # lock 85% of peak profit
    trail_activation_amount: float = 0.0  # activate trailing after any profit (0 = immediate)

    # ── Daily circuit breaker (§5.2) ──
    daily_loss_limit_pct: float = 0.03  # 3% of total capital

    # ── Trading window (§3) ──
    scan_start: str = "09:30"           # IST, no trades before this
    scan_end: str = "15:00"             # IST, force-flatten at this time

    # ── Position sizing (§6) ──
    nifty_lot_size: int = 25            # Nifty options lot size

    # ── Execution mode (§8) ──
    execution_mode: str = "BACKTEST"    # BACKTEST | PAPER | LIVE

    # ── Scan interval (for paper/live) ──
    scan_interval_seconds: int = 120

    # ── Backtest date range ──
    backtest_from_date: str = ""
    backtest_to_date: str = ""

    # ── Derived (not saved) ──
    @property
    def daily_loss_limit(self) -> float:
        """Absolute ₹ amount for circuit breaker."""
        return self.total_capital * self.daily_loss_limit_pct

    def save(self, path: Path = None) -> None:
        """Persist config to JSON."""
        path = path or CONFIG_FILE
        data = asdict(self)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: Path = None) -> TradingConfig:
        """Load config from JSON, falling back to defaults for missing keys."""
        path = path or CONFIG_FILE
        if not path.exists():
            config = cls()
            config.save(path)
            return config

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Only accept known fields (forward-compatible)
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


# ─────────────────────────────────────────────
# App Metadata
# ─────────────────────────────────────────────

APP_NAME = "AutoTrader"
APP_VERSION = "3.0.0"  # Major version bump: complete strategy rewrite