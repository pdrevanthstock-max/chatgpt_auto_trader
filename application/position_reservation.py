from __future__ import annotations

import uuid
from dataclasses import dataclass
from threading import RLock


@dataclass(frozen=True)
class ReservationSnapshot:
    state: str
    owner: str | None
    candidate_id: str | None


class PositionReservation:
    """Atomic global position slot shared by all index scanners."""

    def __init__(self) -> None:
        self._state = "EMPTY"
        self._owner: str | None = None
        self._candidate_id: str | None = None
        self._lock = RLock()

    def snapshot(self) -> ReservationSnapshot:
        with self._lock:
            return ReservationSnapshot(self._state, self._owner, self._candidate_id)

    def try_reserve(self, candidate_id: str) -> str | None:
        with self._lock:
            if self._state != "EMPTY":
                return None
            token = str(uuid.uuid4())
            self._state = "RESERVED"
            self._owner = token
            self._candidate_id = str(candidate_id)
            return token

    def activate(self, token: str) -> bool:
        with self._lock:
            if self._state != "RESERVED" or token != self._owner:
                return False
            self._state = "ACTIVE"
            return True

    def release(self, token: str) -> bool:
        with self._lock:
            if self._state == "EMPTY" or token != self._owner:
                return False
            self._state = "EMPTY"
            self._owner = None
            self._candidate_id = None
            return True
