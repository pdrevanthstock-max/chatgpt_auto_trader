from datetime import datetime, timedelta

import pytest

from data.candle_store import CompletedCandleStore


def test_only_completed_buckets_are_exposed_and_latest_pair_is_close_to_close():
    store = CompletedCandleStore(interval_seconds=60)
    start = datetime(2026, 7, 15, 10, 0, 5)

    store.add_tick("NIFTY:24200:CE", start, 100.0, volume=10, oi=100)
    store.add_tick("NIFTY:24200:CE", start + timedelta(seconds=30), 102.0, volume=15, oi=110)
    assert store.latest_pair("NIFTY:24200:CE") is None

    store.add_tick("NIFTY:24200:CE", start + timedelta(seconds=60), 104.0, volume=20, oi=120)
    store.add_tick("NIFTY:24200:CE", start + timedelta(seconds=120), 106.0, volume=25, oi=130)

    previous, latest = store.latest_pair("NIFTY:24200:CE")
    assert previous.open == 100.0
    assert previous.close == 102.0
    assert latest.open == 104.0
    assert latest.close == 104.0


def test_out_of_order_ticks_are_rejected_without_corrupting_completed_history():
    store = CompletedCandleStore(interval_seconds=60)
    start = datetime(2026, 7, 15, 10, 0)
    store.add_tick("spot", start, 24_200.0)
    store.add_tick("spot", start + timedelta(minutes=1), 24_210.0)

    with pytest.raises(ValueError, match="out-of-order"):
        store.add_tick("spot", start + timedelta(seconds=20), 24_190.0)

    assert store.latest("spot", count=1)[0].close == 24_200.0
