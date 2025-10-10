#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bitunix GRID Bot – Automatisiertes Config-Testskript
----------------------------------------------------
Testet alle konfigurierbaren Parameter aus base.yaml und Coin-Configs.
Zeigt in der CLI erwartete Ergebnisse, tatsächliches Verhalten und
fordert nach jedem Testabschnitt manuell zum Fortfahren auf.
"""

import yaml
import math
import time
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

# ✅ KORREKTER IMPORT (wir sind bereits in strategies/GRID/)
from manager.grid_manager import GridManager

console = Console()

# =============================================================================
# MockClient (Exchange-Simulation)
# =============================================================================
class MockClient:
    def place_order(self, **kwargs):
        console.print(f"[yellow]→ Mock place_order()[/yellow] {kwargs}")
        return "mock_id"

    def cancel_all(self, symbol):
        console.print(f"[yellow]→ Mock cancel_all() für {symbol}[/yellow]")
        return True


# =============================================================================
# Hilfsfunktionen
# =============================================================================
def load_yaml(path: Path):
    """YAML laden mit Fehlermeldung, falls Datei fehlt."""
    if not path.exists():
        console.print(f"[bold red]❌ Config-Datei nicht gefunden:[/bold red] {path}")
        raise SystemExit(1)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def pause_step(message="Weiter mit [Enter] ..."):
    input(f"\n{message}")

def section(title):
    console.rule(f"[bold cyan]{title}[/bold cyan]")

def merge_configs(base, coin):
    """Rekursive Zusammenführung (base + coin)"""
    merged = base.copy()
    for k, v in coin.items():
        if isinstance(v, dict) and k in merged:
            merged[k].update(v)
        else:
            merged[k] = v
    return merged


# =============================================================================
# Tests
# =============================================================================
def test_config_structure(cfg):
    section("Config Struktur & Pflichtfelder")
    required_sections = ["system", "grid", "risk", "margin", "trading"]

    missing = [s for s in required_sections if s not in cfg]
    if missing:
        console.print(f"[bold red]Fehlende Sektionen: {missing}[/bold red]")
    else:
        console.print("[bold green]Alle Pflichtsektionen vorhanden.[/bold green]")

    lp, up = cfg["grid"]["lower_price"], cfg["grid"]["upper_price"]
    if up <= lp:
        console.print(f"[bold red]Fehler:[/bold red] upper_price <= lower_price ({up} ≤ {lp})")
    else:
        console.print(f"[green]OK:[/green] Preisbereich {lp} → {up}")

    gl = cfg["grid"]["grid_levels"]
    if gl < 2:
        console.print("[bold red]grid_levels muss >= 2 sein![/bold red]")
    else:
        console.print(f"[green]OK:[/green] grid_levels = {gl}")

    pause_step()


def test_price_grid(cfg):
    section("Preisraster & Grid-Modus (arithmetisch vs. geometrisch)")

    # Backup der Originalwerte
    original_mode = cfg["grid"]["grid_mode"]

    # Test 1: Arithmetic
    cfg["grid"]["grid_mode"] = "arithmetic"
    gm_arith = GridManager(MockClient(), cfg)
    prices_arith = gm_arith._price_list

    # Test 2: Geometric
    cfg["grid"]["grid_mode"] = "geometric"
    gm_geo = GridManager(MockClient(), cfg)
    prices_geo = gm_geo._price_list

    # Ausgabe beider Preisraster im Vergleich
    table = Table(title="Preisraster Vergleich", box=box.SIMPLE_HEAVY)
    table.add_column("#")
    table.add_column("Arithmetic")
    table.add_column("Geometric")

    for i in range(min(len(prices_arith), len(prices_geo))):
        table.add_row(str(i), str(prices_arith[i]), str(prices_geo[i]))

    console.print(table)

    # Prüfung min_price_step
    tick = cfg["grid"]["min_price_step"]
    console.print(f"[blue]min_price_step:[/blue] {tick}")

    # Test auf Rundungsgenauigkeit
    diffs = [round((prices_arith[i+1] - prices_arith[i]) / tick, 6)
             for i in range(len(prices_arith) - 1)]
    step_consistent = all(abs(d - round(d)) < 1e-6 for d in diffs)

    if step_consistent:
        console.print("[green]OK:[/green] Preisabstände entsprechen min_price_step (arithmetisch).")
    else:
        console.print("[yellow]WARNUNG:[/yellow] Rundungsabweichungen erkannt (prüfe Tick-Größe).")

    console.print("[green]Erwartet:[/green] Arithmetic = lineare Schritte, Geometric = exponentiell wachsend.")
    console.print(f"[blue]Grid Levels:[/blue] {cfg['grid']['grid_levels']}")

    # Restore original mode
    cfg["grid"]["grid_mode"] = original_mode

    pause_step()


def test_fee_handling(cfg):
    section("Gebühren & effektive Ordergröße")
    gm = GridManager(MockClient(), cfg)
    base_size = cfg["grid"]["base_order_size"]
    effective = gm._effective_order_size()

    console.print("[green]Erwartetes Verhalten:[/green]")
    if cfg["risk"]["include_fees"]:
        console.print("- Effektive Größe < Basisgröße (Gebühren berücksichtigt)")
    else:
        console.print("- Effektive Größe = Basisgröße (Gebühren ignoriert)")

    table = Table(title="Fee-Handling", box=box.MINIMAL_DOUBLE_HEAD)
    table.add_column("Parameter")
    table.add_column("Wert")

    table.add_row("include_fees", str(cfg["risk"]["include_fees"]))
    table.add_row("fee_side", cfg["risk"]["fee_side"])
    table.add_row("Base Size", str(base_size))
    table.add_row("Effektiv", str(effective))
    table.add_row("Differenz", f"{round(base_size - effective, 8)}")

    console.print(table)
    pause_step()


def test_tp_sl_modes(cfg):
    section("TP- und SL-Logik (alle Modi)")
    gm = GridManager(MockClient(), cfg)
    entry = (cfg["grid"]["lower_price"] + cfg["grid"]["upper_price"]) / 2

    modes = [
        ("percent", "percent"),
        ("next_grid", "percent"),
        ("percent", "fixed"),
        ("percent", "none"),
    ]

    table = Table(title="TP/SL Testmatrix", box=box.SIMPLE)
    table.add_column("tp_mode")
    table.add_column("sl_mode")
    table.add_column("TP")
    table.add_column("SL")

    for tp_mode, sl_mode in modes:
        gm.grid_conf["tp_mode"] = tp_mode
        gm.grid_conf["sl_mode"] = sl_mode
        tp = gm._take_profit_for(entry, 0)
        sl = gm._stop_loss_for(entry)
        table.add_row(tp_mode, sl_mode, str(tp), str(sl))

    console.print(table)
    console.print("[green]Erwartet:[/green] TP/SL werden nach Modus korrekt berechnet.")
    pause_step()


def test_dry_run(cfg):
    section("Dry-Run Orderplatzierung")
    cfg["trading"]["dry_run"] = True
    gm = GridManager(MockClient(), cfg)
    mid = gm.levels[len(gm.levels)//2]
    gm._place_entry(mid)
    console.print(f"[blue]Erwartet:[/blue] [SIM] Logmeldung, Order aktiv aber keine echte Order-ID.")
    console.print(f"[green]Status:[/green] active={mid.active}, order_id={mid.order_id}")
    pause_step()


def test_margin_settings(cfg):
    section("Margin & Leverage Prüfung")
    mode = cfg["margin"]["mode"]
    lev = cfg["margin"]["leverage"]
    console.print(f"[green]Erwartet:[/green] Margin-Mode '{mode}', Leverage={lev}")
    if lev < 1:
        console.print("[red]❌ Fehler: Leverage < 1[/red]")
    else:
        console.print("[green]OK: Hebel gültig[/green]")
    if mode not in ("isolated", "cross"):
        console.print("[red]❌ Fehler: Ungültiger Margin-Mode[/red]")
    else:
        console.print("[green]OK: Margin-Mode gültig[/green]")
    pause_step()


def test_rebalance(cfg):
    section("Rebalancing-Test")
    gm = GridManager(MockClient(), cfg)
    old_levels = [l.price for l in gm.levels]
    gm.grid_conf["rebalance_interval"] = 0  # sofort erzwingen
    time.sleep(1)
    gm._maybe_rebalance()
    new_levels = [l.price for l in gm.levels]
    console.print("[green]Erwartet:[/green] Preisraster wird neu erstellt (Rebalance aktiv).")
    if old_levels != new_levels:
        console.print("[bold green]OK – Rebalance erfolgreich ausgelöst[/bold green]")
    else:
        console.print("[bold yellow]WARNUNG – kein Unterschied erkannt[/bold yellow]")
    pause_step()


# =============================================================================
# Main
# =============================================================================
def main():
    cfg_dir = Path(__file__).parent / "configs"
    base_cfg = load_yaml(cfg_dir / "base.yaml")
    coin_cfg = load_yaml(cfg_dir / "ONDOUSDT.yaml")
    cfg = merge_configs(base_cfg, coin_cfg)

    console.print(Panel.fit("🤖 [bold magenta]Bitunix GRID Bot – Vollständiger Config-Test[/bold magenta]", width=70))
    console.print(f"Symbol: [yellow]{cfg['symbol']}[/yellow]\n")

    test_config_structure(cfg)
    test_price_grid(cfg)
    test_fee_handling(cfg)
    test_tp_sl_modes(cfg)
    test_dry_run(cfg)
    test_margin_settings(cfg)
    test_rebalance(cfg)

    console.rule("[bold green]✅ Alle Tests abgeschlossen![/bold green]")
    console.print("Vergleiche nun die CLI-Ausgabe mit deinem Logfile, um Abweichungen zu erkennen.\n")


if __name__ == "__main__":
    main()

