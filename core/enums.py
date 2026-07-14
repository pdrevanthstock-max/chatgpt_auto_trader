from enum import Enum

class ExecutionMode(str, Enum):
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    LIVE = "LIVE"

class TradeDirection(str, Enum):
    LONG_CE = "LONG_CE"  # Bullish
    LONG_PE = "LONG_PE"  # Bearish

class ExitReason(str, Enum):
    HARD_STOP = "HARD_STOP"
    GIVEBACK = "GIVEBACK"
    TARGET_HIT = "TARGET_HIT"
    ROTATION = "ROTATION"
    HEDGE_CUT = "HEDGE_CUT"
    EOD_SQUARE_OFF = "EOD_SQUARE_OFF"
    PARTIAL_FILL_ABORT = "PARTIAL_FILL_ABORT"
    MANUAL = "MANUAL"
    CIRCUIT_BREAKER_TRIGGERED = "CIRCUIT_BREAKER_TRIGGERED"

class MarketRegime(str, Enum):
    DIRECTIONAL = "DIRECTIONAL"
    SIDEWAYS = "SIDEWAYS"

class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"

class TradePhase(str, Enum):
    PHASE_1_BOTH_LEGS = "PHASE_1_BOTH_LEGS"
    PHASE_2_SINGLE_LEG = "PHASE_2_SINGLE_LEG"
    PARTIAL_EXIT = "PARTIAL_EXIT"
    CLOSED = "CLOSED"

class SignalType(str, Enum):
    ENTRY = "ENTRY"
    EXIT_BOTH = "EXIT_BOTH"
    ROTATION = "ROTATION"
    HEDGE_CUT = "HEDGE_CUT"
