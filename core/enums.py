"""
Domain Enums
─────────────
All symbolic constants used across the system.
No magic strings elsewhere.
"""

from enum import Enum, auto


class ExecutionMode(str, Enum):
    """§8: Three distinct execution modes."""
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    LIVE = "LIVE"


class TradeDirection(str, Enum):
    """
    §4.5 + user clarification:
    - BULLISH → CE is entry leg, PE is hedge leg (both bought)
    - BEARISH → PE is entry leg, CE is hedge leg (both bought)
    """
    LONG_CE = "LONG_CE"   # Bullish: buy CE (entry) + buy PE (hedge)
    LONG_PE = "LONG_PE"   # Bearish: buy PE (entry) + buy CE (hedge)


class ExitReason(str, Enum):
    """§5: Independent exit triggers."""
    PER_TRADE_STOP = "PER_TRADE_STOP"           # §5.1: 2% of allocated capital
    TRAILING_STOP = "TRAILING_STOP"             # §2.1: 85% lock-in trailing
    DAILY_CIRCUIT_BREAKER = "DAILY_CIRCUIT_BREAKER"  # §5.2: 3% daily cap
    EOD_FLATTEN = "EOD_FLATTEN"                 # §3: Force-flatten at 15:00
    MANUAL = "MANUAL"                           # User-initiated


class MarketSignal(str, Enum):
    """Signal derived from velocity divergence direction."""
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NO_SIGNAL = "NO_SIGNAL"
