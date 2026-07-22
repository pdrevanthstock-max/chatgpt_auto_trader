from datetime import datetime

import pandas as pd

from core.index_registry import IndexRegistry
from data.live_feed import LiveFeed
from data.market_cache import MarketCacheRegistry


def _instrument_rows() -> pd.DataFrame:
    rows = []
    for symbol, lot, step, spot in (
        ("NIFTY", 65, 50, 24_150),
        ("BANKNIFTY", 30, 100, 58_000),
        ("FINNIFTY", 60, 100, 26_900),
        ("MIDCPNIFTY", 120, 25, 14_825),
        ("NIFTYNXT50", 25, 100, 72_500),
    ):
        for strike in range(spot - 4 * step, spot + 4 * step + step, step):
            for option_type in ("CE", "PE"):
                rows.append({
                    "SEM_EXM_EXCH_ID": "NSE",
                    "SEM_SEGMENT": "D",
                    "SEM_SMST_SECURITY_ID": len(rows) + 10_000,
                    "SEM_TRADING_SYMBOL": f"{symbol}-Jul2026-{strike}-{option_type}",
                    "SEM_LOT_UNITS": lot,
                    "SEM_EXPIRY_DATE": "2026-07-28 14:30:00",
                    "SEM_STRIKE_PRICE": strike,
                    "SEM_OPTION_TYPE": option_type,
                })
    return pd.DataFrame(rows)


def test_feed_maps_all_five_indices_and_builds_one_bounded_quote_request(
    tmp_path, monkeypatch
):
    path = tmp_path / "instruments.csv"
    _instrument_rows().to_csv(path, index=False)
    monkeypatch.setattr("data.live_feed.DHAN_CLIENT_ID", "paper-client")
    monkeypatch.setattr("data.live_feed.DHAN_ACCESS_TOKEN", "paper-token")
    monkeypatch.setattr("data.live_feed.DhanContext", lambda **_: object())
    monkeypatch.setattr("data.live_feed.dhanhq", lambda _: object())
    registry = IndexRegistry.default()
    caches = MarketCacheRegistry.default()
    now = datetime.now()
    for symbol, spot in (
        ("NIFTY", 24_150),
        ("BANKNIFTY", 58_000),
        ("FINNIFTY", 26_900),
        ("MIDCPNIFTY", 14_825),
        ("NIFTYNXT50", 72_500),
    ):
        caches.get(symbol).update_spot(float(spot), now)

    feed = LiveFeed(
        index_registry=registry,
        cache_registry=caches,
        instrument_path=path,
    )

    assert feed._initialize_mapping() is True
    request = feed._build_quote_request()

    assert request["IDX_I"] == [13, 25, 27, 38, 442]
    assert len(request["NSE_FNO"]) == 70
    for symbol in registry.symbols:
        spec = registry.get(symbol)
        cache_spot, _ = caches.get(symbol).get_spot()
        atm = int(round(cache_spot / spec.strike_step) * spec.strike_step)
        mapping = feed.strike_maps[symbol]
        assert mapping[(float(atm + spec.strike_step), "CE")] in request["NSE_FNO"]
        assert mapping[(float(atm + 2 * spec.strike_step), "CE")] in request["NSE_FNO"]
        assert mapping[(float(atm - spec.strike_step), "PE")] in request["NSE_FNO"]
        assert mapping[(float(atm - 2 * spec.strike_step), "PE")] in request["NSE_FNO"]
    assert set(feed.active_expiries) == registry.symbols
    assert all(len(feed.strike_maps[symbol]) == 18 for symbol in registry.symbols)
