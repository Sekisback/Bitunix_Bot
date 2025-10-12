# strategies/GRID/utils/config_loader.py
"""
Einfacher Config-Loader ohne automatische Validierung oder rich-Ausgabe.
Lädt base.yaml + Coin-Config, merged sie und gibt GridBotConfig zurück.
"""

import yaml
from pathlib import Path
from typing import Dict, Any
from models.config_models import GridBotConfig
from utils.exceptions import ConfigValidationError


def merge_configs(base: Dict, override: Dict) -> Dict:
    """Merged zwei Configs rekursiv."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value
    return result


def load_config(coin_symbol: str) -> GridBotConfig:
    """Lädt base.yaml + Coin-Config und gibt GridBotConfig zurück (ohne Validator-Ausgabe)."""
    config_dir = Path(__file__).parent.parent / "configs"
    base_path = config_dir / "base.yaml"
    coin_path = config_dir / f"{coin_symbol}.yaml"

    # === Base laden ===
    if not base_path.exists():
        raise ConfigValidationError(f"Base-Config fehlt: {base_path}")

    try:
        with open(base_path, "r", encoding="utf-8") as f:
            base_dict = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigValidationError(f"YAML-Fehler in base.yaml: {e}")

    # === Coin laden ===
    if not coin_path.exists():
        raise ConfigValidationError(
            f"Coin-Config fehlt: {coin_path}\n"
            f"Verfügbare: {list(config_dir.glob('*.yaml'))}"
        )

    try:
        with open(coin_path, "r", encoding="utf-8") as f:
            coin_dict = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigValidationError(f"YAML-Fehler in {coin_symbol}.yaml: {e}")

    # === Merge ===
    merged = merge_configs(base_dict, coin_dict)

    # === In Pydantic-Objekt umwandeln (Validierung durch Pydantic intern)
    try:
        return GridBotConfig(**merged)
    except Exception as e:
        raise ConfigValidationError(f"Ungültige Config: {e}")


def print_config(config: GridBotConfig, title: str = "Geladene Config"):
    """Gibt Config formatiert aus (für Debugging)."""
    print("\n" + "=" * 60)
    print(f"📋 {title}")
    print("=" * 60)
    print(f"Symbol: {config.symbol}")
    print(f"Trading: {config.trading.dict()}")
    print(f"Grid: {config.grid.dict()}")
    print(f"Risk: {config.risk.dict()}")
    print(f"Margin: {config.margin.dict()}")
    print(f"Hedge: {config.hedge.dict()}")
    print("=" * 60 + "\n")
