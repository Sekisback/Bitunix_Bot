# strategies/GRID/manager/hedge_manager.py
"""
HedgeManager – verwaltet Hedge-Logik bei Ausbruch aus dem Grid-Bereich.
"""

import logging
import time

class HedgeManager:
    def __init__(self, config, api_client, symbol, logger=None, dry_run=False):
        self.config = config
        self.api_client = api_client
        self.symbol = symbol
        self.logger = logger or logging.getLogger("HedgeManager")
        self.active = False
        self.dry_run = dry_run 

    # ----------------------------------------------------------------
    def check_trigger(self, price: float, lower_bound: float, upper_bound: float, step: float):
        """Prüft, ob der Preis die Grid-Range verlässt oder wieder eintritt."""
        if not getattr(self.config, "enabled", False):
            return

        trigger_offset = getattr(self.config, "trigger_offset", 1.0)
        trigger_distance = step * trigger_offset

        # Unterer Trigger → erst N Grid-Steps unterhalb
        lower_trigger_price = lower_bound - trigger_distance
        upper_trigger_price = upper_bound + trigger_distance

        if price <= lower_trigger_price:
            self.logger.debug(f"[HEDGE] 📉 Trigger ausgelöst unterhalb Range @ {price} (Grenze: {lower_trigger_price})")
            self.trigger("below", price, step, lower_bound, upper_bound)

        elif price >= upper_trigger_price:
            self.logger.debug(f"[HEDGE] 📈 Trigger ausgelöst oberhalb Range @ {price} (Grenze: {upper_trigger_price})")
            self.trigger("above", price, step, lower_bound, upper_bound)

        elif self.active and getattr(self.config, "close_on_reentry", False) and lower_bound <= price <= upper_bound:
            self.close()

    # ----------------------------------------------------------------
    def trigger(self, direction: str, price: float, step: float, lower_bound: float, upper_bound: float):
        """Startet Hedge je nach Modus (direct, dynamic, reversal)."""
        if self.active:
            return

        grid_mode = getattr(self.config, "grid_direction", "long")
        mode = getattr(self.config, "mode", "direct")
        offset = getattr(self.config, "trigger_offset", 1.0)

        # === Richtung bestimmen je nach Grid-Mode ===
        if grid_mode == "long" and direction == "below":
            hedge_side = "SELL"
            hedge_price = lower_bound - (step * offset)
        elif grid_mode == "short" and direction == "above":
            hedge_side = "BUY"
            hedge_price = upper_bound + (step * offset)
        else:
            # keine Hedge-Bedingung erfüllt
            return

        self.logger.info(f"[HEDGE] ⚡ Direct Hedge {hedge_side} @ {hedge_price:.4f}")

        # === Modus prüfen ===
        if mode == "direct":
            self.place_order(hedge_side, hedge_price, self.get_size())

        elif mode == "dynamic":
            self.logger.info(f"[HEDGE] ⚙️ Dynamic Hedge ausgelöst ({direction})")
            partials = getattr(self.config, "partial_levels", [0.5, 0.75, 1.0])
            for lvl in partials:
                offset_price = hedge_price - (step * lvl) if hedge_side == "SELL" else hedge_price + (step * lvl)
                self.place_order(hedge_side, offset_price, self.get_size(fraction=lvl))

        elif mode == "reversal":
            self.logger.info(f"[HEDGE] 🔁 Reversal Hedge {hedge_side} @ {hedge_price:.4f}")
            self.place_order(hedge_side, hedge_price, self.get_size(multiplier=2.0))

        self.active = True

    # ----------------------------------------------------------------
    def get_size(self, fraction: float = 1.0, multiplier: float = 1.0) -> float:
        """Berechnet Hedge-Größe basierend auf Config."""
        size_mode = getattr(self.config, "size_mode", "net_position")
        fixed_ratio = getattr(self.config, "fixed_size_ratio", 0.5)
        if size_mode == "fixed":
            return fixed_ratio * fraction
        return 1.0 * fraction * multiplier

    # ----------------------------------------------------------------
    def place_order(self, side: str, price: float, size: float):
        """Platziert Hedge-Order (entsprechend Bitunix API) oder simuliert im Dry-Run."""
        if size <= 0:
            self.logger.warning("[HEDGE] ❌ Ungültige Hedge-Größe (0). Abbruch.")
            return

        self.logger.info(f"[HEDGE] 🚀 {side} {size} {self.symbol} @ {price}")

        # Schutz: falscher Client (Public)
        if not hasattr(self.api_client, "place_order"):
            self.logger.error("[HEDGE] ❌ API-Client hat keine place_order()-Methode (vermutlich Public-Client).")
            return

        # --- DRY RUN ---
        if self.dry_run:
            self.logger.debug("[HEDGE] (Dry-Run aktiv – keine echte Order)")
            return


        try:
            # ⚙️ Richtige API-Parameter laut Bitunix
            order_id = self.api_client.place_order(
                symbol=self.symbol,
                side=side,
                order_type="LIMIT",            # Standard: Limit-Order für Hedge
                qty=size,
                price=price,
                trade_side="OPEN",
                tp_price=None,                 # Kein TP im Hedge
                sl_price=None,                 # Kein SL im Hedge
                tp_stop_type="MARK_PRICE",
                sl_stop_type="MARK_PRICE",
                client_id=f"HEDGE_{int(time.time())}"
            )
            self.logger.info(f"[HEDGE] 🧩 Hedge-Order platziert → ID={order_id}")

        except Exception as e:
            self.logger.error(f"[HEDGE] ❌ Fehler beim Platzieren der Hedge-Order: {e}")

    # ----------------------------------------------------------------
    def close(self):
        """Schließt aktive Hedge-Position."""
        self.logger.info("[HEDGE] ✅ Preis wieder in Range – Hedge wird geschlossen.")
        if self.dry_run:
            self.logger.debug("[HEDGE] (Dry-Run aktiv – keine echte Schließung)")
            self.active = False
            return

        if self.api_client and hasattr(self.api_client, "close_position"):
            try:
                self.api_client.close_position(self.symbol)
            except Exception as e:
                self.logger.error(f"[HEDGE] ❌ Fehler beim Schließen der Hedge-Position: {e}")

        self.active = False


    # ----------------------------------------------------------------
    def update_preemptive_hedge(self, net_position_size: float, dry_run: bool = False, 
                           lower_bound: float = None, upper_bound: float = None, step: float = None):
        """
        Passt präventiven Hedge dynamisch an offene Grid-Orders an.
        
        Args:
            net_position_size: Netto-Position (nur aktive Orders)
            dry_run: Wenn True, nur simulieren
            lower_bound: Untere Grid-Grenze (für Preis-Berechnung)
            upper_bound: Obere Grid-Grenze (für Preis-Berechnung)
            step: Grid-Step-Größe (für Preis-Berechnung)
        """
        
        # ... [Debug-Log & Config-Checks bleiben gleich] ...
        
        if not getattr(self.config, "enabled", False):
            self.logger.warning("[HEDGE] ⚠️ Hedge nicht aktiviert (config.enabled=False)")
            return
        
        preemptive = getattr(self.config, "preemptive_hedge", False)
        if not preemptive:
            self.logger.warning("[HEDGE] ⚠️ Präventiv-Hedge nicht aktiviert (config.preemptive_hedge=False)")
            return
        
        # === Position-Analyse ===
        if abs(net_position_size) < 0.001:
            self.logger.info("[HEDGE] 🎯 Keine aktiven Orders → Hedge schließen")
            if self.active and not dry_run:
                self.close()
            self.active = False
            return
        
        # === Hedge-Richtung bestimmen ===
        grid_mode = getattr(self, "grid_direction", "long")
        
        if grid_mode == "long":
            hedge_side = "SELL"
            hedge_qty = abs(net_position_size)
            # Preis = 1 Level UNTERHALB des Grid
            if lower_bound and step:
                hedge_price = lower_bound - step
            else:
                self.logger.warning("[HEDGE] ⚠️ lower_bound/step fehlt, verwende Market-Order")
                hedge_price = None
        
        elif grid_mode == "short":
            hedge_side = "BUY"
            hedge_qty = abs(net_position_size)
            # Preis = 1 Level OBERHALB des Grid
            if upper_bound and step:
                hedge_price = upper_bound + step
            else:
                self.logger.warning("[HEDGE] ⚠️ upper_bound/step fehlt, verwende Market-Order")
                hedge_price = None
        
        else:
            # Both-Mode: Kein präventiver Hedge
            return
        
        # === Logging ===
        price_info = f"@ {hedge_price:.6f}" if hedge_price else "@ MARKET"
        # self.logger.info(
        #     f"[HEDGE] 🛡️  Präventiv: Net={net_position_size:.2f} → "
        #     f"{hedge_side} {hedge_qty:.2f} {self.symbol} {price_info}"
        # )
        
        # === Dry-Run ===
        if dry_run:
            self.logger.info(
                f"[HEDGE] Würde {hedge_side} {hedge_qty:.2f} {price_info} platzieren"
            )
            self.active = True
            return
        
        # === Real-Mode: Hedge platzieren oder anpassen ===
        try:
            if self.active:
                self.logger.info(f"[HEDGE] ⚙️ Update Hedge: {hedge_side} {hedge_qty:.2f}")
                self.close()
                if hedge_price:
                    self._place_preemptive_hedge(hedge_side, hedge_qty, hedge_price)
                else:
                    # Fallback: Market-Order wenn Preis fehlt
                    self._place_market_hedge(hedge_side, hedge_qty)
            else:
                if hedge_price:
                    self._place_preemptive_hedge(hedge_side, hedge_qty, hedge_price)
                else:
                    self._place_market_hedge(hedge_side, hedge_qty)
            
        except Exception as e:
            self.logger.error(f"[HEDGE] ❌ Fehler beim Hedge-Update: {e}")


    def _place_market_hedge(self, side: str, qty: float):
        """Fallback: Market-Order wenn Limit-Preis nicht berechenbar"""
        try:
            order_id = self.api_client.place_order(
                symbol=self.symbol,
                side=side,
                order_type="MARKET",
                qty=qty,
                trade_side="OPEN",
                client_id=f"HEDGE_PREV_MKT_{int(time.time())}"
            )
            self.active = True
            self.logger.info(f"[HEDGE] ✅ Market-Hedge platziert → ID={order_id}")
        except Exception as e:
            self.logger.error(f"[HEDGE] ❌ Market-Hedge fehlgeschlagen: {e}")
    
    # ----------------------------------------------------------------
    def _place_preemptive_hedge(self, side: str, qty: float, price: float):
        """
        Platziert präventiven Hedge als Limit-Order.
        
        Args:
            side: "BUY" oder "SELL"
            qty: Hedge-Größe
            price: Limit-Preis für die Hedge-Order
        """
        if qty <= 0:
            self.logger.warning("[HEDGE] ⚠️ Ungültige Hedge-Größe (0)")
            return
        
        # Schutz: Client-Check
        if not hasattr(self.api_client, "place_order"):
            self.logger.error("[HEDGE] ❌ API-Client hat keine place_order()-Methode")
            return
        
        self.logger.info(f"[HEDGE] 🚀 Präventiv-Hedge: {side} {qty} {self.symbol} @ {price:.6f} (LIMIT)")
        
        try:
            # Limit-Order für präzise Platzierung
            order_id = self.api_client.place_order(
                symbol=self.symbol,
                side=side,
                order_type="LIMIT",  # ← LIMIT statt MARKET
                qty=qty,
                price=price,  # ← Preis 1 Level unterhalb Grid
                trade_side="OPEN",
                client_id=f"HEDGE_PREV_{int(time.time())}"
            )
            
            self.active = True
            self.logger.info(f"[HEDGE] ✅ Präventiv-Hedge platziert → ID={order_id}")
            
        except Exception as e:
            self.logger.error(f"[HEDGE] ❌ Hedge-Platzierung fehlgeschlagen: {e}")