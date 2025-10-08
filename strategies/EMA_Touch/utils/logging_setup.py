import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime


def setup_logging(symbol: str, strategy: str = "EMA_Touch", debug: bool = False):
    """
    Richtet Logging ein: Console + Datei
    
    Args:
        symbol: Trading Symbol (z.B. "ONDOUSDT")
        strategy: Strategie-Name
        debug: Debug-Modus (mehr Details)
    """
    # Log Ordner im Strategy-Verzeichnis erstellen
    # Gehe vom aktuellen Script aus zum Strategy Ordner
    strategy_dir = Path(__file__).parent.parent  # Von utils/ zu EMA_Touch/
    log_dir = strategy_dir / "logs"
    log_dir.mkdir(exist_ok=True)
    
    # Dateiname: Strategie_Coin_Datum.log
    date_str = datetime.now().strftime('%Y%m%d')
    log_file = log_dir / f"{strategy}_{symbol}_{date_str}.log"
    
    # Root Logger konfigurieren
    logger = logging.getLogger()
    
    # Level abhängig von DEBUG
    if debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    
    # Alle bestehenden Handler entfernen
    logger.handlers.clear()
    
    # Format für beide Handler (mit Symbol)
    formatter = logging.Formatter(
        #f'%(asctime)s | {symbol} | %(levelname)s | %(message)s'
        f'%(asctime)s | %(message)s'
    )
        
    # Console Handler - nur für wichtige Meldungen (praktisch aus)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.CRITICAL)
    console_handler.setFormatter(formatter)
    
    # File Handler (rotiert bei 10MB, hält 5 Dateien)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10 MB
        backupCount=5,
        encoding='utf-8'
    )
    
    # Level abhängig von DEBUG
    if debug:
        file_handler.setLevel(logging.DEBUG)
    else:
        file_handler.setLevel(logging.INFO)
    
    file_handler.setFormatter(formatter)
    
    # Handler hinzufügen
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    # Start-Meldung
    if debug:
        logging.info(f"🔍 DEBUG MODE - Vollständiges Logging: {log_file}")
    else:
        logging.info(f"📝 Logging eingerichtet: {log_file} (nur Orders + Errors)")