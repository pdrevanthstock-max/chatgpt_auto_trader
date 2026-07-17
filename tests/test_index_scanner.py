from datetime import date, datetime, timedelta

from application.index_scanner import IndexScanner
from config.settings import TradingConfig
from core.enums import MarketRegime
from core.index_registry import IndexRegistry
from core.models import Trade
from data.market_cache import MarketCacheRegistry


def _populate_directional_chain(cache, *, spot: int, step: int) -> None:
    now = datetime.now()
    cache.update_spot(float(spot), now)
    cache.set_active_expiry(date.today() + timedelta(days=5))
    atm = int(round(spot / step) * step)
    for offset in range(-4, 5):
        strike = atm + offset * step
        cache.update_option(strike, "CE", {
            "bid": 104.5,
            "ask": 105.0,
            "last": 105.0,
            "open": 100.0,
            "volume": 1,
            "oi": 1,
            "timestamp": now,
        })
        cache.update_option(strike, "PE", {
            "bid": 100.5,
            "ask": 101.0,
            "last": 101.0,
            "open": 100.0,
            "volume": 1,
            "oi": 1,
            "timestamp": now,
        })
    cache.update_health(10)


def test_index_scanner_uses_isolated_cache_and_index_lot_size():
    registry = IndexRegistry.default()
    caches = MarketCacheRegistry.default()
    spec = registry.get("BANKNIFTY")
    cache = caches.get("BANKNIFTY")
    _populate_directional_chain(cache, spot=58_020, step=spec.strike_step)
    scanner = IndexScanner(
        spec=spec,
        cache=cache,
        config=TradingConfig(
            execution_mode="PAPER",
            total_capital=450_000.0,
            minimum_projected_net_profit=0.0,
            minimum_projected_return_pct=0.0,
        ),
        require_completed=False,
    )

    result = scanner.scan(
        regime=MarketRegime.DIRECTIONAL,
        spot_trend="UP",
        realized_pnl=0.0,
        active_trade=None,
        available_capital=450_000.0,
        trading_day=date.today(),
    )

    assert result.index_symbol == "BANKNIFTY"
    assert result.candidate is not None
    assert result.candidate.plan.index_symbol == "BANKNIFTY"
    assert result.candidate.plan.lot_size == 30
    assert result.candidate.projected_net > 0.0
    # The established 25 ATM/ITM templates remain intact and PAPER
    # directional research adds exactly four bounded OTM templates.
    assert len(result.diagnostics) == 29


def test_observe_only_scanner_can_report_opportunity_without_changing_permission():
    registry = IndexRegistry.default()
    caches = MarketCacheRegistry.default()
    spec = registry.get("MIDCPNIFTY")
    cache = caches.get("MIDCPNIFTY")
    _populate_directional_chain(cache, spot=14_825, step=spec.strike_step)
    scanner = IndexScanner(
        spec=spec,
        cache=cache,
        config=TradingConfig(
            execution_mode="PAPER",
            total_capital=450_000.0,
            minimum_projected_net_profit=0.0,
            minimum_projected_return_pct=0.0,
        ),
        require_completed=False,
    )

    result = scanner.scan(
        regime=MarketRegime.DIRECTIONAL,
        spot_trend="UP",
        realized_pnl=0.0,
        active_trade=None,
        available_capital=450_000.0,
        trading_day=date.today(),
    )

    assert result.candidate is not None
    assert spec.permission.value == "OBSERVE_ONLY"


def test_index_scanner_ranking_uses_the_same_available_equity_as_final_sizing():
    registry = IndexRegistry.default()
    caches = MarketCacheRegistry.default()
    spec = registry.get("BANKNIFTY")
    cache = caches.get("BANKNIFTY")
    _populate_directional_chain(cache, spot=58_020, step=spec.strike_step)
    scanner = IndexScanner(
        spec=spec,
        cache=cache,
        config=TradingConfig(
            execution_mode="PAPER",
            total_capital=450_000.0,
            minimum_projected_net_profit=0.0,
            minimum_projected_return_pct=0.0,
        ),
        require_completed=False,
    )

    result = scanner.scan(
        regime=MarketRegime.DIRECTIONAL,
        spot_trend="UP",
        realized_pnl=0.0,
        active_trade=None,
        available_capital=45_000.0,
        trading_day=date.today(),
    )

    assert result.candidate is not None
    pair = (
        result.candidate.scored_candidate.ce_strike,
        result.candidate.scored_candidate.pe_strike,
    )
    assert scanner.ranker.last_decisions[pair]["lots"] == result.candidate.plan.quantity


def test_index_scanner_diagnostics_publish_dynamic_strike_universes():
    registry = IndexRegistry.default()
    caches = MarketCacheRegistry.default()
    spec = registry.get("NIFTY")
    cache = caches.get("NIFTY")
    _populate_directional_chain(cache, spot=24_175, step=spec.strike_step)
    scanner = IndexScanner(
        spec=spec,
        cache=cache,
        config=TradingConfig(
            execution_mode="PAPER",
            total_capital=450_000.0,
            minimum_projected_net_profit=0.0,
            minimum_projected_return_pct=0.0,
        ),
        require_completed=False,
    )

    result = scanner.scan(
        regime=MarketRegime.DIRECTIONAL,
        spot_trend="UP",
        realized_pnl=0.0,
        active_trade=None,
        available_capital=450_000.0,
        trading_day=date.today(),
    )

    row = result.diagnostics[0]
    assert row["ce_universe"] == [
        {"strike": 24200, "moneyness": "ATM"},
        {"strike": 24150, "moneyness": "ITM1"},
        {"strike": 24100, "moneyness": "ITM2"},
        {"strike": 24050, "moneyness": "ITM3"},
        {"strike": 24000, "moneyness": "ITM4"},
    ]
    assert row["pe_universe"] == [
        {"strike": 24200, "moneyness": "ATM"},
        {"strike": 24250, "moneyness": "ITM1"},
        {"strike": 24300, "moneyness": "ITM2"},
        {"strike": 24350, "moneyness": "ITM3"},
        {"strike": 24400, "moneyness": "ITM4"},
    ]
    assert row["research_ce_universe"] == [
        {"strike": 24250, "moneyness": "OTM1"},
        {"strike": 24300, "moneyness": "OTM2"},
    ]
    assert row["research_pe_universe"] == [
        {"strike": 24150, "moneyness": "OTM1"},
        {"strike": 24100, "moneyness": "OTM2"},
    ]


def test_final_validation_failure_keeps_dynamic_universe_metadata():
    registry = IndexRegistry.default()
    caches = MarketCacheRegistry.default()
    spec = registry.get("NIFTY")
    cache = caches.get("NIFTY")
    _populate_directional_chain(cache, spot=24_175, step=spec.strike_step)
    scanner = IndexScanner(
        spec=spec,
        cache=cache,
        config=TradingConfig(
            execution_mode="PAPER",
            total_capital=450_000.0,
            minimum_projected_net_profit=0.0,
            minimum_projected_return_pct=0.0,
        ),
        require_completed=False,
    )

    result = scanner.scan(
        regime=MarketRegime.DIRECTIONAL,
        spot_trend="UP",
        realized_pnl=0.0,
        active_trade=Trade(execution_mode="PAPER"),
        available_capital=450_000.0,
        trading_day=date.today(),
    )

    assert result.candidate is None
    assert result.diagnostics[0]["reason"] == "FINAL_VALIDATION_FAILED"
    assert result.diagnostics[0]["ce_universe"][0] == {
        "strike": 24200,
        "moneyness": "ATM",
    }
