# strategies/GRID/constants.py
"""
Zentrale Konstanten für Grid Trading Bot
Ersetzt Magic Numbers im Code
"""

# === Toleranzen ===
PRICE_TOLERANCE = 1e-8  # Toleranz für Preisvergleiche (Float-Genauigkeit)

# === WebSocket ===
WS_HEARTBEAT_INTERVAL = 3  # Sekunden zwischen Ping-Messages
WS_RECONNECT_DELAY = 5     # Sekunden Wartezeit nach Disconnect

# === Account Sync ===
BALANCE_SYNC_INTERVAL = 60      # Sekunden zwischen HTTP-Balance-Abfragen
ORDER_CACHE_STALE_SECONDS = 300 # Orders älter als 5min = stale

# === Bot Timing ===
AUTO_SYNC_CHECK_INTERVAL = 600  # 10 Minuten zwischen Auto-OrderSync
MAIN_LOOP_SLEEP_SECONDS = 2     # Standard-Sleep im Bot-Loop
WS_STARTUP_DELAY = 2            # Wartezeit nach WS-Connect vor Subscribe

# === Grid Defaults ===
DEFAULT_GRID_LEVELS = 10
MIN_GRID_LEVELS = 2
MAX_GRID_LEVELS = 100

DEFAULT_REBALANCE_INTERVAL = 300  # 5 Minuten
MIN_REBALANCE_INTERVAL = 60       # 1 Minute
MAX_REBALANCE_INTERVAL = 3600     # 1 Stunde

# === Risk Management ===
DEFAULT_MAKER_FEE = 0.00014  # 0.014%
DEFAULT_TAKER_FEE = 0.00014  # 0.014%
MIN_ORDER_SIZE = 0.0         # Minimale Ordergröße (Exchange-abhängig)

# === Retry & Error Handling ===
MAX_RECONNECT_ATTEMPTS = 5
ERROR_RETRY_INTERVAL = 30    # Sekunden bis Retry nach Fehler

# === Logging ===
LOG_ROTATION_SIZE_MB = 10
LOG_ROTATION_BACKUP_COUNT = 5
