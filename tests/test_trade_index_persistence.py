from datetime import datetime

from core.enums import MarketRegime, TradeDirection, TradePhase
from core.models import Trade
from database.trade_store import TradeStore
from execution.crash_recovery import CrashRecovery


def _bank_trade() -> Trade:
    return Trade(
        id="bank-paper", execution_mode="PAPER", index_symbol="BANKNIFTY",
        direction=TradeDirection.LONG_CE, strike_ce=58_000, strike_pe=58_100,
        entry_ce_price=100.0, entry_pe_price=99.0, quantity=2, lot_size=30,
        entry_time=datetime(2026, 7, 16, 10, 30),
        regime_at_entry=MarketRegime.DIRECTIONAL,
        phase=TradePhase.PHASE_1_BOTH_LEGS,
    )


def test_trade_store_round_trips_index_symbol(tmp_path):
    store = TradeStore(str(tmp_path / "trades.db"))
    store.save_trade(_bank_trade())
    assert store.get_all_trades()[0].index_symbol == "BANKNIFTY"


def test_crash_recovery_round_trips_index_symbol(tmp_path):
    recovery = CrashRecovery(str(tmp_path / "state.json"))
    recovery.save_state(0.0, _bank_trade(), execution_mode="PAPER")
    _, loaded = recovery.load_state(execution_mode="PAPER")
    assert loaded is not None
    assert loaded.index_symbol == "BANKNIFTY"
