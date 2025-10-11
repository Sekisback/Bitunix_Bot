# file: strategies/GRID/manager/grid_lifecycle.py

import logging
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable, Dict, Set

class GridState(str, Enum):
    INIT = "INIT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ERROR = "ERROR"
    CLOSED = "CLOSED"

ALLOWED_TRANSITIONS: Dict[GridState, Set[GridState]] = {
    GridState.INIT:   {GridState.ACTIVE, GridState.ERROR, GridState.CLOSED},
    GridState.ACTIVE: {GridState.PAUSED, GridState.ERROR, GridState.CLOSED},
    GridState.PAUSED: {GridState.ACTIVE, GridState.ERROR, GridState.CLOSED},
    GridState.ERROR:  {GridState.PAUSED, GridState.CLOSED},
    GridState.CLOSED: set(),
}

@dataclass
class GridLifecycle:
    symbol: str
    on_state_change: Optional[Callable[[GridState, GridState, Optional[str]], None]] = None
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("GridLifecycle"))
    state: GridState = field(default=GridState.INIT, init=False)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc), init=False)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc), init=False)
    error_message: Optional[str] = field(default=None, init=False)
    last_error_time: Optional[datetime] = field(default=None, init=False)
    retry_interval: int = field(default=30, init=False)  # Sekunden bis Retry erlaubt

    #def __post_init__(self):
        #self.logger.info(f"[{self.symbol}] GridLifecycle initialisiert -> Zustand: {self.state.value}")

    def set_state(self, new_state: GridState, message: Optional[str] = None) -> None:
        if new_state not in ALLOWED_TRANSITIONS[self.state]:
            raise ValueError(
                f"Ungültiger Zustandswechsel: {self.state.value} → {new_state.value}"
            )

        old = self.state
        self.state = new_state
        self.updated_at = datetime.now(timezone.utc)
        self.error_message = message if new_state == GridState.ERROR else None
        if new_state == GridState.ERROR:
            self.last_error_time = self.updated_at

        # Logging
        if new_state is GridState.ERROR:
            self.logger.error(f"[{self.symbol}] {old.value} → ERROR: {message}")
        elif new_state is GridState.PAUSED:
            self.logger.warning(f"[{self.symbol}] {old.value} → PAUSED: {message or ''}")
        elif new_state is GridState.CLOSED:
            self.logger.info(f"[{self.symbol}] {old.value} → CLOSED")
        # else:
        #     self.logger.info(f"[{self.symbol}] {old.value} → {new_state.value}")

        # Callback
        if self.on_state_change:
            try:
                self.on_state_change(old, new_state, message)
            except Exception as cb_err:
                self.logger.exception(f"[{self.symbol}] on_state_change Callback-Fehler: {cb_err}")

    # --- NEU: Recovery-Prüfung ---
    def can_retry(self) -> bool:
        """True, wenn Retry nach Fehler erlaubt ist."""
        if not self.last_error_time:
            return False
        elapsed = datetime.now(timezone.utc) - self.last_error_time
        return elapsed >= timedelta(seconds=self.retry_interval)

    def summary(self) -> dict:
        return {
            "symbol": self.symbol,
            "state": self.state.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "error_message": self.error_message,
            "last_error_time": self.last_error_time.isoformat() if self.last_error_time else None,
        }

    # ------------------------------------------------------------
    # Kompatibilitätsfunktionen (alte Methodenbezeichner)
    # ------------------------------------------------------------
    def is_active(self) -> bool:
        return self.state is GridState.ACTIVE

    def is_paused(self) -> bool:
        return self.state is GridState.PAUSED

    def has_error(self) -> bool:
        return self.state is GridState.ERROR
