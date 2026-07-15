from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class IndexPermission(str, Enum):
    TRADABLE = "TRADABLE"
    OBSERVE_ONLY = "OBSERVE_ONLY"


@dataclass(frozen=True)
class IndexSpec:
    symbol: str
    display_name: str
    lot_size: int
    permission: IndexPermission
    metadata_requires_runtime_validation: bool = True
    runtime_connected: bool = False


class IndexRegistry:
    def __init__(self, specs: Mapping[str, IndexSpec]) -> None:
        normalized = {str(key).upper(): value for key, value in specs.items()}
        if not normalized:
            raise ValueError("Index registry cannot be empty.")
        if any(spec.lot_size <= 0 for spec in normalized.values()):
            raise ValueError("Every index lot size must be positive.")
        self._specs = MappingProxyType(normalized)

    @classmethod
    def default(cls) -> "IndexRegistry":
        # Lot sizes are safe fallbacks for the current contract generation.
        # The live instrument master must validate/override them before execution.
        return cls({
            "NIFTY": IndexSpec(
                "NIFTY", "NIFTY 50", 65, IndexPermission.TRADABLE,
                runtime_connected=True,
            ),
            "BANKNIFTY": IndexSpec("BANKNIFTY", "NIFTY Bank", 30, IndexPermission.TRADABLE),
            "FINNIFTY": IndexSpec("FINNIFTY", "NIFTY Financial Services", 60, IndexPermission.TRADABLE),
            "MIDCPNIFTY": IndexSpec("MIDCPNIFTY", "NIFTY Midcap Select", 120, IndexPermission.OBSERVE_ONLY),
            "NIFTYNXT50": IndexSpec("NIFTYNXT50", "NIFTY Next 50", 25, IndexPermission.OBSERVE_ONLY),
        })

    @property
    def symbols(self) -> set[str]:
        return set(self._specs)

    def get(self, symbol: str) -> IndexSpec:
        normalized = str(symbol).upper()
        try:
            return self._specs[normalized]
        except KeyError as exc:
            raise ValueError(f"Unsupported index: {normalized}") from exc
