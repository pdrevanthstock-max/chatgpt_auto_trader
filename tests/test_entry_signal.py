"""
Tests: Entry Signal Filter
───────────────────────────
Unit tests for the 1–1.5% divergence band entry filter.
"""

import pytest
from datetime import datetime

from core.models import PairedCandle, VelocityResult
from core.enums import TradeDirection
from config.settings import TradingConfig
from strategy.entry_signal import EntryFilter


def _make_velocity(
    ce_vel=1.0, pe_vel=0.0, divergence=None, winning="CE"
) -> VelocityResult:
    """Helper: create a VelocityResult."""
    if divergence is None:
        divergence = abs(ce_vel - pe_vel)
    return VelocityResult(
        timestamp=datetime(2026, 7, 1, 10, 0),
        strike=25000,
        ce_velocity=ce_vel,
        pe_velocity=pe_vel,
        divergence=divergence,
        winning_leg=winning,
    )


def _make_candle(ce_close=101.0, pe_close=99.0) -> PairedCandle:
    return PairedCandle(
        timestamp=datetime(2026, 7, 1, 10, 0),
        strike=25000,
        ce_open=100, ce_high=102, ce_low=99, ce_close=ce_close, ce_volume=1000,
        pe_open=100, pe_high=101, pe_low=98, pe_close=pe_close, pe_volume=1000,
    )


class TestEntryFilter:

    def test_signal_within_band(self):
        """1.2% divergence should generate a signal."""
        velocity = _make_velocity(ce_vel=1.2, pe_vel=0.0)
        candle = _make_candle()
        config = TradingConfig()

        signal = EntryFilter.evaluate(velocity, candle, config)
        assert signal is not None
        assert signal.direction == TradeDirection.LONG_CE
        assert signal.divergence == pytest.approx(1.2, abs=0.01)

    def test_below_min_band(self):
        """0.5% divergence should be rejected (below min)."""
        velocity = _make_velocity(ce_vel=0.5, pe_vel=0.0, divergence=0.5)
        candle = _make_candle()
        config = TradingConfig()

        signal = EntryFilter.evaluate(velocity, candle, config)
        assert signal is None

    def test_above_max_band(self):
        """2.0% divergence should be rejected (above max, don't chase)."""
        velocity = _make_velocity(ce_vel=2.0, pe_vel=0.0, divergence=2.0)
        candle = _make_candle()
        config = TradingConfig()

        signal = EntryFilter.evaluate(velocity, candle, config)
        assert signal is None

    def test_exact_min_boundary(self):
        """Exactly 1.0% should qualify."""
        velocity = _make_velocity(divergence=1.0, ce_vel=1.0, pe_vel=0.0)
        candle = _make_candle()
        config = TradingConfig()

        signal = EntryFilter.evaluate(velocity, candle, config)
        assert signal is not None

    def test_exact_max_boundary(self):
        """Exactly 1.5% should qualify."""
        velocity = _make_velocity(divergence=1.5, ce_vel=1.5, pe_vel=0.0)
        candle = _make_candle()
        config = TradingConfig()

        signal = EntryFilter.evaluate(velocity, candle, config)
        assert signal is not None

    def test_pe_winning_gives_bearish(self):
        """PE winning → LONG_PE direction."""
        velocity = _make_velocity(ce_vel=0.0, pe_vel=1.3, divergence=1.3, winning="PE")
        candle = _make_candle()
        config = TradingConfig()

        signal = EntryFilter.evaluate(velocity, candle, config)
        assert signal is not None
        assert signal.direction == TradeDirection.LONG_PE

    def test_no_winning_leg_rejected(self):
        """NONE winning leg → no signal."""
        velocity = _make_velocity(divergence=1.2, winning="NONE")
        candle = _make_candle()
        config = TradingConfig()

        signal = EntryFilter.evaluate(velocity, candle, config)
        assert signal is None

    def test_custom_band_config(self):
        """Custom band (0.5–2.0) should accept 1.8%."""
        velocity = _make_velocity(divergence=1.8, ce_vel=1.8, pe_vel=0.0)
        candle = _make_candle()
        config = TradingConfig(divergence_min_pct=0.5, divergence_max_pct=2.0)

        signal = EntryFilter.evaluate(velocity, candle, config)
        assert signal is not None
