import logging
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Callable, Dict, Set


class GridState(str, Enum):
    INIT = "INIT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ERROR = "ERROR"
    CLOSED = "CLOSED"


# Welche Zustandswechsel sind erlaubt?
ALLOWED_TRANSITIONS: Dict[GridState, Set[GridState]] = {
    GridState.INIT:   {GridState.ACTIVE, GridState.ERROR, GridState.CLOSED},
    GridState.ACTIVE: {GridState.PAUSED, GridState.ERROR, GridState.CLOSED},
    GridState.PAUSED: {GridState.ACTIVE, GridState.ERROR, GridState.CLOSED},
    GridState.ERROR:  {GridState.PAUSED, GridState.CLOSED},   # bewusst kein direkter Sprung zu ACTIVE
    GridState.CLOSED: set(),                                   # Terminal
}


@dataclass
class GridLifecycle:
    symbol: str
    on_state_change: Optional[Callable[[GridState, GridState, Optional[str]], None]] = None
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))
    state: GridState = field(default=GridState.INIT, init=False)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc), init=False)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc), init=False)
    error_message: Optional[str] = field(default=None, init=False)

    def __post_init__(self):
        self.logger.info(f"[{self.symbol}] GridLifecycle initialisiert -> Zustand: {self.state.value}")

    def set_state(self, new_state: GridState, message: Optional[str] = None) -> None:
        if new_state not in ALLOWED_TRANSITIONS[self.state]:
            raise ValueError(
                f"Ungültiger Zustandswechsel: {self.state.value} → {new_state.value}"
            )

        old = self.state
        self.state = new_state
        self.updated_at = datetime.now(timezone.utc)
        self.error_message = message if new_state == GridState.ERROR else None

        # Logging
        if new_state is GridState.ERROR:
            self.logger.error(f"[{self.symbol}] {old.value} → ERROR: {message}")
        elif new_state is GridState.PAUSED:
            self.logger.warning(f"[{self.symbol}] {old.value} → PAUSED: {message or ''}")
        elif new_state is GridState.CLOSED:
            self.logger.info(f"[{self.symbol}] {old.value} → CLOSED")
        else:
            self.logger.info(f"[{self.symbol}] {old.value} → {new_state.value}")

        # Optionaler Callback
        if self.on_state_change:
            try:
                self.on_state_change(old, new_state, message)
            except Exception as cb_err:
                self.logger.exception(f"[{self.symbol}] on_state_change Callback-Fehler: {cb_err}")

    # Convenience-Checks
    def is_active(self) -> bool:
        return self.state is GridState.ACTIVE

    def is_paused(self) -> bool:
        return self.state is GridState.PAUSED

    def has_error(self) -> bool:
        return self.state is GridState.ERROR

    def summary(self) -> dict:
        return {
            "symbol": self.symbol,
            "state": self.state.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "error_message": self.error_message,
        }
