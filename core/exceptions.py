"""
Domain Exceptions
──────────────────
Specific, catchable exceptions instead of bare RuntimeError.
"""


class AutoTraderError(Exception):
    """Base exception for all AutoTrader errors."""
    pass


class DataFetchError(AutoTraderError):
    """Failed to fetch data from Dhan API."""
    pass


class InsufficientDataError(AutoTraderError):
    """Not enough data points to compute signals."""
    pass


class CircuitBreakerTriggered(AutoTraderError):
    """§5.2: Daily loss limit reached. No more trades today."""
    pass


class ConfigurationError(AutoTraderError):
    """Invalid or missing configuration."""
    pass


class InvalidTradeError(AutoTraderError):
    """Trade violates a business rule (e.g., unequal leg quantities)."""
    pass
