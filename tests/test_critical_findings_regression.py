from datetime import datetime

import pytest

from config.settings import TradingConfig
from core.enums import ExitReason, MarketRegime, TradeDirection, TradePhase
from core.models import CandidatePair, Trade
from data.market_cache import market_cache
from strategy.entry_signal import EntrySignal
from strategy.exit_manager import ExitManager
from strategy.pair_ranker import PairRanker
from strategy.position_sizer import PositionSizer
from strategy.single_leg_exit_manager import SingleLegExitManager


def test_low_premium_sizing_stays_dynamic_but_respects_temporary_unit_ceiling():
    config = TradingConfig(total_capital=45_000.0, nifty_lot_size=65)

    lots = PositionSizer().calculate_lots(1.40, 1.40, config)

    assert lots > 0
    assert lots * config.nifty_lot_size <= 1_800


def test_entry_gate_rejects_dual_decay_candidate():
    candidate = CandidatePair(
        ce_strike=24_350,
        pe_strike=23_750,
        ce_velocity=-12.5,
        pe_velocity=-9.7,
        divergence=2.8,
        winning_leg="PE",
    )

    survivors = EntrySignal().evaluate_signals(
        [candidate],
        MarketRegime.SIDEWAYS,
        "SIDEWAYS",
        TradingConfig(divergence_band_min=1.0, divergence_band_max=5.0),
    )

    assert survivors == []


def test_strategy_entry_gate_rejects_both_otm_pair_in_all_execution_modes():
    candidate = CandidatePair(
        ce_strike=24_350,
        pe_strike=23_750,
        ce_velocity=2.0,
        pe_velocity=1.0,
        divergence=1.0,
        winning_leg="CE",
    )

    survivors = EntrySignal().evaluate_signals(
        [candidate],
        MarketRegime.DIRECTIONAL,
        "UP",
        TradingConfig(),
        spot_price=24_000.0,
    )

    assert survivors == []


def test_ranker_rejects_candidate_with_non_positive_projected_net_profit():
    now = datetime.now()
    market_cache.clear()
    for option_type in ("CE", "PE"):
        market_cache.update_option(
            24_000,
            option_type,
            {
                "last": 10.0,
                "bid": 9.9,
                "ask": 10.1,
                "volume": 1_000,
                "oi": 5_000,
                "timestamp": now,
            },
        )
    candidate = CandidatePair(
        ce_strike=24_000,
        pe_strike=24_000,
        ce_velocity=0.01,
        pe_velocity=0.0,
        divergence=1.0,
        winning_leg="CE",
    )

    ranked = PairRanker().rank_candidates(
        [candidate],
        TradingConfig(execution_mode="PAPER"),
    )

    assert ranked is None


def test_hard_stop_uses_three_percent_of_remaining_equity_at_entry():
    remaining_equity = 43_650.0
    trade = Trade(
        direction=TradeDirection.LONG_CE,
        strike_ce=24_350,
        strike_pe=23_750,
        entry_ce_price=20.0,
        entry_pe_price=20.0,
        quantity=1,
        lot_size=65,
        entry_time=datetime.now(),
        regime_at_entry=MarketRegime.SIDEWAYS,
        phase=TradePhase.PHASE_1_BOTH_LEGS,
        risk_capital_at_entry=remaining_equity,
        hard_stop_loss=remaining_equity * 0.03,
    )

    reason = ExitManager().check_exits(
        trade,
        ce_price=9.0,
        pe_price=9.0,
        iv_percentile=50.0,
        is_preclose=False,
        config=TradingConfig(per_trade_loss_limit_pct=0.03),
    )

    assert trade.hard_stop_loss == pytest.approx(1_309.50)
    assert reason == ExitReason.HARD_STOP


def test_circuit_breaker_exit_reason_is_constructible():
    assert ExitReason("CIRCUIT_BREAKER_TRIGGERED") is ExitReason.CIRCUIT_BREAKER_TRIGGERED


def test_hard_stop_remains_active_after_hedge_cut():
    trade = Trade(
        direction=TradeDirection.LONG_CE,
        entry_ce_price=20.0,
        entry_pe_price=20.0,
        quantity=1,
        lot_size=65,
        phase=TradePhase.PHASE_2_SINGLE_LEG,
        risk_capital_at_entry=43_650.0,
        hard_stop_loss=1_309.50,
        losing_leg_exit_price=10.0,
        losing_leg_pnl=-650.0,
        exit_pe_price=10.0,
        ce_current_price=9.0,
        pe_current_price=10.0,
    )

    reason = SingleLegExitManager().check_single_leg_exit(
        trade,
        ce_price=9.0,
        pe_price=10.0,
        config=TradingConfig(),
    )

    assert reason is ExitReason.HARD_STOP
