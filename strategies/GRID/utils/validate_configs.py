# strategies/GRID/utils/validate_configs.py
"""
Standalone Config-Validator
Prüft alle Configs und zeigt Fehler mit Lösungsvorschlägen

Aufruf: python utils/validate_configs.py
"""

from pathlib import Path
import yaml
import sys

# === FIX: Parent-Verzeichnis zum Python-Path hinzufügen ===
GRID_DIR = Path(__file__).parent.parent  # strategies/GRID/
sys.path.insert(0, str(GRID_DIR))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from models.config_models import GridBotConfig
from config_loader import merge_configs, suggest_fix

console = Console()

# strategies/GRID/utils/validate_configs.py

def format_validation_error(error: Exception) -> str:
    """
    Formatiert Pydantic ValidationError kompakt und leserlich
    
    Args:
        error: Pydantic ValidationError oder normale Exception
    
    Returns:
        Kompakte Fehlermeldung ohne URLs
    """
    # Prüfe ob es ein Pydantic ValidationError ist
    try:
        from pydantic_core import ValidationError
        
        if isinstance(error, ValidationError):
            errors = []
            for err in error.errors():
                # Feldpfad (z.B. grid.upper_price)
                field = '.'.join(str(loc) for loc in err['loc'])
                
                # Fehlermeldung aufbereiten
                msg = err['msg']
                
                # Kürze bekannte Meldungen
                if 'greater than 0' in msg.lower():
                    msg = "muss > 0 sein"
                elif 'less than' in msg.lower():
                    msg = msg.replace('Input should be less than', 'muss <')
                elif 'greater than' in msg.lower():
                    msg = msg.replace('Input should be greater than', 'muss >')
                
                errors.append(f"  • {field}: {msg}")
            
            return '\n'.join(errors)
    except ImportError:
        pass
    
    # Fallback für normale Exceptions
    error_str = str(error)
    lines = error_str.split('\n')
    filtered = [
        line for line in lines 
        if not line.strip().startswith('For further information')
        and not line.strip().startswith('https://errors.pydantic')
    ]
    return '\n'.join(filtered).strip()


def validate_all_configs():
    """Prüft alle Config-Dateien"""
    
    console.rule("[bold cyan]🔍 Grid Bot Config Validator[/bold cyan]")
    config_dir = GRID_DIR / "configs"
    
    table = Table(title="Validierungs-Ergebnisse", show_lines=True)
    table.add_column("Config", style="cyan", width=20)
    table.add_column("Status", style="bold", width=10)
    table.add_column("Details", width=50)
    
    all_valid = True
    
    # === 1. Base Config ===
    console.print("\n[yellow]► Prüfe base.yaml...[/yellow]")
    base_path = config_dir / "base.yaml"
    
    try:
        with open(base_path, encoding='utf-8') as f:
            base_dict = yaml.safe_load(f)
        
        GridBotConfig(**base_dict)
        table.add_row("base.yaml", "✅ OK", "Alle Pflichtfelder valide")
        console.print("[green]✓ base.yaml ist valide[/green]")
        
    except Exception as e:
        all_valid = False
        clean_error = format_validation_error(e)
        suggestion = suggest_fix(str(e))
        error_text = f"{clean_error}\n\n{suggestion}"
        table.add_row("base.yaml", "❌ FEHLER", error_text)
        console.print(f"[red]✗ base.yaml hat Fehler[/red]")
    
    # === 2. Coin-Configs ===
    console.print("\n[yellow]► Prüfe Coin-Configs...[/yellow]")
    
    coin_files = sorted(config_dir.glob("*.yaml"))
    coin_files = [f for f in coin_files if f.name != "base.yaml"]
    
    if not coin_files:
        console.print("[yellow]⚠ Keine Coin-Configs gefunden[/yellow]")
    
    for coin_path in coin_files:
        try:
            with open(base_path, encoding='utf-8') as f:
                base_dict = yaml.safe_load(f)
            with open(coin_path, encoding='utf-8') as f:
                coin_dict = yaml.safe_load(f)
            
            merged = merge_configs(base_dict, coin_dict)
            config = GridBotConfig(**merged)
            
            table.add_row(
                coin_path.name,
                "✅ OK",
                f"Symbol: {config.symbol}, "
                f"Grid: {config.grid.grid_levels} levels, "
                f"Dry: {config.trading.dry_run}"
            )
            console.print(f"[green]✓ {coin_path.name} ist valide[/green]")
            
        except Exception as e:
            all_valid = False
            clean_error = format_validation_error(e)
            suggestion = suggest_fix(str(e))
            error_text = f"{clean_error}\n\n{suggestion}"
            table.add_row(coin_path.name, "❌ FEHLER", error_text)
            console.print(f"[red]✗ {coin_path.name} hat Fehler[/red]")
    
    # Ausgabe wie vorher...
    console.print("\n")
    console.print(table)
    console.print("\n")
    
    if all_valid:
        console.print(Panel(
            "✅ [bold green]Alle Configs sind valide und einsatzbereit![/bold green]",
            title="Ergebnis",
            border_style="green"
        ))
        return True
    else:
        console.print(Panel(
            "❌ [bold red]Es gibt Fehler in den Configs![/bold red]\n\n"
            "Siehe Tabelle oben für Details und Lösungsvorschläge.\n"
            "Korrigiere die Fehler und führe den Validator erneut aus.",
            title="Ergebnis",
            border_style="red"
        ))
        return False
    
    
if __name__ == "__main__":
    # Wechsle ins GRID-Verzeichnis
    script_dir = Path(__file__).parent.parent
    import os
    os.chdir(script_dir)
    
    # Validiere alle Configs
    success = validate_all_configs()
    
    # Exit-Code für CI/CD
    sys.exit(0 if success else 1)