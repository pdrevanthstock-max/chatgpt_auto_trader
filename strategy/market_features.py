from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from core.models import Candle


@dataclass(frozen=True)
class MarketFeatures:
    closes: tuple[float, ...]
    highs: tuple[float, ...]
    lows: tuple[float, ...]
    vwap_values: tuple[float, ...]
    atr_values: tuple[float, ...]


class MarketFeatureCalculator:
    """Derives aligned regime inputs from completed OHLCV candles."""

    @staticmethod
    def calculate(candles: Iterable[Candle]) -> MarketFeatures:
        rows = tuple(candles)
        if not rows:
            raise ValueError("completed candles are required.")
        if any(candle.vwap <= 0.0 for candle in rows):
            raise ValueError("real candle VWAP is required; synthetic spot-as-VWAP is prohibited.")
        atr: list[float] = []
        previous_close: float | None = None
        for candle in rows:
            true_range = candle.high - candle.low
            if previous_close is not None:
                true_range = max(
                    true_range,
                    abs(candle.high - previous_close),
                    abs(candle.low - previous_close),
                )
            atr.append(round(float(true_range), 4))
            previous_close = candle.close
        return MarketFeatures(
            closes=tuple(float(row.close) for row in rows),
            highs=tuple(float(row.high) for row in rows),
            lows=tuple(float(row.low) for row in rows),
            vwap_values=tuple(float(row.vwap) for row in rows),
            atr_values=tuple(atr),
        )
