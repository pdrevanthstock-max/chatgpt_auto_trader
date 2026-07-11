class AutoTraderException(Exception):
    """Base exception for all AutoTrader errors."""
    pass

class PartialFillError(AutoTraderException):
    """Raised when only one leg of a basket order is filled within the timeout."""
    pass

class BrokerConnectionError(AutoTraderException):
    """Raised when connection to broker fails or times out."""
    pass

class HealthCheckFailure(AutoTraderException):
    """Raised when system health monitor checks fail, gating entry."""
    pass

class StaleDataError(AutoTraderException):
    """Raised when the MarketCache data is too old."""
    pass

class InsufficientDataError(AutoTraderException):
    """Raised when there is not enough historical or live data to process."""
    pass

class DataFetchError(AutoTraderException):
    """Raised when data fetching from the Dhan API fails."""
    pass

class CircuitBreakerTriggered(AutoTraderException):
    """Raised when daily loss limit is hit and new trades are blocked."""
    pass
