import pytest
from datetime import datetime
from core.models import Trade, ScoredCandidate
from core.enums import MarketRegime, TradePhase, TradeDirection
from config.settings import TradingConfig
from strategy.rotation_engine import RotationEngine
from data.market_cache import MarketCache, market_cache

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
        projected_net_profit=700.20,
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


def test_rotation_uses_banknifty_cache_lot_size_and_net_economics():
    config = TradingConfig(minimum_projected_net_profit=100.0)
    bank_cache = MarketCache(strike_step=100)
    bank_cache.update_option(58_000, "CE", {"open": 100.0, "last": 110.0})
    bank_cache.update_option(58_000, "PE", {"open": 100.0, "last": 110.0})
    market_cache.clear()
    trade = Trade(
        index_symbol="BANKNIFTY",
        strike_ce=58_000,
        strike_pe=58_000,
        entry_ce_price=100.0,
        entry_pe_price=100.0,
        ce_current_price=110.0,
        pe_current_price=110.0,
        quantity=2,
        lot_size=30,
    )
    candidate = ScoredCandidate(
        ce_strike=57_900,
        pe_strike=58_100,
        ce_velocity=8.0,
        pe_velocity=-2.0,
        divergence=10.0,
        winning_leg="CE",
        projected_net_profit=2_000.0,
        confidence=90.0,
    )

    should_rotate, reason = RotationEngine().should_rotate(
        trade,
        candidate,
        datetime(2026, 7, 17, 10, 0),
        MarketRegime.DIRECTIONAL,
        config,
        cache=bank_cache,
        lot_size=30,
    )

    assert should_rotate is True, reason


def test_rotation_rejects_gross_profit_that_is_not_net_positive_after_costs():
    config = TradingConfig(minimum_projected_net_profit=100.0)
    cache = MarketCache(strike_step=100)
    cache.update_option(58_000, "CE", {"open": 100.0, "last": 101.5})
    cache.update_option(58_000, "PE", {"open": 100.0, "last": 101.5})
    trade = Trade(
        index_symbol="BANKNIFTY",
        strike_ce=58_000,
        strike_pe=58_000,
        entry_ce_price=100.0,
        entry_pe_price=100.0,
        ce_current_price=101.5,
        pe_current_price=101.5,
        quantity=1,
        lot_size=30,
    )
    candidate = ScoredCandidate(
        ce_strike=57_900,
        pe_strike=58_100,
        ce_velocity=6.0,
        pe_velocity=-1.0,
        divergence=7.0,
        winning_leg="CE",
        projected_net_profit=1_000.0,
        confidence=90.0,
    )

    should_rotate, reason = RotationEngine().should_rotate(
        trade,
        candidate,
        datetime(2026, 7, 17, 10, 0),
        MarketRegime.DIRECTIONAL,
        config,
        cache=cache,
        lot_size=30,
    )

    assert should_rotate is False
    assert "net" in reason.lower()
