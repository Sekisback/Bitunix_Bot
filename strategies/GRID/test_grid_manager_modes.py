"""
Unit-Test für den Bitunix GridManager
Prüft die korrekte Funktion der Modi:
 - long  (nur BUY + TP oberhalb)
 - short (nur SELL + TP unterhalb)
 - both  (BUY + SELL mit passenden TPs)

Führt keine echten API-Calls aus.
"""

import pytest
from manager.grid_manager import GridManager, GridLevel


# ---------------------------------------------------------------------------
# MockExchange – simuliert eine einfache API
# ---------------------------------------------------------------------------
class MockExchange:
    def __init__(self):
        self.orders = {}
        self.last_id = 0

    def place_limit_order(self, symbol, side, price, size, mode):
        """Erzeugt eine Dummy-Order-ID."""
        self.last_id += 1
        oid = f"{side.upper()}_{self.last_id}"
        self.orders[oid] = {"symbol": symbol, "side": side, "price": price, "size": size}
        return oid

    def check_filled_orders(self, order_ids):
        """Simuliert: alle Orders mit gerader ID gelten als 'gefüllt'."""
        filled = []
        for oid in order_ids:
            num = int(oid.split("_")[1])
            if num % 2 == 0:
                filled.append(oid)
        return filled


# ---------------------------------------------------------------------------
# Hilfsfunktion: Standard-Config generieren
# ---------------------------------------------------------------------------
def make_config(mode: str):
    return {
        "symbol": "ONDOUSDT",
        "trading": {
            "grid_mode": mode,
            "grid_step_pct": 0.5,
            "num_grids": 5,
            "order_size": 10,
            "margin_mode": "isolated",
        }
    }


# ---------------------------------------------------------------------------
# Test 1: Long-Mode
# ---------------------------------------------------------------------------
def test_long_mode():
    cfg = make_config("long")
    exch = MockExchange()
    gm = GridManager(cfg, exch)

    gm.initialize_grid(1.0000)
    gm.place_orders()

    # Nur BUY-Orders erlaubt
    assert all(oid.startswith("BUY") for oid in exch.orders), "Long mode enthält SELL Orders!"

    # Jede Order muss TP oberhalb haben
    for lvl in gm.grid_levels:
        assert lvl.tp_price > lvl.price, f"Long TP ({lvl.tp_price}) nicht über Entry ({lvl.price})"


# ---------------------------------------------------------------------------
# Test 2: Short-Mode
# ---------------------------------------------------------------------------
def test_short_mode():
    cfg = make_config("short")
    exch = MockExchange()
    gm = GridManager(cfg, exch)

    gm.initialize_grid(1.0000)
    gm.place_orders()

    # Nur SELL-Orders erlaubt
    assert all(oid.startswith("SELL") for oid in exch.orders), "Short mode enthält BUY Orders!"

    # Jede Order muss TP unterhalb haben
    for lvl in gm.grid_levels:
        assert lvl.tp_price < lvl.price, f"Short TP ({lvl.tp_price}) nicht unter Entry ({lvl.price})"


# ---------------------------------------------------------------------------
# Test 3: Both-Mode
# ---------------------------------------------------------------------------
def test_both_mode():
    cfg = make_config("both")
    exch = MockExchange()
    gm = GridManager(cfg, exch)

    gm.initialize_grid(1.0000)
    gm.place_orders()

    buys = [o for o in exch.orders.values() if o["side"] == "buy"]
    sells = [o for o in exch.orders.values() if o["side"] == "sell"]

    # Beide Seiten müssen Orders enthalten
    assert buys and sells, "Both mode enthält keine Orders beider Seiten!"

    # BUY-Tps müssen oberhalb liegen, SELL-Tps unterhalb
    for lvl in gm.grid_levels:
        if lvl.price < gm.base_price:
            assert lvl.tp_price > lvl.price, f"BUY TP falsch: {lvl.tp_price} <= {lvl.price}"
        elif lvl.price > gm.base_price:
            assert lvl.tp_price < lvl.price, f"SELL TP falsch: {lvl.tp_price} >= {lvl.price}"


# ---------------------------------------------------------------------------
# Test 4: Simulierter Update-Zyklus
# ---------------------------------------------------------------------------
def test_update_cycle():
    cfg = make_config("both")
    exch = MockExchange()
    gm = GridManager(cfg, exch)

    gm.initialize_grid(1.0000)
    gm.place_orders()
    filled_before = len(exch.orders)

    gm.update(1.0100)  # löst einige TPs aus

    # Nach dem Update sollen wieder Orders existieren (nachgesetzte)
    assert len(gm.active_orders) > 0, "Nach Update keine aktiven Orders mehr!"
    assert len(exch.orders) >= filled_before, "Es wurden nicht genug Orders nachgesetzt!"


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
