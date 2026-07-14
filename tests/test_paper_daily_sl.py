import importlib
from datetime import datetime

from config.settings import TradingConfig
from core.enums import MarketRegime, OrderType, TradeDirection, TradePhase
from core.models import ScoredCandidate, Trade, TradePlan
from data.market_cache import market_cache
from database.trade_store import TradeStore
from execution.execution_validator import ExecutionValidator
from execution.paper_executor import PaperExecutor


def _plan(**overrides) -> TradePlan:
    values = {
        "scored_candidate": ScoredCandidate(
            ce_strike=24300,
            pe_strike=24300,
            ce_velocity=2.0,
            pe_velocity=1.0,
            divergence=1.0,
            winning_leg="CE",
            projected_net_profit=500.0,
            confidence=80.0,
        ),
        "regime": MarketRegime.DIRECTIONAL,
        "order_type": OrderType.MARKET,
        "quantity": 1,
        "lot_size": 65,
    }
    values.update(overrides)
    return TradePlan(**values)


def _populate_quotes() -> None:
    now = datetime.now()
    market_cache.clear()
    for option_type in ("CE", "PE"):
        market_cache.update_option(
            24300,
            option_type,
            {
                "bid": 100.0,
                "ask": 101.0,
                "last": 100.5,
                "open": 100.0,
                "volume": 1000,
                "oi": 2000,
                "timestamp": now,
            },
        )


def test_paper_entry_validation_continues_after_daily_loss_limit():
    _populate_quotes()

    valid, reason = ExecutionValidator().validate_entry(
        _plan(),
        realized_pnl=-2_000.0,
        active_trade=None,
        config=TradingConfig(execution_mode="PAPER", total_capital=45_000.0),
    )

    assert valid is True
    assert reason == "Validation successful"


def test_live_entry_validation_still_blocks_after_daily_loss_limit():
    _populate_quotes()

    valid, reason = ExecutionValidator().validate_entry(
        _plan(),
        realized_pnl=-2_000.0,
        active_trade=None,
        config=TradingConfig(execution_mode="LIVE", total_capital=45_000.0),
    )

    assert valid is False
    assert "Daily circuit breaker breached" in reason


def test_paper_executor_propagates_post_daily_sl_tag():
    _populate_quotes()

    trade = PaperExecutor().execute_entry(
        _plan(post_daily_sl=True),
        datetime.now(),
    )

    assert trade.post_daily_sl is True
    assert trade.display_id.endswith("-SL")


def test_sl_tag_round_trips_through_trade_store(tmp_path):
    trade = Trade(
        id="postsl01",
        direction=TradeDirection.LONG_CE,
        strike_ce=24300,
        strike_pe=24300,
        entry_ce_price=100.0,
        entry_pe_price=100.0,
        quantity=1,
        lot_size=65,
        entry_time=datetime.now(),
        regime_at_entry=MarketRegime.DIRECTIONAL,
        phase=TradePhase.PHASE_1_BOTH_LEGS,
        post_daily_sl=True,
    )
    store = TradeStore(str(tmp_path / "trades.db"))

    store.save_trade(trade)
    loaded = store.get_all_trades()[0]

    assert loaded.post_daily_sl is True
    assert loaded.display_id == "postsl01-SL"


def test_trade_view_helpers_support_legacy_in_memory_trade_objects():
    trade_view = importlib.import_module("ui.trade_view")

    class LegacyTrade:
        id = "legacy01"
        quantity = 179
        lot_size = 65

    legacy = LegacyTrade()

    assert trade_view.units_per_leg(legacy) == 11_635
    assert trade_view.display_trade_id(legacy) == "legacy01"
    assert trade_view.daily_sl_status(legacy) == "NORMAL"
