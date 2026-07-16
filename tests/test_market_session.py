from datetime import datetime

from application.market_session import MarketPhase, MarketSessionSchedule


def at(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 7, 16, hour, minute, second)


def test_premarket_phases_and_countdowns_are_explicit():
    schedule = MarketSessionSchedule()

    idle = schedule.at(at(8, 28))
    startup = schedule.at(at(9, 5))
    warmup = schedule.at(at(9, 15))
    trading = schedule.at(at(9, 30))

    assert idle.phase is MarketPhase.PREMARKET_IDLE
    assert idle.seconds_to_next_phase == 37 * 60
    assert idle.status_interval_seconds == 600
    assert startup.phase is MarketPhase.STARTUP_COUNTDOWN
    assert startup.seconds_to_next_phase == 10 * 60
    assert warmup.phase is MarketPhase.OBSERVATION_WARMUP
    assert warmup.seconds_to_next_phase == 15 * 60
    assert trading.phase is MarketPhase.ENTRY_WINDOW
    assert trading.entries_allowed is True


def test_session_schedule_never_allows_entries_after_cutoff():
    schedule = MarketSessionSchedule()

    assert schedule.at(at(15, 9, 59)).entries_allowed is True
    assert schedule.at(at(15, 10)).phase is MarketPhase.ENTRY_CLOSED
    assert schedule.at(at(15, 20)).phase is MarketPhase.MARKET_CLOSED


def test_premarket_message_reports_next_transition_without_claiming_feed_failure():
    status = MarketSessionSchedule().at(at(8, 28))

    assert status.message == (
        "Premarket idle. Startup countdown begins at 09:05 IST in 37m 00s; "
        "market observation begins at 09:15 and PAPER entries at 09:30."
    )
