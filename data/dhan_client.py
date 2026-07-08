"""
Dhan API Client
────────────────
Thin wrapper around DhanHQ SDK 2.2.0.
Handles only the API calls this system actually uses.

§7.2 gotchas are encoded here:
  - expiry_code=1 (not 0)
  - CE and PE fetched separately
  - strike="ATM" is a rolling reference
"""

from __future__ import annotations

import time
from typing import Dict, Any, Optional

from loguru import logger

from config.settings import DHAN_CLIENT_ID, DHAN_ACCESS_TOKEN
from core.exceptions import DataFetchError, ConfigurationError


class DhanClient:
    """
    Minimal Dhan API client.
    Only exposes methods this project actually uses.
    """

    # Retry config for rate limiting (§Beyond the Scope #3)
    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 2.0  # seconds, doubles each retry

    def __init__(self):
        if not DHAN_CLIENT_ID or not DHAN_ACCESS_TOKEN:
            raise ConfigurationError(
                "DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN must be set in .env"
            )

        from dhanhq import DhanContext, dhanhq

        self._context = DhanContext(DHAN_CLIENT_ID, DHAN_ACCESS_TOKEN)
        self._client = dhanhq(self._context)
        logger.info("Dhan client initialized")

    def get_expired_options_data(
        self,
        option_type: str,         # "CALL" or "PUT"
        from_date: str,           # "YYYY-MM-DD"
        to_date: str,             # "YYYY-MM-DD"
        strike: str = "ATM",      # "ATM", "ATM+1", etc.
        interval: int = 1,        # minutes: 1, 5, 15, 25, 60
        expiry_code: int = 1,     # §7.2: MUST be 1, not 0
        security_id: int = 13,    # 13 = NIFTY
    ) -> Dict[str, Any]:
        """
        Fetch historical option candle data via Dhan's rolling-option endpoint.

        §7.2 known gotchas applied:
          - expiry_code=1 always (0 causes server error)
          - option_type must be "CALL" or "PUT" (no combined fetch)
          - strike="ATM" is relative, changes daily

        Returns raw API response dict with OHLCV + IV + OI data.
        """
        if option_type not in ("CALL", "PUT"):
            raise DataFetchError(
                f"option_type must be 'CALL' or 'PUT', got '{option_type}'"
            )

        payload = {
            "exchangeSegment": "NSE_FNO",
            "instrument": "OPTIDX",
            "securityId": str(security_id),
            "expiryFlag": "MONTH",
            "expiryCode": expiry_code,
            "strike": strike,
            "drvOptionType": option_type,
            "interval": interval,
            "fromDate": from_date,
            "toDate": to_date,
            "requiredData": ["open", "high", "low", "close", "volume"],
        }

        return self._request_with_retry(payload)

    def get_option_chain(self, expiry: str) -> Dict[str, Any]:
        """Fetch live option chain (for paper/live trading later)."""
        return self._client.option_chain(
            under_security_id=13,
            under_exchange_segment=self._client.INDEX,
            expiry=expiry,
        )

    def get_expiry_list(self) -> Dict[str, Any]:
        """Fetch available expiry dates for NIFTY options."""
        return self._client.expiry_list(
            under_security_id=13,
            under_exchange_segment=self._client.INDEX,
        )

    def _request_with_retry(self, payload: Dict) -> Dict[str, Any]:
        """
        POST to rolling-option endpoint with exponential backoff.
        Dhan has undocumented rate limits — this prevents silent failures.
        """
        last_error: Optional[Exception] = None

        for attempt in range(self.MAX_RETRIES):
            try:
                # The dhanhq SDK's internal method for this endpoint
                response = self._client.historical_minute_charts(
                    symbol="",
                    exchange_segment="NSE_FNO",
                    instrument_type="OPTIDX",
                    expiry_code=payload["expiryCode"],
                    from_date=payload["fromDate"],
                    to_date=payload["toDate"],
                )

                # If SDK doesn't have the direct method, fall back to raw POST
                if response is None:
                    raise DataFetchError("SDK returned None")

                return response

            except AttributeError:
                # SDK version may not have this method — use raw request
                import requests

                url = "https://api.dhan.co/v2/charts/rollingoption"
                headers = {
                    "Content-Type": "application/json",
                    "access-token": DHAN_ACCESS_TOKEN,
                }

                resp = requests.post(url, json=payload, headers=headers, timeout=30)

                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 429:
                    # Rate limited
                    delay = self.RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        f"Rate limited (429). Retrying in {delay}s "
                        f"(attempt {attempt + 1}/{self.MAX_RETRIES})"
                    )
                    time.sleep(delay)
                    last_error = DataFetchError(f"Rate limited: {resp.text}")
                    continue
                else:
                    raise DataFetchError(
                        f"Dhan API error {resp.status_code}: {resp.text}"
                    )

            except Exception as e:
                delay = self.RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    f"API request failed: {e}. "
                    f"Retrying in {delay}s (attempt {attempt + 1}/{self.MAX_RETRIES})"
                )
                time.sleep(delay)
                last_error = e

        raise DataFetchError(
            f"Failed after {self.MAX_RETRIES} retries. Last error: {last_error}"
        )
