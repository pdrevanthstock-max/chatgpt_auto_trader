"""
Application Runtime State

This stores temporary values only.

Nothing here is permanent.
"""

from dataclasses import dataclass


@dataclass
class RuntimeState:

    broker_connected: bool = False

    market_open: bool = False

    in_position: bool = False

    active_call = None

    active_put = None

    total_pnl: float = 0.0

    last_scan_time: str = ""


runtime_state = RuntimeState()