from datetime import datetime, timedelta, timezone

import pytest

from application.capital_affordability import build_capital_affordability


def test_capital_affordability_uses_combined_ask_and_index_lot_size():
    as_of = datetime(2026, 7, 17, 4, 1, 10, tzinfo=timezone.utc)

    view = build_capital_affordability(
        ce_ask=600.0,
        pe_ask=300.0,
        lot_size=30,
        available_capital=45_000.0,
        deployment_fraction=0.90,
        ce_quote_time=as_of - timedelta(seconds=3),
        pe_quote_time=as_of - timedelta(seconds=7),
        as_of=as_of,
    )

    assert view.combined_ask == 900.0
    assert view.lot_size == 30
    assert view.available_capital == 45_000.0
    assert view.deployable_capital == 40_500.0
    assert view.one_lot_premium == 27_000.0
    assert view.max_lots == 1
    assert view.estimated_round_trip_charges > 80.0
    assert view.charges_estimate == view.estimated_round_trip_charges
    assert view.maximum_premium_at_risk == 27_000.0
    assert view.as_dict()["charges_estimate"] == view.charges_estimate
    assert view.as_dict()["maximum_premium_at_risk"] == 27_000.0
    assert view.capital_shortfall == 0.0
    assert view.quote_age_seconds == 7.0
    assert view.affordable is True


def test_capital_affordability_reports_one_lot_shortfall():
    view = build_capital_affordability(
        ce_ask=400.0,
        pe_ask=300.0,
        lot_size=65,
        available_capital=45_000.0,
        deployment_fraction=0.90,
    )

    assert view.one_lot_premium == 45_500.0
    assert view.max_lots == 0
    assert view.capital_shortfall == 5_000.0
    assert view.affordable is False


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"ce_ask": -1.0}, "asks"),
        ({"ce_ask": 0.0}, "asks"),
        ({"lot_size": 0}, "lot_size"),
        ({"available_capital": -1.0}, "available_capital"),
        ({"deployment_fraction": 1.1}, "deployment_fraction"),
    ],
)
def test_capital_affordability_rejects_invalid_inputs(overrides, message):
    values = {
        "ce_ask": 100.0,
        "pe_ask": 100.0,
        "lot_size": 65,
        "available_capital": 45_000.0,
        "deployment_fraction": 0.90,
    }
    values.update(overrides)

    with pytest.raises(ValueError, match=message):
        build_capital_affordability(**values)
