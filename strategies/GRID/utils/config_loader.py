# strategies/GRID/utils/config_loader.py
"""
Config-Loader mit Pydantic-Validierung
"""

import yaml
from pathlib import Path
from typing import Dict, Any
from models.config_models import GridBotConfig


def merge_configs(base: Dict, override: Dict) -> Dict:
    """Merged zwei Configs rekursiv (wie bisher)"""
    result = base.copy()
    
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value
    
    return result


def suggest_fix(error_msg: str) -> str:
    """Schlägt Lösung basierend auf Fehlermeldung vor"""
    fixes = {
        "upper_price": "💡 Setze upper_price > lower_price",
        "grid_levels": "💡 Setze grid_levels zwischen 2 und 100",
        "base_order_size": "💡 base_order_size muss > 0 sein",
        "dry_run": "💡 Nutze true/false ohne Anführungszeichen",
        "leverage": "💡 Hebel muss zwischen 1 und 125 liegen",
        "stop_loss_price": "💡 Bei sl_mode: fixed muss stop_loss_price gesetzt sein",
    }
    
    for keyword, fix in fixes.items():
        if keyword in error_msg.lower():
            return fix
    
    return "💡 Prüfe die Doku: strategies/GRID/docs/config_guide.md"


def load_config(coin_symbol: str) -> GridBotConfig:
    """
    Lädt und validiert Config mit Pydantic
    
    Args:
        coin_symbol: Symbol der Coin (z.B. "ONDOUSDT")
    
    Returns:
        Validiertes GridBotConfig-Objekt
    
    Raises:
        FileNotFoundError: Config-Datei fehlt
        ValueError: Config ungültig
    """
    config_dir = Path(__file__).parent.parent / "configs"
    
    # === 1. Base laden und prüfen ===
    print(f"\n🔍 Prüfe base.yaml...")
    base_path = config_dir / "base.yaml"
    
    if not base_path.exists():
        raise FileNotFoundError(f"Base-Config fehlt: {base_path}")
    
    with open(base_path, 'r', encoding='utf-8') as f:
        base_dict = yaml.safe_load(f)
    
    try:
        # Prüfe ob base alleine valide wäre
        GridBotConfig(**base_dict)
        print(f"✅ base.yaml ist valide")
    except Exception as e:
        print(f"❌ Fehler in base.yaml:")
        print(f"   {e}")
        print(f"   {suggest_fix(str(e))}")
        raise ValueError(f"Base-Config ungültig: {e}")
    
    # === 2. Coin-Config laden ===
    print(f"🔍 Prüfe {coin_symbol}.yaml...")
    coin_path = config_dir / f"{coin_symbol}.yaml"
    
    if not coin_path.exists():
        raise FileNotFoundError(
            f"Coin-Config fehlt: {coin_path}\n"
            f"Verfügbare: {list(config_dir.glob('*.yaml'))}"
        )
    
    with open(coin_path, 'r', encoding='utf-8') as f:
        coin_dict = yaml.safe_load(f)
    
    # === 3. Merge und final validieren ===
    merged = merge_configs(base_dict, coin_dict)
    
    try:
        config = GridBotConfig(**merged)
        
        # Erfolgsmeldung
        print(f"✅ {coin_symbol}.yaml + base.yaml = valide")
        print(f"   📊 Symbol: {config.symbol}")
        print(f"   📈 Grid: {config.grid.lower_price} → {config.grid.upper_price}")
        print(f"   🎚️  Levels: {config.grid.grid_levels}")
        print(f"   🧪 Dry-Run: {config.trading.dry_run}")
        
        return config
        
    except Exception as e:
        print(f"❌ Fehler nach Merge von {coin_symbol}.yaml:")
        print(f"   {e}")
        print(f"   {suggest_fix(str(e))}")
        raise ValueError(f"Config-Validierung fehlgeschlagen: {e}")


def print_config(config: GridBotConfig, title: str = "Geladene Config"):
    """Gibt Config formatiert aus (für Debugging)"""
    print("\n" + "=" * 60)
    print(f"📋 {title}")
    print("=" * 60)
    print(f"Symbol: {config.symbol}")
    print(f"Trading: {config.trading.dict()}")
    print(f"Grid: {config.grid.dict()}")
    print(f"Risk: {config.risk.dict()}")
    print(f"Margin: {config.margin.dict()}")
    print("=" * 60 + "\n")