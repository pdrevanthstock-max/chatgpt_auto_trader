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

    def __init__(self) -> None:
        if not DHAN_CLIENT_ID or not DHAN_ACCESS_TOKEN:
            logger.warning("DHAN_CLIENT_ID or DHAN_ACCESS_TOKEN not set in environment.")
        
        # Initialize context and client
        self.ctx = DhanContext(client_id=DHAN_CLIENT_ID, access_token=DHAN_ACCESS_TOKEN)
        self.client = dhanhq(self.ctx)
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

    def get_positions(self) -> List[Dict[str, Any]]:
        """Fetch open positions from broker."""
        try:
            resp = self.client.get_positions()
            if resp.get("status") == "success":
                return resp.get("data", [])
            return []
        except Exception as e:
            logger.error(f"Failed to fetch live positions: {e}")
            return []
