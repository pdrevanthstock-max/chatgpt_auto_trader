from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Callable, Generic, Optional, TypeVar


T = TypeVar("T")


class MarketDataErrorCode(str, Enum):
    EMPTY_RESPONSE = "EMPTY_RESPONSE"
    NON_JSON_RESPONSE = "NON_JSON_RESPONSE"
    BROKER_FAILURE = "BROKER_FAILURE"
    REQUEST_EXCEPTION = "REQUEST_EXCEPTION"


@dataclass(frozen=True)
class MarketDataResult(Generic[T]):
    ok: bool
    endpoint: str
    value: Optional[T] = None
    error_code: Optional[MarketDataErrorCode] = None
    message: str = ""
    preview: str = ""
    correlation_id: str = ""
    attempt_count: int = 1


class SafeMarketResponse:
    _SECRET_PATTERN = re.compile(
        r"(?i)(access[_-]?token\s*[=:]\s*[\"']?)([^\s\"'&<>]+)"
    )

    @classmethod
    def _preview(cls, raw: object, limit: int = 240) -> str:
        text = str(raw).replace("\r", " ").replace("\n", " ")
        text = cls._SECRET_PATTERN.sub(r"\1[REDACTED]", text)
        return text[:limit]

    @classmethod
    def normalize(
        cls,
        raw: Any,
        *,
        endpoint: str,
        correlation_id: str = "",
    ) -> MarketDataResult[dict[str, Any]]:
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            return MarketDataResult(
                ok=False,
                endpoint=endpoint,
                error_code=MarketDataErrorCode.EMPTY_RESPONSE,
                message="Market-data provider returned an empty response.",
                correlation_id=correlation_id,
            )

        parsed = raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return MarketDataResult(
                    ok=False,
                    endpoint=endpoint,
                    error_code=MarketDataErrorCode.NON_JSON_RESPONSE,
                    message="Market-data provider returned a non-JSON response.",
                    preview=cls._preview(raw),
                    correlation_id=correlation_id,
                )

        if not isinstance(parsed, dict):
            return MarketDataResult(
                ok=False,
                endpoint=endpoint,
                error_code=MarketDataErrorCode.NON_JSON_RESPONSE,
                message="Market-data response must be a JSON object.",
                preview=cls._preview(parsed),
                correlation_id=correlation_id,
            )

        if str(parsed.get("status", "")).lower() != "success":
            return MarketDataResult(
                ok=False,
                endpoint=endpoint,
                error_code=MarketDataErrorCode.BROKER_FAILURE,
                message="Market-data provider returned a failure status.",
                preview=cls._preview(parsed),
                correlation_id=correlation_id,
            )

        return MarketDataResult(
            ok=True,
            endpoint=endpoint,
            value=parsed,
            correlation_id=correlation_id,
        )


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.25

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1.")
        if self.base_delay_seconds < 0.0:
            raise ValueError("base_delay_seconds cannot be negative.")

    def run(
        self,
        operation: Callable[[], Any],
        *,
        endpoint: str,
        correlation_id: str = "",
        sleep: Callable[[float], None] = time.sleep,
    ) -> MarketDataResult[dict[str, Any]]:
        last: MarketDataResult[dict[str, Any]] | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                last = SafeMarketResponse.normalize(
                    operation(), endpoint=endpoint, correlation_id=correlation_id
                )
            except Exception as exc:
                last = MarketDataResult(
                    ok=False,
                    endpoint=endpoint,
                    error_code=MarketDataErrorCode.REQUEST_EXCEPTION,
                    message=f"Market-data request failed: {type(exc).__name__}",
                    preview=SafeMarketResponse._preview(exc),
                    correlation_id=correlation_id,
                )
            last = replace(last, attempt_count=attempt)
            if last.ok:
                return last
            if attempt < self.max_attempts:
                sleep(self.base_delay_seconds * (2 ** (attempt - 1)))
        assert last is not None
        return last
