import logging
import logging.config
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime
import yaml


def setup_logging(symbol: str, strategy: str = "GRID", debug: bool = False):
    """
    Richtet hierarchisches Logging ein
    
    Args:
        symbol: Trading Symbol
        strategy: Strategie-Name
        debug: Debug-Modus aktivieren
    """
    strategy_dir = Path(__file__).parent.parent
    log_dir = strategy_dir / "logs" / symbol
    log_dir.mkdir(parents=True, exist_ok=True)

    # Versuche logging_config.yaml zu laden
    config_file = strategy_dir / "utils" / "logging_config.yaml"
    
    if config_file.exists():
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
            
            # Passe Log-Datei an
            date_str = datetime.now().strftime("%Y%m%d")
            log_file = log_dir / f"{strategy}_{symbol}_{date_str}.log"
            
            if 'handlers' in config and 'file' in config['handlers']:
                config['handlers']['file']['filename'] = str(log_file)
            
            # Debug-Modus: Setze alle Logger auf DEBUG
            if debug:
                for logger_name in config.get('loggers', {}).keys():
                    config['loggers'][logger_name]['level'] = 'DEBUG'
                config['root']['level'] = 'DEBUG'
                if 'handlers' in config and 'console' in config['handlers']:
                    config['handlers']['console']['level'] = 'DEBUG'
            
            # Konfiguration anwenden
            logging.config.dictConfig(config)
            
            logging.info("=" * 80)
            logging.info(f"📝 Hierarchisches Logging initialisiert für {strategy} ({symbol})")
            logging.info(f"📁 Log-Datei: {log_file}")
            logging.info(f"🔧 Modus: {'DEBUG' if debug else 'INFO'}")
            logging.info("=" * 80)
            
            return logging.getLogger()
            
        except Exception as e:
            print(f"⚠️ Fehler beim Laden von logging_config.yaml: {e}")
            print("Fallback auf Standard-Logging...")
    
    # Fallback: Standard-Logging wie vorher
    date_str = datetime.now().strftime("%Y%m%d")
    log_file = log_dir / f"{strategy}_{symbol}_{date_str}.log"
    
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.handlers.clear()
    
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.addHandler(file_handler)
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.addHandler(console_handler)
    
    logging.info("=" * 80)
    logging.info(f"📝 Standard-Logging initialisiert für {strategy} ({symbol})")
    logging.info(f"📁 Log-Datei: {log_file}")
    logging.info(f"🔧 Modus: {'DEBUG' if debug else 'INFO'}")
    logging.info("=" * 80)
    
    return logger
