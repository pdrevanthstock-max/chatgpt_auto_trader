from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = PROJECT_ROOT / "config.json"
DATABASE_DIR = PROJECT_ROOT / "database"
REPORTS_DIR = PROJECT_ROOT / "reports"
CACHE_DIR = PROJECT_ROOT / "cache"

DATABASE_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)

DHAN_CLIENT_ID: str = os.getenv("DHAN_CLIENT_ID", "")
DHAN_ACCESS_TOKEN: str = os.getenv("DHAN_ACCESS_TOKEN", "")

@dataclass
class TradingConfig:
    # Capital
    total_capital: float = 30000.0

    # Option specs
    nifty_lot_size: int = 65
    pair_scan_range: int = 10  # ATM ± N strikes (default 10)
    candle_interval_minutes: int = 2

    # Entry criteria
    divergence_band_min: float = 1.0   # % change divergence lower band
    divergence_band_max: float = 5.0   # % change divergence upper band

    # Exit parameters (Phase 1)
    giveback_pct: float = 0.10          # 10% giveback of peak profits

    # Hedge-cut parameters (Directional only)
    hedge_cut_threshold_flat: float = 300.0   # Flat Rs if winning leg value < 10000
    hedge_cut_threshold_pct: float = 0.025    # 2.5% of winning leg value if >= 10000
    hedge_cut_value_breakpoint: float = 10000.0

    # Risk Management
    daily_loss_limit_pct: float = 0.03        # 3% of capital

    # Trading Hours (IST)
    scan_start: str = "09:30"
    scan_end: str = "15:20"
    last_entry_time: str = "15:10"

    # Rotation parameters
    rotation_min_profit_floor: float = 103.0   # Minimum banked net profit
    rotation_score_hysteresis: float = 0.30    # Re-entry requires +0.30 score improvement
    rotation_cooldown_candles: int = 3         # Cooldown in candles before re-entering same pair

    # IV Target Scaling (Sideways only)
    iv_percentile_low: int = 20
    iv_percentile_high: int = 80

    # Pre-close window scaling
    preclose_window_start: str = "15:00"
    preclose_entry_cutoff: str = "15:10"

    # Health Checks
    health_check_api_latency_ms: int = 500
    health_check_spread_max: float = 1.50
    health_check_cache_stale_sec: int = 1

    # App controls
    execution_mode: str = "BACKTEST"  # BACKTEST | PAPER | LIVE
    scan_interval_seconds: int = 120
    backtest_from_date: str = ""
    backtest_to_date: str = ""

    @property
    def daily_loss_limit(self) -> float:
        return self.total_capital * self.daily_loss_limit_pct

    def save(self, path: Path = None) -> None:
        path = path or CONFIG_FILE
        data = asdict(self)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: Path = None) -> TradingConfig:
        path = path or CONFIG_FILE
        if not path.exists():
            config = cls()
            config.save(path)
            return config

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)

APP_NAME = "AutoTrader"
APP_VERSION = "6.0.0"
