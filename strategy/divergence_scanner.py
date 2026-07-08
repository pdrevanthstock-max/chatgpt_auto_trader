"""
Divergence Scanner
───────────────────
Core signal engine: computes per-candle velocity divergence
between CE and PE legs.

User's specification (refined from §4):
  Velocity_CE = ((Close_CE - Open_CE) / Open_CE) * 100
  Velocity_PE = ((Close_PE - Open_PE) / Open_PE) * 100
  Divergence  = |Velocity_CE - Velocity_PE|

This is the heart of the strategy. Everything else is plumbing.
"""

from __future__ import annotations

from typing import List, Optional

from core.models import PairedCandle, VelocityResult
from core.enums import MarketSignal


class DivergenceScanner:
    """
    Scans paired CE/PE candles and computes velocity divergence.
    Stateless — each call is independent.
    """

    @staticmethod
    def compute_velocity(candle: PairedCandle) -> VelocityResult:
        """
        Compute intra-candle percentage velocity for both legs.

        Velocity = ((Close - Open) / Open) * 100

        This measures how much each leg moved within a single candle,
        NOT cumulative since some anchor point.
        """
        # Guard against division by zero (pre-market or zero-price candles)
        if candle.ce_open <= 0 or candle.pe_open <= 0:
            return VelocityResult(
                timestamp=candle.timestamp,
                strike=candle.strike,
                ce_velocity=0.0,
                pe_velocity=0.0,
                divergence=0.0,
                winning_leg="NONE",
            )

        ce_vel = ((candle.ce_close - candle.ce_open) / candle.ce_open) * 100
        pe_vel = ((candle.pe_close - candle.pe_open) / candle.pe_open) * 100

        divergence = abs(ce_vel - pe_vel)

        # Winning leg = the one with higher absolute velocity
        # For entry direction: positive CE velocity → bullish, positive PE velocity → bearish
        # But we compare absolute movement to find which leg is "winning"
        if abs(ce_vel) > abs(pe_vel):
            winning_leg = "CE"
        elif abs(pe_vel) > abs(ce_vel):
            winning_leg = "PE"
        else:
            winning_leg = "NONE"

        return VelocityResult(
            timestamp=candle.timestamp,
            strike=candle.strike,
            ce_velocity=round(ce_vel, 4),
            pe_velocity=round(pe_vel, 4),
            divergence=round(divergence, 4),
            winning_leg=winning_leg,
        )

    @staticmethod
    def determine_signal(velocity: VelocityResult) -> MarketSignal:
        """
        Determine market direction from velocity result.

        User clarification:
          - CE velocity winning (CE moving up more) → BULLISH → buy CE, hedge PE
          - PE velocity winning (PE moving up more) → BEARISH → buy PE, hedge CE
        """
        if velocity.winning_leg == "CE":
            # CE is performing better → bullish signal
            if velocity.ce_velocity > 0:
                return MarketSignal.BULLISH
            # CE is falling less than PE → still relatively bullish
            return MarketSignal.BULLISH

        if velocity.winning_leg == "PE":
            # PE is performing better → bearish signal
            if velocity.pe_velocity > 0:
                return MarketSignal.BEARISH
            return MarketSignal.BEARISH

        return MarketSignal.NO_SIGNAL

    @classmethod
    def scan_candles(
        cls, candles: List[PairedCandle]
    ) -> List[VelocityResult]:
        """Compute velocity for a sequence of candles."""
        return [cls.compute_velocity(c) for c in candles]
