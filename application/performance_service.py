from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import Enum
from typing import Iterable, Optional
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")


class PerformancePeriod(str, Enum):
    TODAY = "today"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"
    ALL_TIME = "all_time"


@dataclass(frozen=True)
class PerformanceSnapshot:
    period: PerformancePeriod
    mode: str
    realized_pnl: float
    active_pnl: float
    total_pnl: float
    daily_risk_pnl: float
    period_start: Optional[datetime]
    period_end: datetime


class PerformanceService:
    """Calculates trading P&L using explicit mode and IST date boundaries."""

    @staticmethod
    def _as_ist(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=IST)
        return value.astimezone(IST)

    @staticmethod
    def _start(period: PerformancePeriod, now: datetime) -> Optional[datetime]:
        day_start = datetime.combine(now.date(), time.min, tzinfo=IST)
        if period is PerformancePeriod.TODAY:
            return day_start
        if period is PerformancePeriod.WEEK:
            return day_start - timedelta(days=now.weekday())
        if period is PerformancePeriod.MONTH:
            return day_start.replace(day=1)
        if period is PerformancePeriod.YEAR:
            return day_start.replace(month=1, day=1)
        return None

    @classmethod
    def _realized(
        cls,
        trades: Iterable[object],
        mode: str,
        start: Optional[datetime],
        end: datetime,
    ) -> float:
        normalized_mode = str(mode).upper()
        total = 0.0
        for trade in trades:
            if str(getattr(trade, "execution_mode", "UNKNOWN")).upper() != normalized_mode:
                continue
            exit_time = getattr(trade, "exit_time", None)
            if exit_time is None:
                continue
            closed_at = cls._as_ist(exit_time)
            if closed_at > end or (start is not None and closed_at < start):
                continue
            total += float(getattr(trade, "net_pnl", 0.0))
        return round(total, 2)

    @classmethod
    def calculate(
        cls,
        trades: Iterable[object],
        mode: str,
        period: PerformancePeriod,
        now: datetime,
        active_pnl: float,
    ) -> PerformanceSnapshot:
        current = cls._as_ist(now)
        materialized = tuple(trades)
        start = cls._start(period, current)
        realized = cls._realized(materialized, mode, start, current)
        today_start = cls._start(PerformancePeriod.TODAY, current)
        today_realized = cls._realized(materialized, mode, today_start, current)
        active = round(float(active_pnl), 2)
        return PerformanceSnapshot(
            period=period,
            mode=str(mode).upper(),
            realized_pnl=realized,
            active_pnl=active,
            total_pnl=round(realized + active, 2),
            daily_risk_pnl=round(today_realized + active, 2),
            period_start=start,
            period_end=current,
        )
