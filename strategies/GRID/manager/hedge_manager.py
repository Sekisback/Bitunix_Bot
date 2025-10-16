# strategies/GRID/manager/hedge_manager.py
"""
HedgeManager – verwaltet Hedge-Logik bei Ausbruch aus dem Grid-Bereich.
Mit PriceProtectScope-Validierung (Bitunix API).

FIXES:
- ✅ get_size() nutzt jetzt net_position
- ✅ live_price wird initialisiert
- ✅ update_preemptive_hedge() prüft None-Werte
- ✅ place_order() prüft live_price früher
"""

import logging
import time
from typing import Optional
from utils.exceptions import OrderPlacementError, InsufficientBalanceError

class HedgeManager:
    def __init__(self, config, api_client, symbol, logger=None, dry_run=False, client_pub=None):
        self.config = config
        self.api_client = api_client
        self.client_pub = client_pub
        self.symbol = symbol
        self.logger = logger or logging.getLogger("HedgeManager")
        self.active = False
        self.dry_run = dry_run
        self.price_protect_scope = None
        self.live_price = None  # ✅ FIX: Initialisierung hinzugefügt
        self.hedge_pending = False

        # Trading Pair Info laden (priceProtectScope)
        self._load_trading_pair_info()

    # ----------------------------------------------------------------
    def _load_trading_pair_info(self):
        """Lädt Trading Pair Informationen (inkl. priceProtectScope) vom Exchange."""
        if not self.client_pub:
            self.logger.warning("[HEDGE] ⚠️ Kein Public Client verfügbar")
            self.price_protect_scope = 0.05
            self.logger.info("[HEDGE] Verwende Fallback priceProtectScope: 5.0%")
            return

        try:
            response = self.client_pub.get_trading_pairs(symbols=self.symbol)

            # Unterschiedliche Formate (dict / list)
            if isinstance(response, dict):
                data = response.get("data", [])
            elif isinstance(response, list):
                data = response
            else:
                self.logger.warning(f"[HEDGE] ⚠️ Unerwartetes Format: {type(response)}")
                data = []

            if not data:
                self.logger.warning(f"[HEDGE] ⚠️ Keine Trading Pair Info für {self.symbol}")
                self.price_protect_scope = 0.05
                return

            pair_info = data[0]
            self.price_protect_scope = float(pair_info.get("priceProtectScope", 0.05))
            self.logger.info(
                f"[HEDGE] 📊 Trading Pair Info geladen: priceProtectScope={self.price_protect_scope*100:.1f}%"
            )

        except Exception as e:
            self.logger.error(f"[HEDGE] ❌ Trading Pair Info Fehler: {e}")
            self.price_protect_scope = 0.05

        finally:
            if self.price_protect_scope is None:
                self.price_protect_scope = 0.05
            self.logger.info(f"[HEDGE] Aktiver priceProtectScope: {self.price_protect_scope*100:.1f}%")


    # ----------------------------------------------------------------
    def check_trigger(self, price: float, lower_bound: float, upper_bound: float, step: float, net_position: float = 0):
        """Prüft, ob der Preis die Grid-Range verlässt oder wieder eintritt."""
        if not getattr(self.config, "enabled", False):
            return

        trigger_offset = getattr(self.config, "trigger_offset", 1.0)
        trigger_distance = step * trigger_offset

        lower_trigger_price = lower_bound - trigger_distance
        upper_trigger_price = upper_bound + trigger_distance

        if price <= lower_trigger_price:
            self.logger.debug(f"[HEDGE] 📉 Trigger unterhalb Range @ {price:.4f}")
            self.trigger("below", price, step, lower_bound, upper_bound, net_position=net_position)

        elif price >= upper_trigger_price:
            self.logger.debug(f"[HEDGE] 📈 Trigger oberhalb Range @ {price:.4f}")
            self.trigger("above", price, step, lower_bound, upper_bound, net_position=net_position)

        elif self.active and getattr(self.config, "close_on_reentry", False) and lower_bound <= price <= upper_bound:
            self.close()

    # ----------------------------------------------------------------
    def trigger(self, direction: str, price: float, step: float, lower_bound: float, upper_bound: float, net_position: float = 0):
        """Startet Hedge je nach Modus (direct, dynamic, reversal)."""
        if self.active:
            return

        grid_mode = getattr(self.config, "grid_direction", "long")
        mode = getattr(self.config, "mode", "direct")
        offset = getattr(self.config, "trigger_offset", 1.0)

        # Richtung bestimmen
        if grid_mode == "long" and direction == "below":
            hedge_side = "SELL"
            hedge_price = lower_bound - (step * offset)
        elif grid_mode == "short" and direction == "above":
            hedge_side = "BUY"
            hedge_price = upper_bound + (step * offset)
        else:
            return

        self.logger.info(f"[HEDGE] ⚡ Hedge {hedge_side} @ {hedge_price:.4f} | Net={net_position:.2f}")

        if mode == "direct":
            self.place_order(hedge_side, hedge_price, self.get_size(net_position=net_position))

        elif mode == "dynamic":
            partials = getattr(self.config, "partial_levels", [0.5, 0.75, 1.0])
            for lvl in partials:
                offset_price = hedge_price - (step * lvl) if hedge_side == "SELL" else hedge_price + (step * lvl)
                self.place_order(hedge_side, offset_price, self.get_size(net_position=net_position, fraction=lvl))

        elif mode == "reversal":
            self.place_order(hedge_side, hedge_price, self.get_size(net_position=net_position, multiplier=2.0))

        self.active = True

    # ----------------------------------------------------------------
    def get_size(self, net_position: float = 0, fraction: float = 1.0, multiplier: float = 1.0) -> float:
        """
        Berechnet Hedge-Größe basierend auf Config.
        
        ✅ FIX: Nutzt jetzt net_position statt festen Wert
        """
        size_mode = getattr(self.config, "size_mode", "net_position")
        fixed_ratio = getattr(self.config, "fixed_size_ratio", 0.5)
        
        if size_mode == "fixed":
            return fixed_ratio * fraction * multiplier
        
        # ✅ FIX: Echte Net-Position verwenden!
        return abs(net_position) * fraction * multiplier

    # ----------------------------------------------------------------
    def place_order(self, side: str, price: float, size: float, sl_price: Optional[float] = None):
        """
        Platziert Hedge-Order mit Stop-Loss
        
        Args:
            side: "BUY" oder "SELL"
            price: Limit-Preis
            size: Ordergröße
            sl_price: Stop-Loss-Preis (optional)
        """
        if size <= 0:
            self.logger.warning("[HEDGE] ❌ Ungültige Hedge-Größe (0)")
            return

        if not self.live_price:
            self.logger.warning("[HEDGE] ⚠️ Kein Live-Preis verfügbar → Order übersprungen")
            return

        current_price = self.live_price
        scope = self.price_protect_scope or 0.05
        min_price = current_price * (1 - scope)
        max_price = current_price * (1 + scope)

        # PriceProtect prüfen
        if side == "SELL" and price < min_price:
            self.logger.warning(
                f"[HEDGE] 🚫 Preis {price:.4f} < min {min_price:.4f} (Scope={scope*100:.1f}%) → Order blockiert"
            )
            return
        if side == "BUY" and price > max_price:
            self.logger.warning(
                f"[HEDGE] 🚫 Preis {price:.4f} > max {max_price:.4f} (Scope={scope*100:.1f}%) → Order blockiert"
            )
            return

        if self.dry_run:
            sl_str = f" | SL={sl_price:.4f}" if sl_price else ""
            self.logger.debug(f"[HEDGE] (Dry) place_order() @ {price:.6f}{sl_str}")
            
            # ✅ NEU: Auch im Dry-Run Status setzen
            self.current_hedge_price = price
            self.current_hedge_size = size
            self.current_sl_price = sl_price
            self.active = True
            return

        try:
            # ✅ NEU: Mit Stop-Loss
            order_params = {
                "symbol": self.symbol,
                "side": side,
                "order_type": "LIMIT",
                "qty": size,
                "price": price,
                "trade_side": "OPEN",
                "client_id": f"HEDGE_{int(time.time())}"
            }
            
            # SL hinzufügen wenn vorhanden
            if sl_price:
                order_params["sl_price"] = sl_price
                order_params["sl_stop_type"] = "MARK_PRICE"
            
            order_id = self.api_client.place_order(**order_params)
            
            # ✅ NEU: Status speichern für Anzeige
            self.current_hedge_price = price
            self.current_hedge_size = size
            self.current_sl_price = sl_price
            self.active = True
            
            sl_info = f" | SL={sl_price:.4f}" if sl_price else ""
            self.logger.info(f"[HEDGE] ✅ Hedge-Order → ID={order_id}{sl_info}")
        
        except OrderPlacementError as e:
            self.logger.error(f"[HEDGE] ❌ Order-Placement-Fehler: {e}")
            raise
        
        except InsufficientBalanceError as e:
            self.logger.error(f"[HEDGE] ❌ Zu wenig Balance: {e}")
            return
        
        except Exception as e:
            self.logger.exception(f"[HEDGE] ❌ Unerwarteter Fehler beim Platzieren: {e}")

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
    def update_preemptive_hedge(self, dry_run: bool = False, 
                       lower_bound: float = None, upper_bound: float = None, 
                       step: float = None, current_price: float = None,
                       grid_levels: list = None, base_size: float = 20.0):
        """
        Passt präventiven Hedge an mit Stop-Loss
        
        Risiko = Offene Orders unter/über Preis + Gefüllte ohne TP
        """
        
        if not getattr(self.config, "enabled", False):
            return
        if not getattr(self.config, "preemptive_hedge", False):
            return
        
        # Prüfe Daten
        if not (lower_bound and upper_bound and step and current_price and grid_levels):
            self.logger.warning("[HEDGE] ⚠️ Unvollständige Daten")
            return

        grid_mode = getattr(self.config, "grid_direction", "long")
        
        # ✅ Risiko-Berechnung + SL-Berechnung
        if grid_mode == "long":
            # Offene Orders UNTER Preis
            active_orders_below = [
                lvl for lvl in grid_levels 
                if lvl.active and lvl.price < current_price and lvl.side == "BUY"
            ]
            
            # Gefüllte ohne TP
            filled_without_tp = [
                lvl for lvl in grid_levels 
                if lvl.position_open or lvl.filled
            ]
            
            risk_count = len(active_orders_below) + len(filled_without_tp)
            hedge_side = "SELL"
            hedge_price = lower_bound - step
            sl_price = hedge_price + (2 * step)  # ✅ SL ÜBER Hedge
            
        elif grid_mode == "short":
            active_orders_above = [
                lvl for lvl in grid_levels 
                if lvl.active and lvl.price > current_price and lvl.side == "SELL"
            ]
            
            filled_without_tp = [
                lvl for lvl in grid_levels 
                if lvl.position_open or lvl.filled
            ]
            
            risk_count = len(active_orders_above) + len(filled_without_tp)
            hedge_side = "BUY"
            hedge_price = upper_bound + step
            sl_price = hedge_price - (2 * step)  # ✅ SL UNTER Hedge
        else:
            return
        
        target_qty = risk_count * base_size
        
        last_logged_state = getattr(self, "_last_hedge_log", None)
        current_state = (risk_count, target_qty)

        if current_state != last_logged_state:
            self._last_hedge_log = current_state
        
        # Kein Risiko → Hedge schließen
        if target_qty < 0.001:
            if self.active and not dry_run:
                self.close()
            self.active = False
            self.hedge_pending = False
            return
        
        # ✅ Hedge existiert → MODIFY
        if self.active and hasattr(self, "hedge_order_id"):
            current_qty = getattr(self, "current_hedge_size", 0)
            
            if current_qty > 0:
                deviation = abs(target_qty - current_qty) / current_qty
                
                if deviation > 0.05:  # 5% Schwelle
                    self.logger.info(f"[HEDGE] 🔄 Modify Qty: {current_qty:.2f} → {target_qty:.2f}")
                    
                    if not dry_run:
                        try:
                            self.api_client.modify_order(
                                order_id=self.hedge_order_id,
                                qty=str(target_qty),
                                sl_price=str(sl_price)  # ✅ SL auch bei Modify
                            )
                            self.current_hedge_size = target_qty
                            self.current_sl_price = sl_price  # ✅ SL speichern
                            self.logger.info(f"[HEDGE] ✅ Qty + SL angepasst (SL={sl_price:.4f})")
                        except Exception as e:
                            self.logger.error(f"[HEDGE] ❌ Modify failed: {e}")
                            # Fallback: Close + neu platzieren
                            self.close()
                            self.active = False
                    else:
                        self.current_hedge_size = target_qty
                        self.current_sl_price = sl_price  # ✅ SL auch im Dry-Run
            return
        
        # ✅ Neuer Hedge → Platzieren mit SL
        if not hedge_price or hedge_price <= 0:
            return
        
        if dry_run:
            self.active = True
            self.current_hedge_size = target_qty
            self.current_hedge_price = hedge_price
            self.current_sl_price = sl_price  # ✅ SL im Dry-Run
            return
        
        try:
            result = self.api_client.place_order(
                symbol=self.symbol, 
                side=hedge_side, 
                order_type="LIMIT",
                qty=target_qty, 
                price=hedge_price, 
                trade_side="OPEN",
                client_id=f"HEDGE_{int(time.time())}",
                sl_price=sl_price,              # ✅ SL übergeben
                sl_stop_type="MARK_PRICE"       # ✅ SL-Typ
            )
            
            self.hedge_order_id = result.get("orderId")
            self.current_hedge_size = target_qty
            self.current_hedge_price = hedge_price
            self.current_sl_price = sl_price  # ✅ SL speichern
            self.active = True
            
            self.logger.info(
                f"[HEDGE] ✅ Order ID={self.hedge_order_id} | "
                f"Preis={hedge_price:.4f} | SL={sl_price:.4f}"
            )
        except Exception as e:
            self.logger.error(f"[HEDGE] ❌ Fehler: {e}")