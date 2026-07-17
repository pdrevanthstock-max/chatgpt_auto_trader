from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from core.enums import MarketRegime


@dataclass(frozen=True)
class OtmResearchInputs:
    execution_mode: str
    regime: MarketRegime
    spot_trend: str
    winning_leg: str
    spot_price: float
    ce_strike: int
    pe_strike: int
    strike_step: int
    ce_ask: float
    pe_ask: float
    ce_velocity: float
    pe_velocity: float
    now: datetime
    expiry: date | None
    projected_net: float
    projected_return_pct: float
    quotes_fresh: bool
    candles_synchronized: bool
    capital_passed: bool
    price_integrity_passed: bool
    final_validation_passed: bool


@dataclass(frozen=True)
class OtmResearchDecision:
    allowed: bool
    reason: str
    pair_class: str = "OTM_RESEARCH"


class OtmResearchGuard:
    """Pure policy for the narrow PAPER-only OTM research exception."""

    @staticmethod
    def _decision(allowed: bool, reason: str) -> OtmResearchDecision:
        return OtmResearchDecision(allowed=allowed, reason=reason)

    @staticmethod
    def _ist_now(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value
        return value.astimezone(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)

    @staticmethod
    def template_allowed(
        *,
        enabled: bool,
        execution_mode: str,
        regime: MarketRegime | None,
        now: datetime,
        expiry: date | None,
    ) -> bool:
        local_now = OtmResearchGuard._ist_now(now)
        if not enabled or execution_mode.upper() != "PAPER":
            return False
        if regime != MarketRegime.DIRECTIONAL:
            return False
        return not (expiry == local_now.date() and local_now.time() >= time(12, 0))

    @staticmethod
    def bounded_strikes(
        *, spot_price: float, ce_strike: int, pe_strike: int, strike_step: int
    ) -> bool:
        if spot_price <= 0.0 or strike_step <= 0:
            return False
        atm = int(round(float(spot_price) / strike_step) * strike_step)
        return (
            ce_strike in {atm + strike_step, atm + 2 * strike_step}
            and pe_strike in {atm - strike_step, atm - 2 * strike_step}
        )

    @staticmethod
    def direction_aligned(*, spot_trend: str, winning_leg: str) -> bool:
        return (
            (spot_trend == "UP" and winning_leg == "CE")
            or (spot_trend == "DOWN" and winning_leg == "PE")
        )

    @classmethod
    def evaluate(
        cls,
        value: OtmResearchInputs,
        *,
        minimum_ask: float = 15.0,
        maximum_premium_ratio: float = 2.5,
        minimum_projected_net: float = 100.0,
        minimum_projected_return_pct: float = 0.25,
    ) -> OtmResearchDecision:
        if value.execution_mode.upper() != "PAPER":
            return cls._decision(False, "OTM_RESEARCH_PAPER_ONLY")
        if value.regime != MarketRegime.DIRECTIONAL:
            return cls._decision(False, "OTM_RESEARCH_DIRECTIONAL_ONLY")
        if not cls.direction_aligned(
            spot_trend=value.spot_trend, winning_leg=value.winning_leg
        ):
            return cls._decision(False, "OTM_RESEARCH_DIRECTION_MISMATCH")
        if value.ce_ask < minimum_ask or value.pe_ask < minimum_ask:
            return cls._decision(False, "OTM_RESEARCH_MINIMUM_ASK")
        if not cls.bounded_strikes(
            spot_price=value.spot_price,
            ce_strike=value.ce_strike,
            pe_strike=value.pe_strike,
            strike_step=value.strike_step,
        ):
            return cls._decision(False, "OTM_RESEARCH_DEPTH_EXCEEDED")
        if value.ce_velocity <= 0.0 and value.pe_velocity <= 0.0:
            return cls._decision(False, "DUAL_DECAY")
        premium_ratio = max(value.ce_ask, value.pe_ask) / min(value.ce_ask, value.pe_ask)
        if premium_ratio > maximum_premium_ratio:
            return cls._decision(False, "PREMIUM_RATIO_EXCEEDED")
        local_now = cls._ist_now(value.now)
        if value.expiry == local_now.date() and local_now.time() >= time(12, 0):
            return cls._decision(False, "EXPIRY_OTM_CUTOFF")
        if value.projected_net < minimum_projected_net or (
            value.projected_return_pct < minimum_projected_return_pct
        ):
            return cls._decision(False, "PROJECTED_NET_BUFFER_FAILED")
        if not value.quotes_fresh:
            return cls._decision(False, "STALE_EXECUTABLE_QUOTE")
        if not value.candles_synchronized:
            return cls._decision(False, "ASYNCHRONOUS_COMPLETED_CANDLES")
        if not value.capital_passed:
            return cls._decision(False, "INSUFFICIENT_CAPITAL")
        if not value.price_integrity_passed:
            return cls._decision(False, "PRICE_INTEGRITY_FAILED")
        if not value.final_validation_passed:
            return cls._decision(False, "FINAL_VALIDATION_FAILED")
        return cls._decision(True, "OTM_RESEARCH_APPROVED")
