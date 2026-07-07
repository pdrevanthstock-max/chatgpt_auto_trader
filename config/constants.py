"""
Application Constants
---------------------

This file contains constants that are used across the entire project.

Avoid putting business logic here.

Only reusable constant values.
"""

from pathlib import Path

# =====================================================
# PROJECT PATHS
# =====================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATABASE_FOLDER = PROJECT_ROOT / "database"

REPORT_FOLDER = PROJECT_ROOT / "reports"

CSV_FOLDER = REPORT_FOLDER / "csv"

LOG_FOLDER = REPORT_FOLDER / "logs"

# =====================================================
# MARKET TIMINGS
# =====================================================

MARKET_OPEN = "09:15"

MARKET_CLOSE = "15:00"

SCAN_INTERVAL_SECONDS = 120

# =====================================================
# TRADING
# =====================================================

DEFAULT_CAPITAL = 25000

MAX_OPEN_POSITIONS = 1

DEFAULT_TARGET_PERCENT = 1.0

DEFAULT_STOPLOSS_PERCENT = 0.50

DEFAULT_TRAILING_OFFSET = 0.30

# =====================================================
# DATABASE
# =====================================================

DATABASE_NAME = "autotrader.db"

DATABASE_PATH = DATABASE_FOLDER / DATABASE_NAME

# =====================================================
# LOGGING
# =====================================================

LOG_FILE = LOG_FOLDER / "autotrader.log"