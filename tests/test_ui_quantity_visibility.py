from pathlib import Path


def test_live_cards_and_journal_show_lots_and_units_per_leg():
    app_source = (Path(__file__).parents[1] / "ui" / "app.py").read_text(
        encoding="utf-8"
    )

    assert "{active_trade.quantity:,} lots" in app_source
    assert "{units_per_leg(active_trade):,} units/leg" in app_source
    assert '"Lots": t.quantity' in app_source
    assert '"Units / Leg": units_per_leg(t)' in app_source
