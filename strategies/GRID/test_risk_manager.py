#!/usr/bin/env python3
# strategies/GRID/test_risk_manager.py
"""
Test-Skript für RiskManager (Paket 4b)
Prüft Fee/TP/SL-Berechnungen
"""

import sys
from pathlib import Path

GRID_DIR = Path(__file__).parent
sys.path.insert(0, str(GRID_DIR))

from manager.risk_manager import RiskManager
from manager.grid_calculator import GridCalculator
from models.config_models import (
    GridConfig, RiskConfig, GridMode, TPMode, SLMode
)
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


def test_fee_calculation():
    """Test: Fee-Berechnung"""
    console.print("\n[cyan]Test 1: Fee-Berechnung[/cyan]")
    
    grid_config = GridConfig(
        upper_price=2.0,
        lower_price=1.0,
        grid_levels=10,
        grid_mode=GridMode.ARITHMETIC,
        min_price_step=0.01,
        base_order_size=100.0
    )
    
    risk_config = RiskConfig(
        include_fees=True,
        fee_side="taker",
        taker_fee_pct=0.0006  # 0.06%
    )
    
    calc = GridCalculator(grid_config)
    risk = RiskManager(grid_config, risk_config, calc)
    
    # === Test mit Fees ===
    effective = risk.calculate_effective_size()
    
    # Erwartung: 100 - (100 * 0.0006 * 2) = 100 - 0.12 = 99.88
    expected = 100.0 * (1.0 - 0.0006 * 2)
    
    assert abs(effective - expected) < 0.01, f"Erwarte {expected}, habe {effective}"
    
    console.print(f"[green]✅ Fee-Berechnung korrekt[/green]")
    console.print(f"  Base: 100.0 → Effective: {effective:.4f}")
    
    # === Test ohne Fees ===
    risk_config.include_fees = False
    risk2 = RiskManager(grid_config, risk_config, calc)
    effective2 = risk2.calculate_effective_size()
    
    assert effective2 == 100.0, f"Ohne Fees sollte 100.0 sein, ist {effective2}"
    console.print(f"  Ohne Fees: {effective2:.4f}")


def test_tp_percent_mode():
    """Test: TP mit Percent-Mode"""
    console.print("\n[cyan]Test 2: Take-Profit (Percent)[/cyan]")
    
    grid_config = GridConfig(
        upper_price=2.0,
        lower_price=1.0,
        grid_levels=10,
        grid_mode=GridMode.ARITHMETIC,
        min_price_step=0.01,
        base_order_size=100.0,
        tp_mode=TPMode.PERCENT,
        take_profit_pct=0.01  # 1%
    )
    
    risk_config = RiskConfig()
    calc = GridCalculator(grid_config)
    risk = RiskManager(grid_config, risk_config, calc)
    
    # === BUY: TP oberhalb ===
    entry_buy = 1.50
    tp_buy = risk.calculate_take_profit(entry_buy, 5, "BUY")
    expected_buy = entry_buy * 1.01
    
    assert abs(tp_buy - expected_buy) < 0.01
    console.print(f"[green]✅ BUY TP korrekt:[/green] {entry_buy} → {tp_buy} (+1%)")
    
    # === SELL: TP unterhalb ===
    entry_sell = 1.50
    tp_sell = risk.calculate_take_profit(entry_sell, 5, "SELL")
    expected_sell = entry_sell * 0.99
    
    assert abs(tp_sell - expected_sell) < 0.01
    console.print(f"[green]✅ SELL TP korrekt:[/green] {entry_sell} → {tp_sell} (-1%)")


def test_tp_next_grid_mode():
    """Test: TP mit Next-Grid-Mode"""
    console.print("\n[cyan]Test 3: Take-Profit (Next Grid)[/cyan]")
    
    grid_config = GridConfig(
        upper_price=2.0,
        lower_price=1.0,
        grid_levels=5,
        grid_mode=GridMode.ARITHMETIC,
        min_price_step=0.01,
        base_order_size=100.0,
        tp_mode=TPMode.NEXT_GRID
    )
    
    risk_config = RiskConfig()
    calc = GridCalculator(grid_config)
    risk = RiskManager(grid_config, risk_config, calc)
    
    price_list = calc.calculate_price_list()
    
    table = Table(title="Next-Grid TP")
    table.add_column("#", style="cyan")
    table.add_column("Entry", style="yellow")
    table.add_column("Side", style="magenta")
    table.add_column("TP", style="green")
    table.add_column("Status", style="bold")
    
    # Test Level 2 (Mitte)
    level = 2
    entry = price_list[level]
    
    # BUY → TP = Level 3
    tp_buy = risk.calculate_take_profit(entry, level, "BUY", price_list)
    expected_buy = price_list[level + 1]
    ok_buy = abs(tp_buy - expected_buy) < 0.01
    
    table.add_row(
        str(level), f"{entry:.2f}", "BUY", f"{tp_buy:.2f}",
        "✅" if ok_buy else "❌"
    )
    
    # SELL → TP = Level 1
    tp_sell = risk.calculate_take_profit(entry, level, "SELL", price_list)
    expected_sell = price_list[level - 1]
    ok_sell = abs(tp_sell - expected_sell) < 0.01
    
    table.add_row(
        str(level), f"{entry:.2f}", "SELL", f"{tp_sell:.2f}",
        "✅" if ok_sell else "❌"
    )
    
    console.print(table)
    
    if ok_buy and ok_sell:
        console.print("[green]✅ Next-Grid TP korrekt[/green]")
    else:
        console.print("[red]❌ Next-Grid TP fehlerhaft[/red]")


def test_sl_percent_mode():
    """Test: SL mit Percent-Mode"""
    console.print("\n[cyan]Test 4: Stop-Loss (Percent)[/cyan]")
    
    grid_config = GridConfig(
        upper_price=2.0,
        lower_price=1.0,
        grid_levels=10,
        grid_mode=GridMode.ARITHMETIC,
        min_price_step=0.01,
        base_order_size=100.0,
        sl_mode=SLMode.PERCENT,
        stop_loss_pct=0.02  # 2%
    )
    
    risk_config = RiskConfig()
    calc = GridCalculator(grid_config)
    risk = RiskManager(grid_config, risk_config, calc)
    
    entry = 1.50
    
    # === BUY: SL unterhalb ===
    sl_buy = risk.calculate_stop_loss(entry, "BUY")
    expected_buy = entry * 0.98
    
    assert abs(sl_buy - expected_buy) < 0.01
    console.print(f"[green]✅ BUY SL korrekt:[/green] {entry} → {sl_buy} (-2%)")
    
    # === SELL: SL oberhalb ===
    sl_sell = risk.calculate_stop_loss(entry, "SELL")
    expected_sell = entry * 1.02
    
    assert abs(sl_sell - expected_sell) < 0.01
    console.print(f"[green]✅ SELL SL korrekt:[/green] {entry} → {sl_sell} (+2%)")


def test_sl_fixed_mode():
    """Test: SL mit Fixed-Mode"""
    console.print("\n[cyan]Test 5: Stop-Loss (Fixed)[/cyan]")
    
    grid_config = GridConfig(
        upper_price=2.0,
        lower_price=1.0,
        grid_levels=10,
        grid_mode=GridMode.ARITHMETIC,
        min_price_step=0.01,
        base_order_size=100.0,
        sl_mode=SLMode.FIXED,
        stop_loss_price=0.90
    )
    
    risk_config = RiskConfig()
    calc = GridCalculator(grid_config)
    risk = RiskManager(grid_config, risk_config, calc)
    
    entry = 1.50
    sl = risk.calculate_stop_loss(entry, "BUY")
    
    assert sl == 0.90
    console.print(f"[green]✅ Fixed SL korrekt:[/green] {entry} → {sl}")


def test_tp_sl_validation():
    """Test: TP/SL Validierung"""
    console.print("\n[cyan]Test 6: TP/SL Validierung[/cyan]")
    
    grid_config = GridConfig(
        upper_price=2.0,
        lower_price=1.0,
        grid_levels=10,
        grid_mode=GridMode.ARITHMETIC,
        min_price_step=0.01,
        base_order_size=100.0
    )
    
    risk_config = RiskConfig()
    calc = GridCalculator(grid_config)
    risk = RiskManager(grid_config, risk_config, calc)
    
    table = Table(title="TP/SL Validierung")
    table.add_column("Side", style="cyan")
    table.add_column("Entry", style="yellow")
    table.add_column("TP", style="green")
    table.add_column("SL", style="red")
    table.add_column("Expected", style="dim")
    table.add_column("Result", style="bold")
    
    test_cases = [
        # (side, entry, tp, sl, should_be_valid)
        ("BUY", 1.50, 1.60, 1.40, True),   # ✅ TP > entry > SL
        ("BUY", 1.50, 1.40, 1.60, False),  # ❌ TP < entry (falsch!)
        ("BUY", 1.50, 1.60, 1.60, False),  # ❌ SL == entry (falsch!)
        ("SELL", 1.50, 1.40, 1.60, True),  # ✅ SL > entry > TP
        ("SELL", 1.50, 1.60, 1.40, False), # ❌ TP > entry (falsch!)
        ("SELL", 1.50, 1.40, 1.40, False), # ❌ SL == entry (falsch!)
    ]
    
    all_ok = True
    for side, entry, tp, sl, expected in test_cases:
        actual = risk.validate_tp_sl(entry, tp, sl, side)
        ok = actual == expected
        all_ok = all_ok and ok
        
        expected_str = "Valid" if expected else "Invalid"
        result_str = "✅ OK" if ok else f"❌ FAIL (got {actual})"
        
        table.add_row(
            side, f"{entry:.2f}", f"{tp:.2f}", f"{sl:.2f}",
            expected_str, result_str
        )
    
    console.print(table)
    
    if all_ok:
        console.print("[green]✅ Alle Validierungen korrekt[/green]")
    else:
        console.print("[red]❌ Validierung fehlerhaft - siehe Tabelle[/red]")
        raise AssertionError("TP/SL-Validierung hat Fehler")


def test_risk_summary():
    """Test: Risk-Summary"""
    console.print("\n[cyan]Test 7: Risk Summary[/cyan]")
    
    grid_config = GridConfig(
        upper_price=2.0,
        lower_price=1.0,
        grid_levels=10,
        grid_mode=GridMode.ARITHMETIC,
        min_price_step=0.01,
        base_order_size=100.0,
        tp_mode=TPMode.PERCENT,
        take_profit_pct=0.015,
        sl_mode=SLMode.PERCENT,
        stop_loss_pct=0.02
    )
    
    risk_config = RiskConfig(
        include_fees=True,
        fee_side="maker",
        maker_fee_pct=0.0002
    )
    
    calc = GridCalculator(grid_config)
    risk = RiskManager(grid_config, risk_config, calc)
    
    summary = risk.get_risk_summary()
    
    table = Table(title="Risk Summary")
    table.add_column("Parameter", style="cyan")
    table.add_column("Wert", style="yellow")
    
    for key, value in summary.items():
        if value is not None:
            table.add_row(key, str(value))
    
    console.print(table)
    console.print("[green]✅ Summary funktioniert[/green]")


def main():
    """Führt alle Tests aus"""
    console.print(Panel.fit(
        "[bold magenta]🧪 RiskManager Test-Suite[/bold magenta]",
        border_style="magenta"
    ))
    
    try:
        test_fee_calculation()
        test_tp_percent_mode()
        test_tp_next_grid_mode()
        test_sl_percent_mode()
        test_sl_fixed_mode()
        test_tp_sl_validation()
        test_risk_summary()
        
        console.print("\n" + "=" * 60)
        console.print(Panel(
            "[bold green]✅ Alle Tests bestanden![/bold green]",
            border_style="green"
        ))
        
    except AssertionError as e:
        console.print(f"\n[red]❌ Test fehlgeschlagen:[/red] {e}")
        sys.exit(1)
    
    except Exception as e:
        console.print(f"\n[red]❌ Unerwarteter Fehler:[/red] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
