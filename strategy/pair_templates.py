from __future__ import annotations

from typing import Iterable


class PairTemplateGenerator:
    """Produces bounded executable strike layouts instead of a CE×PE matrix."""

    @staticmethod
    def matched_atm(strikes: Iterable[int | float | str], spot: float) -> list[tuple[object, object]]:
        unique = list(dict.fromkeys(strikes))
        if "ATM" in unique:
            return [("ATM", "ATM")]
        numeric = [value for value in unique if isinstance(value, (int, float))]
        if not numeric or spot <= 0.0:
            return []
        nearest = min(numeric, key=lambda strike: (abs(float(strike) - spot), float(strike)))
        return [(nearest, nearest)]

    @staticmethod
    def atm_itm_cross(
        *,
        ce_strikes: Iterable[int | float],
        pe_strikes: Iterable[int | float],
        spot: float,
        strike_step: int,
        depth: int = 4,
        include_atm: bool = True,
    ) -> list[tuple[int, int]]:
        if spot <= 0.0 or strike_step <= 0 or depth < 0:
            return []
        atm = int(round(float(spot) / strike_step) * strike_step)
        start = 0 if include_atm else 1
        ce_available = {int(value) for value in ce_strikes}
        pe_available = {int(value) for value in pe_strikes}
        ce_layout = [
            atm - offset * strike_step
            for offset in range(start, depth + 1)
            if atm - offset * strike_step in ce_available
        ]
        pe_layout = [
            atm + offset * strike_step
            for offset in range(start, depth + 1)
            if atm + offset * strike_step in pe_available
        ]
        return [(ce, pe) for ce in ce_layout for pe in pe_layout]

    @staticmethod
    def otm_research_cross(
        *,
        ce_strikes: Iterable[int | float],
        pe_strikes: Iterable[int | float],
        spot: float,
        strike_step: int,
    ) -> list[tuple[int, int]]:
        if spot <= 0.0 or strike_step <= 0:
            return []
        atm = int(round(float(spot) / strike_step) * strike_step)
        ce_available = {int(value) for value in ce_strikes}
        pe_available = {int(value) for value in pe_strikes}
        ce_layout = [
            strike for strike in (atm + strike_step, atm + 2 * strike_step)
            if strike in ce_available
        ]
        pe_layout = [
            strike for strike in (atm - strike_step, atm - 2 * strike_step)
            if strike in pe_available
        ]
        return [(ce, pe) for ce in ce_layout for pe in pe_layout]

    @classmethod
    def bounded_universe(
        cls,
        *,
        ce_strikes: Iterable[int | float],
        pe_strikes: Iterable[int | float],
        spot: float,
        strike_step: int,
        depth: int = 4,
        include_atm: bool = True,
        include_otm_research: bool = False,
    ) -> list[tuple[int, int]]:
        ce_values = list(ce_strikes)
        pe_values = list(pe_strikes)
        established = cls.atm_itm_cross(
            ce_strikes=ce_values,
            pe_strikes=pe_values,
            spot=spot,
            strike_step=strike_step,
            depth=depth,
            include_atm=include_atm,
        )
        if not include_otm_research:
            return established
        return established + cls.otm_research_cross(
            ce_strikes=ce_values,
            pe_strikes=pe_values,
            spot=spot,
            strike_step=strike_step,
        )
