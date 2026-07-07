"""
Exit Flow Test

Tests that stop-loss and trailing stop exits work correctly.

Uses temporary test data — does NOT touch production database files.
"""

import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

from engine.position_monitor import PositionMonitor
from engine.trailing_manager import TrailingManager
from engine.exit_manager import ExitManager


def test_stop_loss_exit():
    """
    Simulates a price drop below stop-loss.
    Verifies exit_reason = STOP_LOSS.
    """

    print()
    print("=" * 60)
    print("TEST: Stop Loss Exit")
    print("=" * 60)

    position = {
        "status": "FILLED",
        "direction": "LONG_CE",
        "entry_price": 100.0,
        "quantity": 75,
        "stop_loss": 98.0,         # 2% SL
        "target": None,
        "trail": True,
        "current_price": 100.0,
        "exit_price": None,
        "exit_time": None,
        "exit_reason": None,
        "pnl": 0,
        "closed": False,
    }

    # Price drops to 97 — below SL of 98
    updated = PositionMonitor.update(position, 97.0)

    assert updated["exit_reason"] == "STOP_LOSS", \
        f"Expected STOP_LOSS, got {updated['exit_reason']}"

    assert updated["pnl"] == -225.0, \
        f"Expected PnL -225.0, got {updated['pnl']}"

    print(f"  ✓ Exit reason  : {updated['exit_reason']}")
    print(f"  ✓ PnL          : {updated['pnl']}")

    # Now close the position
    closed = ExitManager.close(updated, 97.0, "STOP_LOSS")

    assert closed["closed"] is True
    assert closed["status"] == "EXITED"
    assert closed["exit_price"] == 97.0
    assert closed["pnl"] == -225.0

    print(f"  ✓ Closed       : {closed['closed']}")
    print(f"  ✓ Status       : {closed['status']}")
    print(f"  ✓ Exit price   : {closed['exit_price']}")
    print()
    print("  PASSED ✓")


def test_no_exit_above_stop():
    """
    Price stays above stop-loss — no exit should trigger.
    """

    print()
    print("=" * 60)
    print("TEST: No Exit Above Stop Loss")
    print("=" * 60)

    position = {
        "status": "FILLED",
        "direction": "LONG_CE",
        "entry_price": 100.0,
        "quantity": 75,
        "stop_loss": 98.0,
        "target": None,
        "trail": True,
        "current_price": 100.0,
        "exit_price": None,
        "exit_time": None,
        "exit_reason": None,
        "pnl": 0,
        "closed": False,
    }

    # Price drops slightly but stays above SL
    updated = PositionMonitor.update(position, 99.0)

    assert updated["exit_reason"] is None, \
        f"Expected None, got {updated['exit_reason']}"

    print(f"  ✓ Exit reason  : {updated['exit_reason']} (no exit)")
    print(f"  ✓ PnL          : {updated['pnl']}")
    print()
    print("  PASSED ✓")


def test_trailing_stop_activation():
    """
    Tests trailing stop activates at +1% profit
    and locks in 90% of gains.
    """

    print()
    print("=" * 60)
    print("TEST: Trailing Stop Activation")
    print("=" * 60)

    position = {
        "status": "FILLED",
        "direction": "LONG_CE",
        "entry_price": 100.0,
        "quantity": 75,
        "stop_loss": 98.0,         # initial 2% SL
        "target": None,
        "trail": True,
        "current_price": 100.0,
        "exit_price": None,
        "exit_time": None,
        "exit_reason": None,
        "pnl": 0,
        "closed": False,
    }

    # Step 1: Price at 100.5 (+0.5%) — trailing should NOT activate
    position = PositionMonitor.update(position, 100.5)
    position = TrailingManager.update(position)

    assert position["stop_loss"] == 98.0, \
        f"SL should stay at 98.0, got {position['stop_loss']}"

    print(f"  ✓ +0.5% → SL stays at {position['stop_loss']}")

    # Step 2: Price at 101.5 (+1.5%) — trailing activates
    position = PositionMonitor.update(position, 101.5)
    position = TrailingManager.update(position)

    # new_stop = 100 + (1.5 * 0.9) = 101.35
    expected_sl = 101.35

    assert position["stop_loss"] == expected_sl, \
        f"Expected SL {expected_sl}, got {position['stop_loss']}"

    print(f"  ✓ +1.5% → SL moves to {position['stop_loss']}")

    # Step 3: Price at 110 (+10%) — trail follows
    position = PositionMonitor.update(position, 110.0)
    position = TrailingManager.update(position)

    # new_stop = 100 + (10 * 0.9) = 109.0
    expected_sl = 109.0

    assert position["stop_loss"] == expected_sl, \
        f"Expected SL {expected_sl}, got {position['stop_loss']}"

    print(f"  ✓ +10%  → SL moves to {position['stop_loss']}")

    # Step 4: Price drops to 108 — SL should stay at 109 (never goes down)
    position = PositionMonitor.update(position, 108.0)
    position = TrailingManager.update(position)

    assert position["stop_loss"] == 109.0, \
        f"SL should stay at 109.0, got {position['stop_loss']}"

    print(f"  ✓ Drop  → SL stays at {position['stop_loss']}")

    # Step 5: Price at 108 is below SL 109 — exit triggered
    assert position["exit_reason"] == "STOP_LOSS", \
        f"Expected STOP_LOSS, got {position['exit_reason']}"

    print(f"  ✓ 108 < 109 → exit: {position['exit_reason']}")

    # Final PnL: (108 - 100) * 75 = 600
    assert position["pnl"] == 600.0, \
        f"Expected PnL 600.0, got {position['pnl']}"

    print(f"  ✓ PnL locked: ₹{position['pnl']}")
    print()
    print("  PASSED ✓")


def test_trailing_never_moves_down():
    """
    Once SL moves up, it should NEVER decrease.
    """

    print()
    print("=" * 60)
    print("TEST: Trailing Stop Never Moves Down")
    print("=" * 60)

    position = {
        "status": "FILLED",
        "direction": "LONG_CE",
        "entry_price": 100.0,
        "quantity": 75,
        "stop_loss": 98.0,
        "target": None,
        "trail": True,
        "current_price": 100.0,
        "exit_price": None,
        "exit_time": None,
        "exit_reason": None,
        "pnl": 0,
        "closed": False,
    }

    # Price to 105 → SL = 100 + (5 * 0.9) = 104.5
    position = PositionMonitor.update(position, 105.0)
    position = TrailingManager.update(position)
    sl_after_up = position["stop_loss"]

    print(f"  Price 105 → SL = {sl_after_up}")

    # Price drops to 104.6 (above SL) → SL should NOT decrease
    position = PositionMonitor.update(position, 104.6)
    position = TrailingManager.update(position)

    assert position["stop_loss"] == sl_after_up, \
        f"SL moved down! Was {sl_after_up}, now {position['stop_loss']}"

    print(f"  Price 104.6 → SL stays {position['stop_loss']}")
    print()
    print("  PASSED ✓")


# ----------------------------------------------------------

if __name__ == "__main__":

    test_stop_loss_exit()
    test_no_exit_above_stop()
    test_trailing_stop_activation()
    test_trailing_never_moves_down()

    print()
    print("=" * 60)
    print("ALL EXIT FLOW TESTS PASSED ✓")
    print("=" * 60)
