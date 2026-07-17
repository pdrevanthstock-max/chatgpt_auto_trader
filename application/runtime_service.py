from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from typing import Callable, Protocol

from application.diagnostic_capture import DiagnosticCaptureService
from application.index_selection import IndexSelectionService
from application.market_session import MarketSessionSchedule
from application.system_health import SystemHealthService, SystemHealthSnapshot


class EnginePort(Protocol):
    running: bool
    session_execution_mode: str | None
    active_trade: object | None
    activity_log: list[str]

    def start(self) -> None: ...
    def stop(self) -> None: ...


@dataclass(frozen=True)
class RuntimeSnapshot:
    state: str
    execution_mode: str
    has_active_position: bool
    activity: tuple[str, ...]
    market_phase: str
    market_status: str
    seconds_to_next_phase: int
    system_health: dict[str, object]


class RuntimeService:
    """Owns one process-level engine and enforces the web app's PAPER-only lock."""

    def __init__(
        self,
        engine_factory: Callable[[], EnginePort],
        now_provider: Callable[[], datetime] | None = None,
        health_provider: Callable[[], SystemHealthSnapshot] | None = None,
    ) -> None:
        self._factory = engine_factory
        self._engine: EnginePort | None = None
        self._lock = RLock()
        self._now_provider = now_provider or datetime.now
        self._market_schedule = MarketSessionSchedule()
        self._health_provider = health_provider or SystemHealthService().snapshot

    @property
    def engine(self) -> EnginePort | None:
        with self._lock:
            return self._engine

    def snapshot(self) -> RuntimeSnapshot:
        with self._lock:
            engine = self._engine
            running = bool(engine and engine.running)
            active = bool(
                engine
                and engine.active_trade is not None
                and getattr(engine.active_trade, "is_open", False)
            )
            market = self._market_schedule.at(self._now_provider())
            return RuntimeSnapshot(
                state="RUNNING" if running else "STOPPED",
                execution_mode="PAPER",
                has_active_position=active,
                activity=tuple(list(engine.activity_log)[-200:]) if engine else (),
                market_phase=market.phase.value,
                market_status=market.message,
                seconds_to_next_phase=market.seconds_to_next_phase,
                system_health=self._health_provider().as_dict(),
            )

    def start(self) -> RuntimeSnapshot:
        with self._lock:
            if self._engine is not None and self._engine.running:
                return self.snapshot()
            if self._engine is None:
                self._engine = self._factory()
            self._engine.start()
            confirmed = str(self._engine.session_execution_mode or "").upper()
            if confirmed != "PAPER":
                self._engine.stop()
                raise RuntimeError("Web runtime did not confirm PAPER mode; startup was aborted.")
            return self.snapshot()

    def stop(self) -> RuntimeSnapshot:
        with self._lock:
            if self.snapshot().has_active_position:
                raise RuntimeError(
                    "Engine cannot stop while an active position requires risk and exit monitoring."
                )
            if self._engine is not None and self._engine.running:
                self._engine.stop()
            return self.snapshot()


def production_paper_engine_factory(
    diagnostics: DiagnosticCaptureService,
    selection: IndexSelectionService,
) -> Callable[[], EnginePort]:
    def create() -> EnginePort:
        # Lazy import avoids Streamlit compatibility initialization until the
        # user explicitly starts the PAPER engine from the web UI.
        from ui.app import LiveEngine

        return LiveEngine(
            execution_mode_lock="PAPER",
            diagnostic_capture=diagnostics,
            index_selection=selection,
        )

    return create
