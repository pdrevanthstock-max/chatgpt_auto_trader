from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable


@dataclass(frozen=True)
class SystemHealthSnapshot:
    cpu_percent: float | None
    memory_percent: float | None
    status: str
    explanation: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _read_psutil() -> tuple[float, float]:
    import psutil

    return float(psutil.cpu_percent(interval=None)), float(psutil.virtual_memory().percent)


class SystemHealthService:
    """Reads real host metrics and classifies them without fabricated fallbacks."""

    def __init__(
        self,
        metrics_provider: Callable[[], tuple[float, float]] | None = None,
    ) -> None:
        self._metrics_provider = metrics_provider or _read_psutil

    def snapshot(self) -> SystemHealthSnapshot:
        try:
            cpu, memory = self._metrics_provider()
            cpu = round(float(cpu), 2)
            memory = round(float(memory), 2)
            if not 0.0 <= cpu <= 100.0 or not 0.0 <= memory <= 100.0:
                raise ValueError("metric percentage outside 0-100")
        except (ImportError, OSError, RuntimeError, TypeError, ValueError):
            return SystemHealthSnapshot(
                cpu_percent=None,
                memory_percent=None,
                status="UNAVAILABLE",
                explanation="System metrics are unavailable; no fallback values are shown.",
            )

        if cpu >= 90.0:
            status, explanation = "CRITICAL", "Critical: CPU is at or above 90%."
        elif memory >= 95.0:
            status, explanation = "CRITICAL", "Critical: memory is at or above 95%."
        elif cpu >= 75.0:
            status, explanation = "WARNING", "Warning: CPU is at or above 75%."
        elif memory >= 85.0:
            status, explanation = "WARNING", "Warning: memory is at or above 85%."
        else:
            status = "NORMAL"
            explanation = "CPU and memory are below warning thresholds."
        return SystemHealthSnapshot(cpu, memory, status, explanation)
