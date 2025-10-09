import yaml
from pathlib import Path
from typing import Dict, Any
import logging


def merge_configs(base: Dict, override: Dict) -> Dict:
    """
    Merged zwei Configs rekursiv
    override überschreibt base-Werte
    
    Args:
        base: Basis Dictionary
        override: Überschreibende Werte
    
    Returns:
        Gemergtes Dictionary
    """
    result = base.copy()
    
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            # Rekursiv für verschachtelte Dicts
            result[key] = merge_configs(result[key], value)
        else:
            # Überschreibe Wert
            result[key] = value
    
    return result


def load_config(coin_symbol: str) -> Dict[str, Any]:
    """
    Lädt Config mit Vererbung:
    1. base.yaml laden
    2. Coin-spezifische Config laden
    3. Merge beide (Coin überschreibt base)
    
    Args:
        coin_symbol: Symbol der Coin-Config (z.B. "ONDOUSDT")
    
    Returns:
        Finales Config Dictionary
    
    Raises:
        FileNotFoundError: Wenn Config-Datei nicht existiert
        ValueError: Wenn YAML ungültig ist
    """
    # Config Verzeichnis bestimmen
    config_dir = Path(__file__).parent.parent / "configs"
    
    # === Base Config laden ===
    base_path = config_dir / "base.yaml"
    if not base_path.exists():
        raise FileNotFoundError(f"Base Config nicht gefunden: {base_path}")
    
    try:
        with open(base_path, 'r', encoding='utf-8') as f:
            base_config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Ungültige YAML in base.yaml: {e}")
    
    # === Coin Config laden ===
    coin_path = config_dir / f"{coin_symbol}.yaml"
    if not coin_path.exists():
        raise FileNotFoundError(
            f"Config für {coin_symbol} nicht gefunden: {coin_path}\n"
            f"Verfügbare Configs: {list(config_dir.glob('*.yaml'))}"
        )
    
    try:
        with open(coin_path, 'r', encoding='utf-8') as f:
            coin_config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Ungültige YAML in {coin_symbol}.yaml: {e}")
    
    # === Merge: coin überschreibt base ===
    final_config = merge_configs(base_config, coin_config)
    
    # Validierung: Symbol muss in coin config definiert sein
    if 'symbol' not in final_config:
        raise ValueError(f"'symbol' fehlt in {coin_symbol}.yaml Config")
    
    return final_config


def print_config(config: Dict, title: str = "Geladene Config"):
    """
    Gibt Config formatiert aus (für Debugging)
    
    Args:
        config: Config Dictionary
        title: Titel für Ausgabe
    """
    print("\n" + "=" * 60)
    print(f"📋 {title}")
    print("=" * 60)
    
    def print_dict(d, indent=0):
        """Rekursiv Dict ausgeben"""
        for key, value in d.items():
            if isinstance(value, dict):
                print("  " * indent + f"{key}:")
                print_dict(value, indent + 1)
            else:
                print("  " * indent + f"{key}: {value}")
    
    print_dict(config)
    print("=" * 60 + "\n")