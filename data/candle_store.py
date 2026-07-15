from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from threading import RLock

from core.models import Candle


def option_candle_key(index_symbol: str, strike: int | float, option_type: str) -> str:
    return f"{str(index_symbol).upper()}:{int(strike)}:{str(option_type).upper()}"


def spot_candle_key(index_symbol: str) -> str:
    return f"{str(index_symbol).upper()}:SPOT"


@dataclass
class _BuildingCandle:
    bucket: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    oi: int
    weighted_price: float
    weight: int
    last_cumulative_volume: int


class CompletedCandleStore:
    """Aggregates ordered ticks and exposes completed interval candles only."""

    def __init__(self, interval_seconds: int = 60, max_completed: int = 500) -> None:
        if interval_seconds <= 0 or max_completed < 2:
            raise ValueError("interval_seconds must be positive and max_completed at least 2.")
        self.interval_seconds = interval_seconds
        self._completed: dict[str, deque[Candle]] = defaultdict(lambda: deque(maxlen=max_completed))
        self._building: dict[str, _BuildingCandle] = {}
        self._last_tick: dict[str, datetime] = {}
        self._lock = RLock()

    def _bucket(self, timestamp: datetime) -> datetime:
        epoch = int(timestamp.timestamp())
        start = epoch - (epoch % self.interval_seconds)
        return datetime.fromtimestamp(start, tz=timestamp.tzinfo)

    @staticmethod
    def _completed_candle(row: _BuildingCandle) -> Candle:
        vwap = row.weighted_price / row.weight if row.weight > 0 else row.close
        return Candle(
            timestamp=row.bucket,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=row.volume,
            oi=row.oi,
            vwap=round(vwap, 4),
        )

    def add_tick(
        self,
        key: str,
        timestamp: datetime,
        price: float,
        *,
        volume: int = 0,
        oi: int = 0,
    ) -> Candle | None:
        if price <= 0.0:
            raise ValueError("tick price must be positive.")
        stream = str(key)
        bucket = self._bucket(timestamp)
        with self._lock:
            last_tick = self._last_tick.get(stream)
            if last_tick is not None and timestamp < last_tick:
                raise ValueError(f"out-of-order tick for {stream}.")
            self._last_tick[stream] = timestamp
            current = self._building.get(stream)
            if current is not None and bucket < current.bucket:
                raise ValueError(f"out-of-order candle bucket for {stream}.")

            completed = None
            if current is None or bucket > current.bucket:
                if current is not None:
                    completed = self._completed_candle(current)
                    self._completed[stream].append(completed)
                weight = 1
                self._building[stream] = _BuildingCandle(
                    bucket=bucket,
                    open=float(price),
                    high=float(price),
                    low=float(price),
                    close=float(price),
                    volume=0,
                    oi=int(oi),
                    weighted_price=float(price),
                    weight=weight,
                    last_cumulative_volume=max(0, int(volume)),
                )
                return completed

            volume_delta = max(0, int(volume) - current.last_cumulative_volume)
            weight = max(1, volume_delta)
            current.high = max(current.high, float(price))
            current.low = min(current.low, float(price))
            current.close = float(price)
            current.volume += volume_delta
            current.oi = int(oi)
            current.weighted_price += float(price) * weight
            current.weight += weight
            current.last_cumulative_volume = max(current.last_cumulative_volume, int(volume))
            return None

    def latest(self, key: str, count: int = 1) -> tuple[Candle, ...]:
        if count <= 0:
            raise ValueError("count must be positive.")
        with self._lock:
            return tuple(list(self._completed.get(str(key), ())) [-count:])

    def latest_pair(self, key: str) -> tuple[Candle, Candle] | None:
        rows = self.latest(key, 2)
        return (rows[0], rows[1]) if len(rows) == 2 else None

    def clear(self) -> None:
        with self._lock:
            self._completed.clear()
            self._building.clear()
            self._last_tick.clear()


completed_candles = CompletedCandleStore()
