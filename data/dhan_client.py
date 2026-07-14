import time
import logging
from typing import Dict, Any, List
from dhanhq import DhanContext, dhanhq
from config.settings import DHAN_CLIENT_ID, DHAN_ACCESS_TOKEN
from core.exceptions import DataFetchError

logger = logging.getLogger("AutoTrader")

class DhanClient:
    """Wrapper around Dhan SDK with retry logic and error handling."""
    MAX_RETRIES = 5
    RETRY_BASE_DELAY = 1.0

    def __init__(self, orders_enabled: bool = False) -> None:
        if not DHAN_CLIENT_ID or not DHAN_ACCESS_TOKEN:
            logger.warning("DHAN_CLIENT_ID or DHAN_ACCESS_TOKEN not set in environment.")
        
        # Initialize context and client
        self.ctx = DhanContext(client_id=DHAN_CLIENT_ID, access_token=DHAN_ACCESS_TOKEN)
        self.client = dhanhq(self.ctx)
        self.orders_enabled = bool(orders_enabled)
        logger.info("Dhan client wrapper initialized")

    def get_expired_options_data(
        self,
        option_type: str,
        from_date: str,
        to_date: str,
        strike: str,
        security_id: str = "13",  # default NIFTY
        expiry_flag: str = "WEEK",
        expiry_code: int = 1,
        interval: int = 1,
    ) -> Dict[str, Any]:
        """
        Fetch historical expired options data.
        """
        if option_type not in ("CALL", "PUT"):
            raise DataFetchError(f"option_type must be 'CALL' or 'PUT', got {option_type}")

        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.client.expired_options_data(
                    security_id=security_id,
                    exchange_segment="NSE_FNO",
                    instrument_type="OPTIDX",
                    expiry_flag=expiry_flag,
                    expiry_code=expiry_code,
                    strike=strike,
                    drv_option_type=option_type,
                    required_data=["open", "high", "low", "close", "volume"],
                    from_date=from_date,
                    to_date=to_date,
                    interval=interval,
                )
                if response is None:
                    raise DataFetchError("SDK returned None response")
                return response
            except Exception as e:
                delay = self.RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    f"Dhan API call failed on attempt {attempt+1}/{self.MAX_RETRIES}: {e}. "
                    f"Retrying in {delay}s..."
                )
                time.sleep(delay)

        raise DataFetchError(f"Failed to fetch options data after {self.MAX_RETRIES} attempts.")

    def place_order(self, order_details: Dict[str, Any]) -> str:
        """Place live order on Dhan. Returns order ID."""
        if not getattr(self, "orders_enabled", False):
            raise DataFetchError("Dhan order writes are disabled for this client session.")
        try:
            # Structurally valid live order placement
            # Using order placement structure from Dhan API
            resp = self.client.place_order(**order_details)
            if resp.get("status") == "success":
                return resp.get("data", {}).get("orderId", "")
            else:
                raise DataFetchError(f"Order placement failed: {resp}")
        except Exception as e:
            raise DataFetchError(f"Failed to place order: {e}")

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending live order; order writes must be explicitly enabled."""
        if not getattr(self, "orders_enabled", False):
            raise DataFetchError("Dhan order writes are disabled for this client session.")
        try:
            response = self.client.cancel_order(order_id)
            if not isinstance(response, dict) or response.get("status") != "success":
                raise DataFetchError(f"Order cancellation failed: {response}")
            data = response.get("data", {})
            status = str(data.get("orderStatus", "CANCELLED")).upper()
            if status != "CANCELLED":
                raise DataFetchError(
                    f"Order {order_id} cancellation was not confirmed: {response}"
                )
            return True
        except Exception as e:
            if isinstance(e, DataFetchError):
                raise
            raise DataFetchError(f"Failed to cancel order {order_id}: {e}")

    def get_positions(self) -> List[Dict[str, Any]]:
        """Fetch open positions from broker."""
        try:
            resp = self.client.get_positions()
            if isinstance(resp, dict) and resp.get("status") == "success":
                return resp.get("data", [])
            return []
        except Exception as e:
            logger.error(f"Failed to fetch live positions: {e}")
            return []

    def get_fund_limits(self) -> Dict[str, float]:
        """Return normalized read-only broker funds for allocation validation."""
        try:
            response = self.client.get_fund_limits()
            if not isinstance(response, dict) or response.get("status") != "success":
                raise DataFetchError(f"Fund-limit query failed: {response}")
            data = response.get("data")
            if not isinstance(data, dict):
                raise DataFetchError(f"Fund-limit response has no data: {response}")
            available = data.get("availabelBalance", data.get("availableBalance"))
            if available is None:
                raise DataFetchError("Fund-limit response has no available balance.")
            return {
                "available_balance": float(available),
                "utilized_amount": float(data.get("utilizedAmount", 0.0) or 0.0),
                "sod_limit": float(data.get("sodLimit", 0.0) or 0.0),
            }
        except Exception as e:
            if isinstance(e, DataFetchError):
                raise
            raise DataFetchError(f"Failed to fetch fund limits: {e}")
    def get_order_by_id(self, order_id: str) -> Dict[str, Any]:
        """Return the broker's current order record; placement alone is not a fill."""
        try:
            response = self.client.get_order_by_id(order_id)
            if not isinstance(response, dict) or response.get("status") != "success":
                raise DataFetchError(f"Order status query failed: {response}")
            data = response.get("data")
            if not isinstance(data, dict):
                raise DataFetchError(f"Order status response has no order data: {response}")
            return data
        except Exception as e:
            if isinstance(e, DataFetchError):
                raise
            raise DataFetchError(f"Failed to query order {order_id}: {e}")

    def validate_credentials(self) -> bool:
        """
        Runs a pre-flight query to verify Dhan API credentials.
        Raises ValueError if authentication fails.
        """
        try:
            resp = self.client.get_positions()
            if isinstance(resp, dict) and resp.get("status") == "failure":
                remarks = resp.get("remarks", {})
                error_msg = remarks.get("error_message") or "Unknown error"
                error_type = remarks.get("error_type") or ""
                
                # Check for authentication failures
                if "Authentication" in error_type or "access token" in error_msg.lower() or "authentication" in error_msg.lower():
                    raise ValueError(f"Dhan Access Token expired or invalid: {error_msg}")
                else:
                    # Raise a general exception for other failures (e.g. rate limits or connection failures)
                    raise ValueError(f"Dhan API returned failure status: {error_msg} (type: {error_type})")
            elif isinstance(resp, str) and "Invalid_Authentication" in resp:
                raise ValueError("Dhan Access Token expired or invalid.")
            return True
        except Exception as e:
            # Re-raise any ValueError we explicitly raised
            if isinstance(e, ValueError):
                raise
            # If it's a generic exception, log it and raise it as an authentication/connection failure
            logger.error(f"Dhan validation failed with error: {e}")
            raise ValueError(f"Dhan validation failed: {e}")
