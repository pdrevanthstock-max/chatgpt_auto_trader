from datetime import datetime

from data.market_cache import MarketCacheRegistry


def test_index_caches_are_isolated_and_use_index_specific_strike_steps():
    caches = MarketCacheRegistry.default()
    now = datetime.now()

    caches.get("NIFTY").update_spot(24_126.0, now)
    caches.get("BANKNIFTY").update_spot(57_951.0, now)
    caches.get("FINNIFTY").update_spot(26_851.0, now)
    caches.get("NIFTY").update_option(24_150, "CE", {"last": 100.0})

    assert caches.get("NIFTY").get_atm_strike() == 24_150
    assert caches.get("BANKNIFTY").get_atm_strike() == 58_000
    assert caches.get("FINNIFTY").get_atm_strike() == 26_900
    assert caches.get("BANKNIFTY").get_option_chain() == {}
    assert caches.get("NIFTY").get_option_chain() != {}


def test_clearing_one_index_does_not_clear_another_index():
    caches = MarketCacheRegistry.default()
    now = datetime.now()
    caches.get("NIFTY").update_spot(24_100.0, now)
    caches.get("BANKNIFTY").update_spot(58_000.0, now)

    caches.get("NIFTY").clear()

    assert caches.get("NIFTY").get_spot()[0] == 0.0
    assert caches.get("BANKNIFTY").get_spot()[0] == 58_000.0
