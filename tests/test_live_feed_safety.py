from data.live_feed import LiveFeed
from data.market_cache import market_cache
from data.market_response import RetryPolicy
from pathlib import Path


def test_live_feed_reports_through_injected_engine_without_streamlit_context():
    class FakeEngine:
        active_trade = None

        def __init__(self):
            self.messages = []

        def log_activity(self, message):
            self.messages.append(message)

    engine = FakeEngine()
    feed = LiveFeed(engine=engine)

    feed.log_to_engine("connected")

    assert engine.messages == ["LiveFeed: connected"]


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


def test_quote_fetch_retries_empty_response_and_fails_closed():
    class EmptyClient:
        def quote_data(self, _request):
            return ""

    class FakeEngine:
        def __init__(self):
            self.messages = []

        def log_activity(self, message):
            self.messages.append(message)

    engine = FakeEngine()
    feed = LiveFeed(engine=engine)
    feed.client = EmptyClient()
    feed.quote_retry_policy = RetryPolicy(max_attempts=2, base_delay_seconds=0.0)

    result = feed._fetch_quotes([1, 2], correlation_id="scan-empty")

    assert result is None
    assert feed.fallback_engaged is True
    assert any("EMPTY_RESPONSE" in message for message in engine.messages)


def test_successful_quote_fetch_clears_transient_failure_state():
    class SuccessClient:
        def quote_data(self, _request):
            return {"status": "success", "data": {"data": {"NSE_FNO": {}}}}

    feed = LiveFeed()
    feed.client = SuccessClient()
    feed.fallback_engaged = True
    feed.quote_retry_policy = RetryPolicy(max_attempts=1, base_delay_seconds=0.0)

    result = feed._fetch_quotes([1], correlation_id="scan-ok")

    assert result["status"] == "success"
    assert feed.fallback_engaged is False


def test_live_feed_source_builds_completed_option_and_spot_candles():
    source = Path("data/live_feed.py").read_text(encoding="utf-8")
    assert "completed_candles.add_tick" in source
    assert "option_candle_key" in source
    assert "spot_candle_key(symbol)" in source
    assert 'segments.get("IDX_I"' in source
