"""
Tests: Divergence Scanner
──────────────────────────
Unit tests for the core velocity divergence calculation.
"""

import pytest
from datetime import datetime

from core.models import PairedCandle
from strategy.divergence_scanner import DivergenceScanner


def _make_candle(
    ce_open=100.0, ce_close=101.0,
    pe_open=100.0, pe_close=99.0,
    strike=25000,
) -> PairedCandle:
    """Helper: create a PairedCandle with sensible defaults."""
    return PairedCandle(
        timestamp=datetime(2026, 7, 1, 10, 0),
        strike=strike,
        ce_open=ce_open, ce_high=max(ce_open, ce_close),
        ce_low=min(ce_open, ce_close), ce_close=ce_close,
        ce_volume=1000,
        pe_open=pe_open, pe_high=max(pe_open, pe_close),
        pe_low=min(pe_open, pe_close), pe_close=pe_close,
        pe_volume=1000,
    )


class TestDivergenceScanner:
    """Tests for DivergenceScanner.compute_velocity."""

    def test_basic_velocity_calculation(self):
        """CE +1%, PE -1% → divergence = 2%."""
        candle = _make_candle(ce_open=100, ce_close=101, pe_open=100, pe_close=99)
        result = DivergenceScanner.compute_velocity(candle)

        assert result.ce_velocity == pytest.approx(1.0, abs=0.01)
        assert result.pe_velocity == pytest.approx(-1.0, abs=0.01)
        assert result.divergence == pytest.approx(2.0, abs=0.01)

    def test_zero_divergence(self):
        """Both legs move identically → divergence = 0."""
        candle = _make_candle(ce_open=100, ce_close=101, pe_open=100, pe_close=101)
        result = DivergenceScanner.compute_velocity(candle)

        assert result.divergence == pytest.approx(0.0, abs=0.01)

    def test_winning_leg_ce(self):
        """CE moves more → CE is winning leg."""
        candle = _make_candle(ce_open=100, ce_close=103, pe_open=100, pe_close=100.5)
        result = DivergenceScanner.compute_velocity(candle)

        assert result.winning_leg == "CE"

    def test_winning_leg_pe(self):
        """PE moves more → PE is winning leg."""
        candle = _make_candle(ce_open=100, ce_close=100.2, pe_open=100, pe_close=104)
        result = DivergenceScanner.compute_velocity(candle)

        assert result.winning_leg == "PE"

    def test_zero_price_guard(self):
        """Zero open price should not crash (division by zero guard)."""
        candle = _make_candle(ce_open=0, ce_close=100, pe_open=100, pe_close=99)
        result = DivergenceScanner.compute_velocity(candle)

        assert result.ce_velocity == 0.0
        assert result.divergence == 0.0
        assert result.winning_leg == "NONE"

    def test_both_legs_falling(self):
        """Both legs falling but at different rates."""
        candle = _make_candle(ce_open=200, ce_close=196, pe_open=200, pe_close=190)
        result = DivergenceScanner.compute_velocity(candle)

        # CE: -2%, PE: -5% → divergence = 3%
        assert result.ce_velocity == pytest.approx(-2.0, abs=0.01)
        assert result.pe_velocity == pytest.approx(-5.0, abs=0.01)
        assert result.divergence == pytest.approx(3.0, abs=0.01)

    def test_small_divergence_in_band(self):
        """Divergence exactly within 1-1.5% band."""
        # CE: +1.2%, PE: 0% → divergence = 1.2%
        candle = _make_candle(ce_open=100, ce_close=101.2, pe_open=100, pe_close=100)
        result = DivergenceScanner.compute_velocity(candle)

        assert 1.0 <= result.divergence <= 1.5

    def test_scan_candles_returns_list(self):
        """scan_candles should return a VelocityResult per candle."""
        candles = [
            _make_candle(ce_close=101),
            _make_candle(ce_close=102),
            _make_candle(ce_close=103),
        ]
        results = DivergenceScanner.scan_candles(candles)
        assert len(results) == 3
