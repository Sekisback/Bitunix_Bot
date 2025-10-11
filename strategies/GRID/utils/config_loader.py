# strategies/GRID/utils/config_loader.py
"""
Config-Loader mit Pydantic-Validierung
"""

import yaml
from pathlib import Path
from typing import Dict, Any
from models.config_models import GridBotConfig
from rich.console import Console
from utils.error_format import format_validation_error

console = Console()

def merge_configs(base: Dict, override: Dict) -> Dict:
    """Merged zwei Configs rekursiv (wie bisher)"""
    result = base.copy()
    
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value
    
    return result


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
    console.print(f"\n[cyan]🔍 Prüfe base.yaml...[/cyan]")
    base_path = config_dir / "base.yaml"

    if not base_path.exists():
        raise FileNotFoundError(f"Base-Config fehlt: {base_path}")

    with open(base_path, 'r', encoding='utf-8') as f:
        base_dict = yaml.safe_load(f)

    try:
        GridBotConfig(**base_dict)
        console.print("[green]✅ base.yaml ist valide[/green]")
    except Exception as e:
        console.print("[red]❌ Fehler in base.yaml:[/red]")
        console.print(format_validation_error(e))
        raise ValueError(f"Base-Config ungültig: {e}")

    # === 2. Coin-Config laden ===
    console.print(f"\n[cyan]🔍 Prüfe {coin_symbol}.yaml...[/cyan]")
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
        console.print(f"[green]✅ {coin_symbol}.yaml + base.yaml = valide[/green]")
        console.print(f"   📊 Symbol: {config.symbol}")
        console.print(f"   📈 Grid: {config.grid.lower_price} → {config.grid.upper_price}")
        console.print(f"   🎚️ Levels: {config.grid.grid_levels}")
        console.print(f"   🧪 Dry-Run: {config.trading.dry_run}")
        return config

    except Exception as e:
        console.print(f"[red]❌ Fehler nach Merge von {coin_symbol}.yaml:[/red]")
        console.print(format_validation_error(e))
        # 🚫 Kein weiterer Raise → verhindert hässlichen Traceback
        import sys
        sys.exit(1)



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