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
from utils.config_loader import merge_configs
from utils.error_format import format_validation_error

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
                
                # 💄 Präfix nur, wenn Feld vorhanden
                if field:
                    errors.append(f"❌ {field}: {msg}")
                else:
                    errors.append(f"❌ {msg}")
            
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
    
    table = Table(title="Validierungs-Ergebnisse", show_lines=True, expand=True)
    table.add_column("Config", style="cyan", width=10)
    table.add_column("Status", style="bold", width=10)
    table.add_column("Details", overflow="fold")
    
    all_valid = True
    
    # === 1. Base Config ===
    console.print("\n[yellow]► Prüfe base.yaml...[/yellow]")
    base_path = config_dir / "base.yaml"
    
    try:
        with open(base_path, encoding='utf-8') as f:
            base_dict = yaml.safe_load(f)

        cfg = GridBotConfig(**base_dict)

        # === Hedge-Validierung nur wenn Parsing erfolgreich ===
        hedge_issues = validate_hedge_config(cfg)
        if hedge_issues:
            all_valid = False
            detail = "\n".join(f"❌ {x}" for x in hedge_issues)
            table.add_row("base.yaml", "⚠ WARNUNG", f"Hedge: {detail}")
            console.print("[yellow]⚠ Hedge-Parameter prüfen in base.yaml[/yellow]")
        else:
            table.add_row("base.yaml", "✅ OK", "Alle Pflichtfelder valide")
            console.print("[green]✓ base.yaml ist valide[/green]")

    except Exception as e:
        all_valid = False
        clean_error = format_validation_error(e)
        table.add_row("base.yaml", "❌ FEHLER", clean_error)
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

            # === Hedge-Validierung ===
            hedge_issues = validate_hedge_config(config)
            if hedge_issues:
                all_valid = False
                detail = "\n".join(f"❌ {x}" for x in hedge_issues)
                table.add_row(coin_path.name, "⚠ WARNUNG", f"Hedge: {detail}")
                console.print(f"[yellow]⚠ Hedge-Parameter prüfen in {coin_path.name}[/yellow]")
            else:
                table.add_row(
                    coin_path.name,
                    "✅ OK",
                    f"Symbol: {config.symbol}, Grid: {config.grid.grid_levels} levels, Dry: {config.trading.dry_run}"
                )
                console.print(f"[green]✓ {coin_path.name} ist valide[/green]")

        except Exception as e:
            all_valid = False
            clean_error = format_validation_error(e)
            table.add_row(coin_path.name, "❌ FEHLER", clean_error)
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
            "Siehe Tabelle oben für Details. "
            "Korrigiere die Fehler und führe den Validator erneut aus.",
            title="Ergebnis",
            border_style="red"
        ))
        return False

def validate_hedge_config(cfg):
    """Führt logische Prüfungen für den Hedge-Abschnitt durch"""
    issues = []

    if not cfg.hedge.enabled:
        return issues  # nichts zu prüfen, Hedge deaktiviert

    # 1️⃣ Mode-abhängige Regeln
    if cfg.hedge.mode == "dynamic" and not cfg.hedge.partial_levels:
        issues.append("Bei mode='dynamic' müssen 'partial_levels' gesetzt sein.")
    if cfg.hedge.mode not in ("direct", "dynamic", "reversal"):
        issues.append(f"Ungültiger Hedge-Mode: {cfg.hedge.mode}")

    # 2️⃣ Trigger-Offset muss sinnvoll sein
    if cfg.hedge.trigger_offset <= 0:
        issues.append("trigger_offset muss > 0 sein (z. B. 1.0).")

    # 3️⃣ Größe / Ratio
    if cfg.hedge.size_mode == "fixed":
        if not (0 < cfg.hedge.fixed_size_ratio <= 1):
            issues.append("Bei size_mode='fixed' muss fixed_size_ratio zwischen 0 und 1 liegen.")
    elif cfg.hedge.size_mode != "net_position":
        issues.append(f"Ungültiger size_mode: {cfg.hedge.size_mode}")

    # 4️⃣ partial_levels logisch prüfen
    if cfg.hedge.mode == "dynamic":
        invalid = [x for x in cfg.hedge.partial_levels if not (0 < x <= 1)]
        if invalid:
            issues.append(f"partial_levels enthalten ungültige Werte: {invalid} (muss 0–1).")

    # 5️⃣ close_on_reentry ist bool – kein Fehler nötig, aber Hinweis
    if not isinstance(cfg.hedge.close_on_reentry, bool):
        issues.append("close_on_reentry muss bool sein (true/false).")

    return issues

    
if __name__ == "__main__":
    # Wechsle ins GRID-Verzeichnis
    script_dir = Path(__file__).parent.parent
    import os
    os.chdir(script_dir)
    
    # Validiere alle Configs
    success = validate_all_configs()
    
    # Exit-Code für CI/CD
    sys.exit(0 if success else 1)