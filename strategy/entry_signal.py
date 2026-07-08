"""
Entry Signal Filter
────────────────────
§4.4: Enter only when divergence is between 1% and 1.5%.
Below 1%: no signal.
Above 1.5%: too divergent, skip — do not chase.

User's clarification:
  "Filter and identify ONLY the pair(s) where the absolute candle
   price movement difference is between 1% and 1.5%."
"""

from __future__ import annotations

from typing import Optional

from core.models import VelocityResult, PairedCandle, EntrySignal
from core.enums import TradeDirection, MarketSignal
from config.settings import TradingConfig
from strategy.divergence_scanner import DivergenceScanner


class EntryFilter:
    """
    Applies the divergence band filter and generates entry signals.
    """

    @staticmethod
    def evaluate(
        velocity: VelocityResult,
        candle: PairedCandle,
        config: TradingConfig,
    ) -> Optional[EntrySignal]:
        """
        Check if a velocity result qualifies for entry.

        Returns an EntrySignal if the divergence is within the
        configured band, None otherwise.

        §4.4: 1.0% ≤ divergence ≤ 1.5% (configurable via UI)
        """
        # Band filter
        if velocity.divergence < config.divergence_min_pct:
            return None  # Too quiet — no signal

        if velocity.divergence > config.divergence_max_pct:
            return None  # Too divergent — don't chase

        # No signal if legs are perfectly balanced
        if velocity.winning_leg == "NONE":
            return None

        # Determine direction
        signal = DivergenceScanner.determine_signal(velocity)
        if signal == MarketSignal.NO_SIGNAL:
            return None

        # Map market signal to trade direction
        if signal == MarketSignal.BULLISH:
            direction = TradeDirection.LONG_CE
        else:
            direction = TradeDirection.LONG_PE

        return EntrySignal(
            timestamp=velocity.timestamp,
            strike=velocity.strike,
            direction=direction,
            divergence=velocity.divergence,
            ce_velocity=velocity.ce_velocity,
            pe_velocity=velocity.pe_velocity,
            ce_price=candle.ce_close,
            pe_price=candle.pe_close,
        )
