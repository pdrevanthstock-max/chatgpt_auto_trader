import pytest
from datetime import datetime
from core.models import Trade, ScoredCandidate
from core.enums import MarketRegime, TradePhase, TradeDirection
from config.settings import TradingConfig
from strategy.rotation_engine import RotationEngine
from data.market_cache import market_cache

def test_rotation_engine_cooldown_and_logic():
    config = TradingConfig(
        rotation_min_profit_floor=103.0,
        rotation_cooldown_candles=3,
        candle_interval_minutes=2
    )
    engine = RotationEngine()
    
    # Active trade
    trade = Trade(
        direction=TradeDirection.LONG_CE,
        strike_ce=24300,
        strike_pe=24300,
        entry_ce_price=100.0,
        entry_pe_price=100.0,
        quantity=1,
        lot_size=65,
        entry_time=datetime.now(),
        regime_at_entry=MarketRegime.SIDEWAYS,
        phase=TradePhase.PHASE_1_BOTH_LEGS,
        ce_current_price=105.0,
        pe_current_price=105.0  # PnL = 10 * 65 = 650 (exceeds floor)
    )

    # Scored candidate
    candidate = ScoredCandidate(
        ce_strike=24400, pe_strike=24400,
        ce_velocity=5.0, pe_velocity=-5.0, divergence=10.0,
        winning_leg="CE", projected_net_profit=500.0, confidence=85.0
    )

    # Set mock option values for active trade in cache
    market_cache.clear()
    market_cache.update_option(24300, "CE", {"open": 100.0, "last": 105.0})
    market_cache.update_option(24300, "PE", {"open": 100.0, "last": 105.0})

    now = datetime.now()
    
    # Test 1: Should not rotate if in cooldown
    engine.set_cooldown(24400, 24400, now, config)
    should, reason = engine.should_rotate(trade, candidate, now, MarketRegime.SIDEWAYS, config)
    assert not should
    assert "cooldown" in reason.lower()


def test_rotation_compares_candidates_using_turnover_based_costs():
    config = TradingConfig(rotation_min_profit_floor=103.0)
    trade = Trade(
        direction=TradeDirection.LONG_CE,
        strike_ce=24300,
        strike_pe=24300,
        entry_ce_price=100.0,
        entry_pe_price=100.0,
        quantity=1,
        lot_size=65,
        entry_time=datetime(2026, 7, 14, 9, 45),
        regime_at_entry=MarketRegime.SIDEWAYS,
        phase=TradePhase.PHASE_1_BOTH_LEGS,
        ce_current_price=105.0,
        pe_current_price=105.0,
    )
    candidate = ScoredCandidate(
        ce_strike=24400,
        pe_strike=24400,
        ce_velocity=8.0,
        pe_velocity=-2.0,
        divergence=10.0,
        winning_leg="CE",
        projected_net_profit=550.20,
        confidence=85.0,
    )
    market_cache.clear()
    market_cache.update_option(24300, "CE", {"open": 100.0, "last": 105.0})
    market_cache.update_option(24300, "PE", {"open": 100.0, "last": 105.0})

    should_rotate, _ = RotationEngine().should_rotate(
        trade,
        candidate,
        datetime(2026, 7, 14, 10, 0),
        MarketRegime.SIDEWAYS,
        config,
    )

    assert should_rotate is True
