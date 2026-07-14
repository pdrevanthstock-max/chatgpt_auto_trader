from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from core.enums import TradeDirection, ExitReason, MarketRegime, TradePhase, OrderType, SignalType
from core.transaction_costs import OptionCostBreakdown, calculate_option_round_trip_costs

@dataclass(frozen=True)
class Candle:
    """A single OHLCV candle."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0
    oi: int = 0
    strike: float = 0.0
    spot: float = 0.0

@dataclass(frozen=True)
class PairedCandle:
    """Aligned CE + PE candle at the same timestamp."""
    timestamp: datetime
    ce_open: float
    ce_high: float
    ce_low: float
    ce_close: float
    ce_volume: int
    pe_open: float
    pe_high: float
    pe_low: float
    pe_close: float
    pe_volume: int

@dataclass
class DayBucket:
    """A single trading day's aligned CE+PE candle data for a strike pair."""
    date: datetime
    strike_ce: int
    strike_pe: int
    candles: List[PairedCandle] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return len(self.candles) == 0

@dataclass(frozen=True)
class CandidatePair:
    """A generated CE x PE candidate pair before scoring."""
    ce_strike: int
    pe_strike: int
    ce_velocity: float
    pe_velocity: float
    divergence: float
    winning_leg: str  # "CE" or "PE"

@dataclass(frozen=True)
class ScoredCandidate:
    """A candidate pair with projected net profit and confidence score."""
    ce_strike: int
    pe_strike: int
    ce_velocity: float
    pe_velocity: float
    divergence: float
    winning_leg: str
    projected_net_profit: float
    confidence: float

@dataclass
class TradePlan:
    """Assembled trade details before entry order execution."""
    scored_candidate: ScoredCandidate
    regime: MarketRegime
    order_type: OrderType
    quantity: int
    lot_size: int = 65
    ce_limit_price: Optional[float] = None
    pe_limit_price: Optional[float] = None
    post_daily_sl: bool = False
    risk_capital_at_entry: float = 0.0
    hard_stop_loss: float = 0.0

@dataclass
class Trade:
    """Tracks the lifecycle of an active or closed trade."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    direction: TradeDirection = TradeDirection.LONG_CE
    strike_ce: int = 0
    strike_pe: int = 0
    entry_ce_price: float = 0.0
    entry_pe_price: float = 0.0
    quantity: int = 0
    lot_size: int = 65
    entry_time: Optional[datetime] = None
    regime_at_entry: MarketRegime = MarketRegime.SIDEWAYS
    phase: TradePhase = TradePhase.PHASE_1_BOTH_LEGS
    post_daily_sl: bool = False
    risk_capital_at_entry: float = 0.0
    hard_stop_loss: float = 0.0
    ce_open_units: Optional[int] = None
    pe_open_units: Optional[int] = None
    
    # State tracking
    ce_current_price: float = 0.0
    pe_current_price: float = 0.0
    peak_combined_pnl: float = 0.0
    peak_single_leg_pnl: float = 0.0
    
    # Phase transition (hedge cut)
    hedge_cut_time: Optional[datetime] = None
    losing_leg_exit_price: Optional[float] = None
    losing_leg_pnl: float = 0.0
    
    # Exit
    exit_ce_price: Optional[float] = None
    exit_pe_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    exit_reason: Optional[ExitReason] = None
    target_pnl: Optional[float] = None  # Saved target for exit precision

    @property
    def is_open(self) -> bool:
        return self.phase != TradePhase.CLOSED

    @property
    def winning_leg(self) -> str:
        if self.direction == TradeDirection.LONG_CE:
            return "CE"
        return "PE"

    @property
    def losing_leg(self) -> str:
        if self.direction == TradeDirection.LONG_CE:
            return "PE"
        return "CE"

    @property
    def entry_winning_price(self) -> float:
        return self.entry_ce_price if self.winning_leg == "CE" else self.entry_pe_price

    @property
    def entry_losing_price(self) -> float:
        return self.entry_pe_price if self.winning_leg == "CE" else self.entry_ce_price

    @property
    def current_winning_price(self) -> float:
        return self.ce_current_price if self.winning_leg == "CE" else self.pe_current_price

    @property
    def current_losing_price(self) -> float:
        return self.pe_current_price if self.winning_leg == "CE" else self.ce_current_price

    @property
    def exit_winning_price(self) -> Optional[float]:
        return self.exit_ce_price if self.winning_leg == "CE" else self.exit_pe_price

    @property
    def exit_losing_price(self) -> Optional[float]:
        return self.exit_pe_price if self.winning_leg == "CE" else self.exit_ce_price

    @property
    def combined_pnl(self) -> float:
        if self.phase == TradePhase.PHASE_1_BOTH_LEGS:
            ce_p = (self.ce_current_price - self.entry_ce_price) * self.quantity * self.lot_size
            pe_p = (self.pe_current_price - self.entry_pe_price) * self.quantity * self.lot_size
            return round(ce_p + pe_p, 2)
        elif self.phase == TradePhase.PHASE_2_SINGLE_LEG:
            winning_p = (self.current_winning_price - self.entry_winning_price) * self.quantity * self.lot_size
            return round(self.losing_leg_pnl + winning_p, 2)
        else:  # CLOSED
            if self.losing_leg_exit_price is not None:
                w_exit = self.exit_winning_price if self.exit_winning_price is not None else self.current_winning_price
                winning_p = (w_exit - self.entry_winning_price) * self.quantity * self.lot_size
                return round(self.losing_leg_pnl + winning_p, 2)
            else:
                ce_ex = self.exit_ce_price if self.exit_ce_price is not None else self.ce_current_price
                pe_ex = self.exit_pe_price if self.exit_pe_price is not None else self.pe_current_price
                ce_p = (ce_ex - self.entry_ce_price) * self.quantity * self.lot_size
                pe_p = (pe_ex - self.entry_pe_price) * self.quantity * self.lot_size
                return round(ce_p + pe_p, 2)

    @property
    def gross_pnl(self) -> float:
        return self.combined_pnl

    @property
    def units_per_leg(self) -> int:
        return self.quantity * self.lot_size

    @property
    def display_id(self) -> str:
        return f"{self.id}-SL" if self.post_daily_sl else self.id

    @property
    def transaction_cost_breakdown(self) -> OptionCostBreakdown:
        ce_exit = self.exit_ce_price
        if ce_exit is None:
            ce_exit = self.ce_current_price if self.ce_current_price > 0.0 else self.entry_ce_price

        pe_exit = self.exit_pe_price
        if pe_exit is None:
            pe_exit = self.pe_current_price if self.pe_current_price > 0.0 else self.entry_pe_price

        return calculate_option_round_trip_costs(
            entry_ce_price=self.entry_ce_price,
            entry_pe_price=self.entry_pe_price,
            exit_ce_price=ce_exit,
            exit_pe_price=pe_exit,
            lots=self.quantity,
            lot_size=self.lot_size,
        )

    @property
    def transaction_costs(self) -> float:
        return self.transaction_cost_breakdown.total

    @property
    def net_pnl(self) -> float:
        return round(self.combined_pnl - self.transaction_costs, 2)

@dataclass
class DaySession:
    """Tracks all trades and PnL for a single trading day."""
    date: datetime = None
    trades: List[Trade] = field(default_factory=list)
    realized_pnl: float = 0.0
    circuit_breaker_hit: bool = False

    @property
    def trade_count(self) -> int:
        return len(self.trades)

    @property
    def open_trade(self) -> Optional[Trade]:
        for t in reversed(self.trades):
            if t.is_open:
                return t
        return None

    @property
    def unrealized_pnl(self) -> float:
        trade = self.open_trade
        if trade is None:
            return 0.0
        return trade.net_pnl

    @property
    def total_pnl(self) -> float:
        return round(self.realized_pnl + self.unrealized_pnl, 2)

    def close_trade(self, trade: Trade) -> None:
        self.realized_pnl = round(self.realized_pnl + trade.net_pnl, 2)

@dataclass
class ExecutionSignal:
    """FIFO queue signal package."""
    type: SignalType
    timestamp: datetime = field(default_factory=datetime.now)
    trade_id: Optional[str] = None
    trade_plan: Optional[TradePlan] = None
    reason: Optional[str] = None
