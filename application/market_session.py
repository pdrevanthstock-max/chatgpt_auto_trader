from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from enum import Enum


class MarketPhase(str, Enum):
    PREMARKET_IDLE = "PREMARKET_IDLE"
    STARTUP_COUNTDOWN = "STARTUP_COUNTDOWN"
    OBSERVATION_WARMUP = "OBSERVATION_WARMUP"
    ENTRY_WINDOW = "ENTRY_WINDOW"
    ENTRY_CLOSED = "ENTRY_CLOSED"
    MARKET_CLOSED = "MARKET_CLOSED"


@dataclass(frozen=True)
class MarketSessionStatus:
    phase: MarketPhase
    seconds_to_next_phase: int
    status_interval_seconds: int
    entries_allowed: bool
    message: str


class MarketSessionSchedule:
    """Describes the IST market-day phases used by the PAPER entry loop."""

    startup_countdown = time(9, 5)
    observation_start = time(9, 15)
    entry_start = time(9, 30)
    entry_cutoff = time(15, 10)
    market_close = time(15, 20)

    @staticmethod
    def _seconds_until(now: datetime, target: time) -> int:
        target_dt = now.replace(
            hour=target.hour, minute=target.minute, second=target.second, microsecond=0
        )
        return max(0, int((target_dt - now).total_seconds()))

    @staticmethod
    def _duration(seconds: int) -> str:
        minutes, remaining = divmod(max(0, seconds), 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}h {minutes:02d}m {remaining:02d}s"
        return f"{minutes}m {remaining:02d}s"

    def at(self, now: datetime) -> MarketSessionStatus:
        current = now.time()
        if now.weekday() >= 5:
            return MarketSessionStatus(
                MarketPhase.MARKET_CLOSED, 0, 600, False,
                "Market is closed for the weekend. New entries remain disabled.",
            )
        if current < self.startup_countdown:
            remaining = self._seconds_until(now, self.startup_countdown)
            return MarketSessionStatus(
                MarketPhase.PREMARKET_IDLE, remaining, 600, False,
                "Premarket idle. Startup countdown begins at 09:05 IST in "
                f"{self._duration(remaining)}; market observation begins at 09:15 "
                "and PAPER entries at 09:30.",
            )
        if current < self.observation_start:
            remaining = self._seconds_until(now, self.observation_start)
            return MarketSessionStatus(
                MarketPhase.STARTUP_COUNTDOWN, remaining, 60, False,
                "Market-data startup countdown active. Observation begins at 09:15 IST in "
                f"{self._duration(remaining)}; PAPER entries remain disabled until 09:30.",
            )
        if current < self.entry_start:
            remaining = self._seconds_until(now, self.entry_start)
            return MarketSessionStatus(
                MarketPhase.OBSERVATION_WARMUP, remaining, 60, False,
                "Observation warm-up active. Feed and completed candles are monitored; "
                f"PAPER entries begin at 09:30 IST in {self._duration(remaining)}.",
            )
        if current < self.entry_cutoff:
            return MarketSessionStatus(
                MarketPhase.ENTRY_WINDOW,
                self._seconds_until(now, self.entry_cutoff),
                60,
                True,
                "PAPER entry window is active.",
            )
        if current < self.market_close:
            remaining = self._seconds_until(now, self.market_close)
            return MarketSessionStatus(
                MarketPhase.ENTRY_CLOSED, remaining, 60, False,
                "New entries are closed after 15:10 IST. Existing-position risk and exits remain active; "
                f"market close is in {self._duration(remaining)}.",
            )
        return MarketSessionStatus(
            MarketPhase.MARKET_CLOSED, 0, 600, False,
            "Market session is closed. New entries remain disabled.",
        )
