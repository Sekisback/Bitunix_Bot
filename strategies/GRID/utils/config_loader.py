# strategies/GRID/utils/config_loader.py
"""
Config-Loader mit Pydantic-Validierung
"""

import yaml
from pathlib import Path
from typing import Dict, Any
from models.config_models import GridBotConfig
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from utils.error_format import format_validation_error
from utils.exceptions import ConfigValidationError  # ← NEU

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
    """Lädt base.yaml + Coin-Config, validiert, gibt GridBotConfig zurück"""

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

    # === Merge und validieren ===
    merged = merge_configs(base_dict, coin_dict)

    try:
        config = GridBotConfig(**merged)
        # 👉 bei Erfolg keinerlei Ausgabe
        return config

    except Exception as e:
        # 🔴 Nur bei Fehlern: schöne tabellarische Ausgabe
        console.print("\n[red]✗ Fehler in den Configs erkannt[/red]")

        table = Table(
            title="Validierungs-Ergebnisse",
            show_lines=True,
            expand=True,
            header_style="bold cyan",
            title_style="italic dim",
        )
        table.add_column("Config", style="cyan", width=20)
        table.add_column("Status", style="bold", width=10)
        table.add_column("Details", overflow="fold")

        clean_error = format_validation_error(e)

        table.add_row("base.yaml", "✅ OK", "Alle Pflichtfelder valide")
        table.add_row(f"{coin_symbol}.yaml", "❌ FEHLER", clean_error)

        console.print(table)
        console.print(
            Panel(
                "[bold red]✗ Es gibt Fehler in den Configs![/bold red]\n\n"
                "Siehe Tabelle oben für Details. "
                "Korrigiere die Fehler und führe den Validator erneut aus.",
                title="[red]Ergebnis[/red]",
            )
        )
        
        # ← NEU: Werfe ConfigValidationError statt sys.exit
        raise ConfigValidationError(f"Config-Validierung fehlgeschlagen: {e}")


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
    print(f"Hedge: {config.hedge.dict()}")
    print("=" * 60 + "\n")