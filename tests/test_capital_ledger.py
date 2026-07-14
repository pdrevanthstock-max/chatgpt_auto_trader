from datetime import date, datetime

import pytest

from database.capital_ledger import CapitalLedger, CapitalTransactionType


def test_paper_refill_to_target_records_deposit_without_erasing_trading_loss(tmp_path):
    ledger = CapitalLedger(str(tmp_path / "capital.db"))
    current_equity = 8_634.65

    transaction = ledger.adjust_paper_to_target(
        current_equity=current_equity,
        target_equity=45_000.0,
        note="Refill PAPER test balance",
        engine_running=False,
        has_open_position=False,
    )

    assert transaction.transaction_type is CapitalTransactionType.DEPOSIT
    assert transaction.amount == pytest.approx(36_365.35)
    assert ledger.cash_adjustment_total("PAPER") == pytest.approx(36_365.35)
    assert current_equity + ledger.cash_adjustment_total("PAPER") == pytest.approx(45_000.0)


def test_trade_pnl_is_visible_in_ledger_but_not_double_counted_as_cash_flow(tmp_path):
    ledger = CapitalLedger(str(tmp_path / "capital.db"))

    ledger.record_trade_pnl("PAPER", "trade-1", -1_350.0)
    ledger.record(
        mode="PAPER",
        transaction_type=CapitalTransactionType.DEPOSIT,
        amount=1_350.0,
        note="Refill",
    )

    transactions = ledger.list_transactions("PAPER")
    assert [item.transaction_type for item in transactions] == [
        CapitalTransactionType.TRADE_PNL,
        CapitalTransactionType.DEPOSIT,
    ]
    assert ledger.cash_adjustment_total("PAPER") == 1_350.0


def test_trade_pnl_recording_is_idempotent_by_trade_reference(tmp_path):
    ledger = CapitalLedger(str(tmp_path / "capital.db"))

    first = ledger.record_trade_pnl("PAPER", "trade-1", -1_350.0)
    second = ledger.record_trade_pnl("PAPER", "trade-1", -1_350.0)

    assert second.id == first.id
    assert len(ledger.list_transactions("PAPER")) == 1


def test_zero_trade_pnl_is_still_audited(tmp_path):
    ledger = CapitalLedger(str(tmp_path / "capital.db"))

    transaction = ledger.record_trade_pnl("PAPER", "flat-trade", 0.0)

    assert transaction.amount == 0.0
    assert transaction.transaction_type is CapitalTransactionType.TRADE_PNL


def test_paper_equity_combines_base_capital_realized_pnl_and_cash_adjustments(tmp_path):
    ledger = CapitalLedger(str(tmp_path / "capital.db"))
    ledger.record(
        mode="PAPER",
        transaction_type=CapitalTransactionType.DEPOSIT,
        amount=36_365.35,
        note="Refill to target",
    )

    equity = ledger.paper_equity(
        base_capital=45_000.0,
        realized_net_pnl=-36_365.35,
    )

    assert equity == 45_000.0


@pytest.mark.parametrize("engine_running,has_open_position", [(True, False), (False, True)])
def test_capital_adjustment_is_blocked_while_engine_or_position_is_active(
    tmp_path, engine_running, has_open_position
):
    ledger = CapitalLedger(str(tmp_path / "capital.db"))

    with pytest.raises(ValueError, match="stopped.*no open position"):
        ledger.adjust_paper_to_target(
            current_equity=10_000.0,
            target_equity=45_000.0,
            note="Unsafe refill attempt",
            engine_running=engine_running,
            has_open_position=has_open_position,
        )

    assert ledger.list_transactions("PAPER") == []


def test_live_allocation_change_is_bounded_by_broker_confirmed_available_funds(tmp_path):
    ledger = CapitalLedger(str(tmp_path / "capital.db"))

    transaction = ledger.set_live_allocation(
        previous_allocation=0.0,
        new_allocation=40_000.0,
        broker_available_funds=100_000.0,
        note="Allocate only part of Dhan funds",
        engine_running=False,
        has_open_position=False,
    )

    assert transaction.transaction_type is CapitalTransactionType.ALLOCATION_CHANGE
    assert transaction.amount == 40_000.0
    assert transaction.broker_balance == 100_000.0
    assert ledger.latest_live_allocation() == 40_000.0

    with pytest.raises(ValueError, match="broker-confirmed"):
        ledger.set_live_allocation(
            previous_allocation=40_000.0,
            new_allocation=110_000.0,
            broker_available_funds=100_000.0,
            note="Must fail",
            engine_running=False,
            has_open_position=False,
        )


def test_latest_live_allocation_is_resulting_value_not_sum_from_unknown_baseline(tmp_path):
    ledger = CapitalLedger(str(tmp_path / "capital.db"))

    ledger.set_live_allocation(
        previous_allocation=45_000.0,
        new_allocation=40_000.0,
        broker_available_funds=100_000.0,
        note="Reduce strategy allocation",
        engine_running=False,
        has_open_position=False,
    )

    assert ledger.latest_live_allocation() == 40_000.0


def test_live_daily_stop_latches_for_the_day_and_survives_restart(tmp_path):
    db_path = str(tmp_path / "capital.db")
    ledger = CapitalLedger(db_path)
    trading_day = date(2026, 7, 14)

    ledger.latch_live_daily_stop(
        trading_day=trading_day,
        realized_pnl=-1_400.0,
        loss_limit=-1_350.0,
    )

    restarted = CapitalLedger(db_path)
    assert restarted.is_live_daily_stop_active(trading_day)
    assert not restarted.is_live_daily_stop_active(date(2026, 7, 15))


def test_live_allocation_change_does_not_clear_same_day_daily_stop(tmp_path):
    ledger = CapitalLedger(str(tmp_path / "capital.db"))
    trading_day = date(2026, 7, 14)
    ledger.latch_live_daily_stop(trading_day, -1_400.0, -1_350.0)

    ledger.set_live_allocation(
        previous_allocation=40_000.0,
        new_allocation=80_000.0,
        broker_available_funds=100_000.0,
        note="Increase allocation after stop",
        engine_running=False,
        has_open_position=False,
    )

    assert ledger.is_live_daily_stop_active(trading_day)
