from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from numbers import Real

from core.exceptions import PartialFillError


class AtomicPaperLimitFill:
    """Wait for both PAPER buy limits to be executable in one quote snapshot."""

    def __init__(
        self,
        *,
        chain_provider: Callable[[], Mapping[object, object]],
        timeout_seconds: float,
        poll_seconds: float,
        monotonic: Callable[[], float],
        sleep: Callable[[float], None],
    ) -> None:
        self._chain_provider = chain_provider
        self._timeout_seconds = max(0.0, float(timeout_seconds))
        self._poll_seconds = max(0.01, float(poll_seconds))
        self._monotonic = monotonic
        self._sleep = sleep

    @staticmethod
    def _ask(quote: Mapping[str, object] | None, leg: str) -> float:
        if not quote:
            raise PartialFillError(
                f"PAPER atomic limit fill aborted: {leg} quote is missing."
            )
        ask = quote.get("ask")
        if (
            isinstance(ask, bool)
            or not isinstance(ask, Real)
            or not math.isfinite(float(ask))
            or float(ask) <= 0.0
        ):
            raise PartialFillError(
                f"PAPER atomic limit fill aborted: {leg} ask is invalid."
            )
        return float(ask)

    def wait(
        self,
        *,
        ce_strike: object,
        pe_strike: object,
        ce_limit: float,
        pe_limit: float,
    ) -> tuple[float, float]:
        deadline = self._monotonic() + self._timeout_seconds

        while True:
            chain = self._chain_provider()
            ce_quote = chain.get(ce_strike, {}).get("CE")
            pe_quote = chain.get(pe_strike, {}).get("PE")
            ce_ask = self._ask(ce_quote, "CE")
            pe_ask = self._ask(pe_quote, "PE")

            if ce_ask <= ce_limit and pe_ask <= pe_limit:
                return ce_ask, pe_ask

            now = self._monotonic()
            if now >= deadline:
                raise PartialFillError(
                    "PAPER atomic limit fill timed out with no trade created: "
                    f"CE buy limit {ce_limit:.2f} vs ask {ce_ask:.2f}; "
                    f"PE buy limit {pe_limit:.2f} vs ask {pe_ask:.2f}."
                )

            self._sleep(min(self._poll_seconds, deadline - now))
