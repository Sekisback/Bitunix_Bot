# strategies/GRID/manager/hedge_manager.py
"""
HedgeManager – verwaltet Hedge-Logik bei Ausbruch aus dem Grid-Bereich.
Mit PriceProtectScope-Validierung (Bitunix API).
"""

import logging
import time


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
    def check_trigger(self, price: float, lower_bound: float, upper_bound: float, step: float):
        """Prüft, ob der Preis die Grid-Range verlässt oder wieder eintritt."""
        if not getattr(self.config, "enabled", False):
            return

        trigger_offset = getattr(self.config, "trigger_offset", 1.0)
        trigger_distance = step * trigger_offset

        lower_trigger_price = lower_bound - trigger_distance
        upper_trigger_price = upper_bound + trigger_distance

        if price <= lower_trigger_price:
            self.logger.debug(f"[HEDGE] 📉 Trigger unterhalb Range @ {price:.4f}")
            self.trigger("below", price, step, lower_bound, upper_bound)

        elif price >= upper_trigger_price:
            self.logger.debug(f"[HEDGE] 📈 Trigger oberhalb Range @ {price:.4f}")
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

        # Richtung bestimmen
        if grid_mode == "long" and direction == "below":
            hedge_side = "SELL"
            hedge_price = lower_bound - (step * offset)
        elif grid_mode == "short" and direction == "above":
            hedge_side = "BUY"
            hedge_price = upper_bound + (step * offset)
        else:
            return

        self.logger.info(f"[HEDGE] ⚡ Hedge {hedge_side} @ {hedge_price:.4f}")

        if mode == "direct":
            self.place_order(hedge_side, hedge_price, self.get_size())

        elif mode == "dynamic":
            partials = getattr(self.config, "partial_levels", [0.5, 0.75, 1.0])
            for lvl in partials:
                offset_price = hedge_price - (step * lvl) if hedge_side == "SELL" else hedge_price + (step * lvl)
                self.place_order(hedge_side, offset_price, self.get_size(fraction=lvl))

        elif mode == "reversal":
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
        """Platziert Hedge-Order mit Prüfung des PriceProtectScope."""
        if size <= 0:
            self.logger.warning("[HEDGE] ❌ Ungültige Hedge-Größe (0)")
            return

        current_price = getattr(self, "live_price", None)
        if not current_price:
            self.logger.warning("[HEDGE] ⚠️ Kein Live-Preis verfügbar – Orderprüfung übersprungen")
            return

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

        self.logger.info(f"[HEDGE] 🚀 {side} {size} {self.symbol} @ {price:.6f}")

        if self.dry_run:
            self.logger.debug("[HEDGE] (Dry-Run aktiv – keine echte Order)")
            return

        try:
            order_id = self.api_client.place_order(
                symbol=self.symbol,
                side=side,
                order_type="LIMIT",
                qty=size,
                price=price,
                trade_side="OPEN",
                client_id=f"HEDGE_{int(time.time())}"
            )
            self.logger.info(f"[HEDGE] ✅ Hedge-Order platziert → ID={order_id}")
            self.active = True
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
    def update_preemptive_hedge(self, net_position_size: float, dry_run: bool = False, lower_bound: float = None, upper_bound: float = None, step: float = None):
        
        # === Debug-Log ===
        self.logger.info(f"[HEDGE] 🔍 update_preemptive_hedge() aufgerufen: net={net_position_size:.2f}, dry_run={dry_run}")

        """Passt präventiven Hedge an offene Grid-Orders an."""
        if not getattr(self.config, "enabled", False):
            self.logger.warning("[HEDGE] ⚠️ Hedge nicht aktiviert (config.enabled=False)")
            return

        if not getattr(self.config, "preemptive_hedge", False):
            self.logger.warning("[HEDGE] ⚠️ Präventiv-Hedge nicht aktiviert (config.preemptive_hedge=False)")
            return

        if abs(net_position_size) < 0.001:
            self.logger.info("[HEDGE] 🎯 Keine aktiven Orders → Hedge schließen")
            if self.active and not dry_run:
                self.close()
            self.active = False
            return

        grid_mode = getattr(self, "grid_direction", "long")

        if grid_mode == "long":
            hedge_side = "SELL"
            hedge_qty = abs(net_position_size)
            hedge_price = (lower_bound - step) if (lower_bound and step) else None
        elif grid_mode == "short":
            hedge_side = "BUY"
            hedge_qty = abs(net_position_size)
            hedge_price = (upper_bound + step) if (upper_bound and step) else None
        else:
            return

        if not hedge_price:
            self.logger.warning("[HEDGE] ⚠️ Kein Hedge-Preis berechenbar – kein Orderversuch")
            return
        
        # # kein Livepreis verfügbar → Hedge verschieben
        # if not getattr(self, "live_price", None):
        #     return

        if dry_run:
            self.logger.info(f"[HEDGE] Würde {hedge_side} {hedge_qty:.2f} @ {hedge_price:.6f} platzieren")
            self.active = True
            return

        try:
            self.place_order(hedge_side, hedge_price, hedge_qty)
        except Exception as e:
            self.logger.error(f"[HEDGE] ❌ Fehler beim Hedge-Update: {e}")
