import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime


def setup_logging(symbol: str, strategy: str = "GRID", debug: bool = False):
    """
    Richtet das Logging für die GRID-Strategie ein (Konsole + Datei)

    Args:
        symbol: Trading Symbol (z. B. "ONDOUSDT")
        strategy: Strategie-Name (Standard: GRID)
        debug: Wenn True, wird DEBUG-Logging aktiviert
    """

    # === 1️⃣ Log-Verzeichnis vorbereiten ===
    # Von dieser Datei ausgehend -> strategies/GRID/utils/logging_setup.py
    strategy_dir = Path(__file__).parent.parent  # geht von utils → GRID/
    log_dir = strategy_dir / "logs" / symbol
    log_dir.mkdir(parents=True, exist_ok=True)

    # === 2️⃣ Logdatei nach Datum anlegen ===
    date_str = datetime.now().strftime("%Y%m%d")
    log_file = log_dir / f"{strategy}_{symbol}_{date_str}.log"

    # === 3️⃣ Root-Logger holen ===
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG if debug else logging.INFO)

    # Alte Handler entfernen, um doppelte Logs zu vermeiden
    logger.handlers.clear()

    # === 4️⃣ Format definieren ===
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # === 5️⃣ File Handler (rotiert bei 10 MB, behält 5 Backups) ===
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.addHandler(file_handler)

    # === 6️⃣ Console Handler (nur Warnungen + Infos, oder Debug falls aktiv) ===
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.addHandler(console_handler)

    # === 7️⃣ Startmeldung ===
    logging.info("=" * 80)
    logging.info(f"📝 Logging initialisiert für {strategy} ({symbol})")
    logging.info(f"📁 Log-Datei: {log_file}")
    logging.info(f"🔧 Modus: {'DEBUG' if debug else 'INFO'}")
    logging.info("=" * 80)

    return logger
