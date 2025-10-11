#!/usr/bin/env python3
# strategies/GRID/debug_risk_summary.py
"""
Quick-Test: Prüft ob RiskManager korrekt initialisiert wird
"""

import sys
from pathlib import Path

GRID_DIR = Path(__file__).parent
sys.path.insert(0, str(GRID_DIR))

from utils.config_loader import load_config
from manager.grid_calculator import GridCalculator
from manager.risk_manager import RiskManager
from rich.console import Console
from rich.panel import Panel

console = Console()

def test_risk_manager_init():
    """Test: RiskManager-Initialisierung"""
    console.print(Panel.fit(
        "[bold cyan]🔍 RiskManager Debug[/bold cyan]",
        border_style="cyan"
    ))
    
    try:
        # Config laden
        console.print("[yellow]1. Lade Config...[/yellow]")
        config = load_config("ONDOUSDT")
        console.print("[green]✅ Config geladen[/green]")
        
        # GridCalculator
        console.print("\n[yellow]2. Initialisiere GridCalculator...[/yellow]")
        calc = GridCalculator(config.grid)
        console.print(f"[green]✅ GridCalculator OK[/green]")
        
        # RiskManager
        console.print("\n[yellow]3. Initialisiere RiskManager...[/yellow]")
        risk = RiskManager(config.grid, config.risk, calc)
        console.print("[green]✅ RiskManager OK[/green]")
        
        # Risk-Summary abrufen
        console.print("\n[yellow]4. Hole Risk-Summary...[/yellow]")
        summary = risk.get_risk_summary()
        
        console.print("\n[bold]📋 Risk-Summary:[/bold]")
        for key, value in summary.items():
            if value is not None:
                console.print(f"  {key}: {value}")
        
        # Fee-Info abrufen
        console.print("\n[yellow]5. Hole Fee-Info...[/yellow]")
        fee_info = risk.get_fee_info()
        
        console.print("\n[bold]💰 Fee-Info:[/bold]")
        for key, value in fee_info.items():
            console.print(f"  {key}: {value}")
        
        # Test-Berechnung
        console.print("\n[yellow]6. Test-Berechnung...[/yellow]")
        size = risk.calculate_effective_size()
        tp = risk.calculate_take_profit(1.095, 1, "SELL")
        sl = risk.calculate_stop_loss(1.095, "SELL")
        
        console.print(f"  Effective Size: {size}")
        console.print(f"  TP @ 1.095:     {tp}")
        console.print(f"  SL @ 1.095:     {sl}")
        
        console.print(Panel(
            "[bold green]✅ Alle Checks OK!\n\n"
            "RiskManager funktioniert korrekt.\n"
            "Falls Log-Summary fehlt → grid_manager.py erneut kopieren.[/bold green]",
            border_style="green"
        ))
        
    except Exception as e:
        console.print(Panel(
            f"[bold red]❌ Fehler: {e}[/bold red]",
            border_style="red"
        ))
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    test_risk_manager_init()
