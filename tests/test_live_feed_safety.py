from data.live_feed import LiveFeed
from data.market_cache import market_cache


def test_failed_live_feed_never_populates_synthetic_prices(monkeypatch):
    market_cache.clear()
    feed = LiveFeed()
    feed._running = True

    def fail_initialization():
        feed.fallback_engaged = True
        return False

    monkeypatch.setattr(feed, "_initialize_mapping", fail_initialization)
    monkeypatch.setattr(
        "data.live_feed.time.sleep",
        lambda _seconds: setattr(feed, "_running", False),
    )

    feed._run()

    assert feed.fallback_engaged is True
    assert feed._running is False
    assert market_cache.get_spot()[0] == 0.0
    assert market_cache.get_option_chain() == {}
