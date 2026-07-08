"""
Domain Models
──────────────
Immutable dataclasses for all domain objects.
These are the data contracts between layers — no logic here.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List

from core.enums import TradeDirection, ExitReason


# ─────────────────────────────────────────────
# Market Data
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class Candle:
    """A single OHLCV candle (1-min or aggregated)."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0
    oi: int = 0  # open interest


@dataclass(frozen=True)
class PairedCandle:
    """
    Aligned CE + PE candle at the same timestamp and strike.
    This is the atomic unit for velocity calculations.
    """
    timestamp: datetime
    strike: int
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
    """
    §7.2 gotcha #2: One trading day's aligned CE+PE candle data.
    % change calculations must NEVER span a day boundary.
    """
    date: datetime
    strike: int
    candles: List[PairedCandle] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return len(self.candles) == 0


# ─────────────────────────────────────────────
# Signal / Scanning
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class VelocityResult:
    """Per-candle velocity calculation for a CE/PE pair."""
    timestamp: datetime
    strike: int
    ce_velocity: float       # ((Close - Open) / Open) * 100
    pe_velocity: float       # ((Close - Open) / Open) * 100
    divergence: float        # abs(ce_velocity - pe_velocity)
    winning_leg: str         # "CE" or "PE" — the leg with better performance


@dataclass(frozen=True)
class EntrySignal:
    """A confirmed entry signal that passed the 1–1.5% filter."""
    timestamp: datetime
    strike: int
    direction: TradeDirection
    divergence: float
    ce_velocity: float
    pe_velocity: float
    ce_price: float          # current CE price at signal time
    pe_price: float          # current PE price at signal time


# ─────────────────────────────────────────────
# Trade / Position
# ─────────────────────────────────────────────

@dataclass
class Trade:
    """
    A complete trade record (open or closed).

    §4.5 confirmed: BOTH legs are actually bought (2-contract basket).
    §4.6: Quantity is identical on both legs.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    # Direction
    direction: TradeDirection = TradeDirection.LONG_CE

    # Entry
    entry_ce_price: float = 0.0
    entry_pe_price: float = 0.0
    quantity: int = 0           # lot quantity, identical for both legs
    lot_size: int = 25          # Nifty lot size
    entry_time: Optional[datetime] = None
    strike: int = 0

    # Capital allocation (§5.1: 2% stop is relative to THIS)
    capital_allocated: float = 0.0

    # Current state (updated each scan cycle)
    current_ce_price: float = 0.0
    current_pe_price: float = 0.0
    peak_combined_pnl: float = 0.0   # highest PnL seen (for trailing)
    trailing_stop_pnl: float = 0.0   # trailing stop level in PnL terms

    # Exit
    exit_ce_price: Optional[float] = None
    exit_pe_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    exit_reason: Optional[ExitReason] = None

    @property
    def is_open(self) -> bool:
        return self.exit_time is None

    @property
    def entry_leg_price(self) -> float:
        """The entry price of the primary (winning) leg."""
        if self.direction == TradeDirection.LONG_CE:
            return self.entry_ce_price
        return self.entry_pe_price

    @property
    def hedge_leg_price(self) -> float:
        """The entry price of the hedge leg."""
        if self.direction == TradeDirection.LONG_CE:
            return self.entry_pe_price
        return self.entry_ce_price

    @property
    def current_entry_leg_price(self) -> float:
        """Current price of the primary leg."""
        if self.direction == TradeDirection.LONG_CE:
            return self.current_ce_price
        return self.current_pe_price

    @property
    def current_hedge_leg_price(self) -> float:
        """Current price of the hedge leg."""
        if self.direction == TradeDirection.LONG_CE:
            return self.current_pe_price
        return self.current_ce_price

    @property
    def total_contracts(self) -> int:
        """Total number of individual contracts (quantity × lot_size × 2 legs)."""
        return self.quantity * self.lot_size * 2

    @property
    def combined_pnl(self) -> float:
        """
        Combined PnL across both legs.
        Both legs are bought, so PnL = (current - entry) × qty × lot_size for each.
        """
        if not self.is_open and self.exit_ce_price is not None:
            ce_pnl = (self.exit_ce_price - self.entry_ce_price) * self.quantity * self.lot_size
            pe_pnl = (self.exit_pe_price - self.entry_pe_price) * self.quantity * self.lot_size
        else:
            ce_pnl = (self.current_ce_price - self.entry_ce_price) * self.quantity * self.lot_size
            pe_pnl = (self.current_pe_price - self.entry_pe_price) * self.quantity * self.lot_size
        return round(ce_pnl + pe_pnl, 2)

    @property
    def entry_leg_pnl(self) -> float:
        """PnL on the entry (primary) leg only."""
        price_diff = self.current_entry_leg_price - self.entry_leg_price
        return round(price_diff * self.quantity * self.lot_size, 2)

    @property
    def hedge_leg_pnl(self) -> float:
        """PnL on the hedge leg only."""
        price_diff = self.current_hedge_leg_price - self.hedge_leg_price
        return round(price_diff * self.quantity * self.lot_size, 2)


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
        return trade.combined_pnl

    @property
    def total_pnl(self) -> float:
        return round(self.realized_pnl + self.unrealized_pnl, 2)

    def close_trade(self, trade: Trade) -> None:
        """Record a closed trade's PnL into realized."""
        self.realized_pnl = round(self.realized_pnl + trade.combined_pnl, 2)
