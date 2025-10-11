# strategies/GRID/exceptions.py
"""
Custom Exceptions für Grid Trading Bot
Ermöglicht spezifisches Error-Handling
"""


class GridException(Exception):
    """Basis-Exception für alle Grid-Fehler"""
    pass


class ConfigValidationError(GridException):
    """Config-Validierung fehlgeschlagen"""
    pass


class InsufficientBalanceError(GridException):
    """Balance zu niedrig für Order"""
    def __init__(self, required: float, available: float):
        self.required = required
        self.available = available
        super().__init__(
            f"Insufficient balance: need {required}, available {available}"
        )


class OrderPlacementError(GridException):
    """Fehler beim Platzieren einer Order"""
    pass


class OrderCancellationError(GridException):
    """Fehler beim Stornieren einer Order"""
    pass


class PriceOutOfRangeError(GridException):
    """Preis außerhalb des Grid-Bereichs"""
    def __init__(self, price: float, lower: float, upper: float):
        self.price = price
        self.lower = lower
        self.upper = upper
        super().__init__(
            f"Price {price} out of grid range [{lower}, {upper}]"
        )


class InvalidLeverageError(GridException):
    """Ungültiger Hebel"""
    def __init__(self, leverage: int):
        self.leverage = leverage
        super().__init__(f"Invalid leverage: {leverage} (must be 1-125)")


class GridInitializationError(GridException):
    """Fehler beim Initialisieren des Grids"""
    pass


class OrderSyncError(GridException):
    """Fehler beim Order-Sync"""
    pass


class WebSocketConnectionError(GridException):
    """WebSocket-Verbindungsfehler"""
    pass


class APITimeoutError(GridException):
    """API-Request Timeout"""
    pass


class InvalidGridConfigError(ConfigValidationError):
    """Ungültige Grid-Konfiguration"""
    pass
