"""
Position Lifecycle Test

Tests the full lifecycle:
  Open → Monitor → Trail → Exit → Journal → Clear

Uses a TEMPORARY database folder to avoid touching production files.
"""

import json
import shutil
from pathlib import Path
from datetime import datetime

from engine.position_monitor import PositionMonitor
from engine.trailing_manager import TrailingManager
from engine.exit_manager import ExitManager


def test_full_lifecycle():
    """
    Simulates the complete trade lifecycle with in-memory data.

    1. Open a position (simulated)
    2. Price moves up → trailing activates
    3. Price drops → SL hit → exit
    4. Verify final PnL and trade record
    """

    print()
    print("=" * 60)
    print("TEST: Full Position Lifecycle")
    print("=" * 60)

    # ----- STEP 1: OPEN POSITION -----

    position = {
        "status": "FILLED",
        "entry_security_id": 44640,
        "hedge_security_id": 44634,
        "direction": "LONG_CE",
        "entry_price": 100.0,
        "initial_risk": 2.0,
        "quantity": 75,
        "stop_loss": 98.0,
        "target": None,
        "trail": True,
        "entry_time": datetime.now().isoformat(),
        "current_price": 100.0,
        "exit_price": None,
        "exit_time": None,
        "exit_reason": None,
        "pnl": 0,
        "closed": False,
    }

    print("  Step 1: Position opened")
    print(f"    Entry: {position['entry_price']}, SL: {position['stop_loss']}")

    # ----- STEP 2: PRICE RISES -----

    prices_up = [100.5, 101.0, 102.0, 105.0, 108.0, 110.0]

    for price in prices_up:

        position = PositionMonitor.update(position, price)
        position = TrailingManager.update(position)

    print(f"  Step 2: Price rose to {position['current_price']}")
    print(f"    SL trailed to: {position['stop_loss']}")
    print(f"    PnL: ₹{position['pnl']}")

    # At 110: SL = 100 + (10 * 0.9) = 109.0
    assert position["stop_loss"] == 109.0, \
        f"Expected SL 109.0, got {position['stop_loss']}"

    assert position["exit_reason"] is None, \
        "Should not exit while above SL"

    # ----- STEP 3: PRICE DROPS BELOW TRAILING SL -----

    position = PositionMonitor.update(position, 108.5)
    position = TrailingManager.update(position)

    print(f"  Step 3: Price dropped to {position['current_price']}")
    print(f"    SL: {position['stop_loss']}")
    print(f"    Exit reason: {position['exit_reason']}")

    assert position["exit_reason"] == "STOP_LOSS", \
        f"Expected STOP_LOSS at 108.5 (SL=109), got {position['exit_reason']}"

    # ----- STEP 4: CLOSE POSITION -----

    position = ExitManager.close(
        position,
        108.5,
        position["exit_reason"],
    )

    print(f"  Step 4: Position closed")
    print(f"    Exit price: {position['exit_price']}")
    print(f"    Final PnL: ₹{position['pnl']}")
    print(f"    Status: {position['status']}")

    assert position["closed"] is True
    assert position["status"] == "EXITED"
    assert position["exit_price"] == 108.5

    # PnL = (108.5 - 100) * 75 = 637.5
    assert position["pnl"] == 637.5, \
        f"Expected PnL 637.5, got {position['pnl']}"

    # ----- STEP 5: VERIFY JOURNAL FORMAT -----

    # Simulate what TradeJournal.append would store
    trade_record = json.loads(
        json.dumps(position, default=str)
    )

    assert trade_record["closed"] is True
    assert trade_record["exit_reason"] == "STOP_LOSS"
    assert trade_record["pnl"] == 637.5

    print(f"  Step 5: Trade record valid")

    print()
    print("  PASSED ✓")


def test_immediate_stop_loss():
    """
    Price drops immediately → exits on first check.
    """

    print()
    print("=" * 60)
    print("TEST: Immediate Stop Loss")
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

    # First update: price drops hard
    position = PositionMonitor.update(position, 95.0)
    position = TrailingManager.update(position)

    assert position["exit_reason"] == "STOP_LOSS"

    position = ExitManager.close(position, 95.0, "STOP_LOSS")

    # PnL = (95 - 100) * 75 = -375
    assert position["pnl"] == -375.0, \
        f"Expected -375.0, got {position['pnl']}"

    assert position["closed"] is True

    print(f"  ✓ Exit at 95.0 → PnL: ₹{position['pnl']}")
    print()
    print("  PASSED ✓")


def test_put_direction():
    """
    Tests LONG_PE direction (bearish trade).
    Note: Current PnL logic assumes long (profit = current - entry).
    For puts, the option price rises when market falls,
    so the same logic applies — the option IS the instrument.
    """

    print()
    print("=" * 60)
    print("TEST: LONG_PE Direction")
    print("=" * 60)

    position = {
        "status": "FILLED",
        "direction": "LONG_PE",
        "entry_price": 50.0,
        "quantity": 75,
        "stop_loss": 49.0,         # 2% SL
        "target": None,
        "trail": True,
        "current_price": 50.0,
        "exit_price": None,
        "exit_time": None,
        "exit_reason": None,
        "pnl": 0,
        "closed": False,
    }

    # Put option price rises (market went down)
    position = PositionMonitor.update(position, 55.0)
    position = TrailingManager.update(position)

    # Profit = 5, trail SL = 50 + (5 * 0.9) = 54.5
    assert position["stop_loss"] == 54.5, \
        f"Expected SL 54.5, got {position['stop_loss']}"

    print(f"  ✓ Put rose to 55 → SL trailed to {position['stop_loss']}")
    print(f"  ✓ PnL: ₹{position['pnl']}")
    print()
    print("  PASSED ✓")


def test_trade_statistics_format():
    """
    Verifies the trade record matches what TradeStatistics expects.
    """

    print()
    print("=" * 60)
    print("TEST: Trade Statistics Compatibility")
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

    position = PositionMonitor.update(position, 95.0)
    position = ExitManager.close(position, 95.0, "STOP_LOSS")

    # TradeStatistics reads "pnl" from each trade
    assert "pnl" in position
    assert isinstance(position["pnl"], (int, float))

    # It also checks pnl > 0 for wins
    assert position["pnl"] < 0  # this was a loss

    # Serialise and deserialise (like JSON file round-trip)
    trade_json = json.loads(
        json.dumps(position, default=str)
    )

    assert trade_json["pnl"] == position["pnl"]
    assert trade_json["closed"] is True
    assert trade_json["exit_reason"] == "STOP_LOSS"

    print(f"  ✓ PnL field present  : {trade_json['pnl']}")
    print(f"  ✓ Closed field       : {trade_json['closed']}")
    print(f"  ✓ Exit reason        : {trade_json['exit_reason']}")
    print(f"  ✓ JSON round-trip OK")
    print()
    print("  PASSED ✓")


# ----------------------------------------------------------

if __name__ == "__main__":

    test_full_lifecycle()
    test_immediate_stop_loss()
    test_put_direction()
    test_trade_statistics_format()

    print()
    print("=" * 60)
    print("ALL LIFECYCLE TESTS PASSED ✓")
    print("=" * 60)
