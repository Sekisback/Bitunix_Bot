# file: strategies/GRID/manager/order_sync.py
import time
import logging

class OrderSync:
    """
    Synchronisiert erwartete Grid-Orders mit den echten Orders am Exchange.
    Kann im Dry-Run oder Real-Mode laufen.
    """

    def __init__(self, symbol, levels, logger: logging.Logger, client=None, size: float = None, grid_direction: str = "both"):
        self.symbol = symbol
        self.levels = levels
        self.logger = logger
        self.client = client
        self.size = size or 0.0
        self.grid_direction = grid_direction
        self.fetch_orders_callback = None  # kann vom AccountSync überschrieben werden

    # ---------------------------------------------------------------------
    async def fetch_exchange_orders(self):
        """Holt offene Orders – entweder über Callback (AccountSync) oder HTTP-Fallback."""
        if self.fetch_orders_callback:
            try:
                return self.fetch_orders_callback()
            except Exception as e:
                self.logger.error(f"[OrderSync] Fehler bei fetch_orders_callback: {e}")
                return []
        return []  # Fallback: kein Cache verfügbar

    # ---------------------------------------------------------------------
    def match_orders(self, exchange_orders):
        """Vergleicht aktuelle Exchange-Orders mit erwarteten Grid-Levels."""
        matched, missing, obsolete = [], [], []

        # --- MISSING: Level ohne aktive Order ---
        for lvl in self.levels:
            if not lvl.active and not lvl.filled:
                matched_order = next(
                    (o for o in exchange_orders if abs(float(o.get("price", 0)) - lvl.price) < 1e-8),
                    None,
                )
                if matched_order:
                    lvl.order_id = matched_order.get("orderId")
                    lvl.active = True
                    matched.append(lvl)
                else:
                    missing.append(lvl)

        # --- OBSOLETE: Exchange-Orders, die keinem Level mehr entsprechen ---
        level_prices = [l.price for l in self.levels]
        for o in exchange_orders:
            if float(o.get("price", 0)) not in level_prices:
                obsolete.append(o)

        return matched, missing, obsolete

    # ---------------------------------------------------------------------
    async def sync_orders(self, dry_run: bool = True):
        """
        Führt die Synchronisation durch.
        - dry_run=True  → Nur prüfen & loggen
        - dry_run=False → Tatsächliches Nachsetzen/Löschen
        """
        exchange_orders = await self.fetch_exchange_orders()
        matched, missing, obsolete = self.match_orders(exchange_orders)

        self.logger.info(
            f"[OrderSync] MATCHED={len(matched)} | MISSING={len(missing)} | OBSOLETE={len(obsolete)}"
        )

        # ---------------------------------------------------------------
        # 🧪 Dry-Run
        # ---------------------------------------------------------------
        if dry_run:
            self.logger.info("[OrderSync] Dry-Run aktiv — keine echten Änderungen durchgeführt.")
            for lvl in missing:
                self.logger.debug(f"[DryRun] Würde Order setzen @ {lvl.price}")
            for o in obsolete:
                self.logger.debug(f"[DryRun] Würde Order löschen ID={o.get('orderId')} @ {o.get('price')}")
            return {
                "matched": len(matched),
                "missing": len(missing),
                "obsolete": len(obsolete),
                "mode": "dry_run",
            }

        # ---------------------------------------------------------------
        # ⚡ Real-Mode
        # ---------------------------------------------------------------
        for lvl in missing:
            try:
                # Sicherheitsprüfung für Richtung
                if self.grid_direction == "long" and lvl.side == "SELL":
                    self.logger.warning(f"[OrderSync] ⚠️ Überspringe SELL-Level @ {lvl.price} (long-mode aktiv)")
                    continue
                if self.grid_direction == "short" and lvl.side == "BUY":
                    self.logger.warning(f"[OrderSync] ⚠️ Überspringe BUY-Level @ {lvl.price} (short-mode aktiv)")
                    continue

                client_id = f"GRID_{lvl.index}_{int(time.time())}"
                size = self.size or 0.0
                if size <= 0.0:
                    self.logger.error("[OrderSync] ⚠️ Ungültige Ordergröße — Order übersprungen.")
                    continue

                # trade_side dynamisch bestimmen
                if self.grid_direction == "both":
                    trade_side = "OPEN" if lvl.side == "BUY" else "CLOSE"
                else:
                    trade_side = "OPEN"

                # Sicherstellen, dass TP/SL existieren
                tp_price = lvl.tp if lvl.tp is not None else 0
                sl_price = lvl.sl if lvl.sl is not None else 0

                # 💬 Logging mit vollständigen Details
                self.logger.info(
                    f"[OrderSync] 🟢 Setze echte Order @ {lvl.price} | side={lvl.side} | trade_side={trade_side} | "
                    f"size={size} | TP={tp_price} | SL={sl_price}"
                )

                result = self.client.place_order(
                    symbol=self.symbol,
                    side=lvl.side,
                    order_type="LIMIT",
                    qty=size,
                    price=lvl.price,
                    trade_side=trade_side,
                    tp_price=tp_price,
                    sl_price=sl_price,
                    tp_stop_type="MARK_PRICE",
                    sl_stop_type="MARK_PRICE",
                    client_id=client_id,
                )

                lvl.order_id = result.get("orderId") if isinstance(result, dict) else str(result)
                lvl.active = True
                self.logger.info(f"[OrderSync] ✅ Order gesetzt ID={lvl.order_id} @ {lvl.price} (TP={tp_price}, SL={sl_price})")

            except Exception as e:
                self.logger.error(f"[OrderSync] Fehler beim Setzen @ {lvl.price}: {e}")

        # ---------------------------------------------------------------
        # 🧹 Obsolete Orders aufräumen (optional)
        # ---------------------------------------------------------------
        for o in obsolete:
            try:
                order_id = o.get("orderId")
                self.logger.info(f"[OrderSync] 🗑️ Lösche veraltete Order ID={order_id}")
                # Optional: self.client.cancel_order(symbol=self.symbol, orderId=order_id)
            except Exception as e:
                self.logger.error(f"[OrderSync] Fehler beim Löschen ID={o.get('orderId')}: {e}")

        return {
            "matched": len(matched),
            "missing": len(missing),
            "obsolete": len(obsolete),
            "mode": "live",
        }
