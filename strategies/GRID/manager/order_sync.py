import logging
from typing import Callable, List, Optional


class OrderSync:
    """
    Synchronisiert interne Grid-Level-Orders mit den offenen Orders (aus WS oder Cache).
    Unterstützt einen 'dry_run'-Modus, der nur prüft, aber nichts ändert.
    """

    def __init__(
        self,
        symbol: str,
        levels,
        logger: Optional[logging.Logger] = None,
        fetch_orders_callback: Optional[Callable[[], List[dict]]] = None,
    ):
        """
        :param symbol: Handels-Paar (z.B. 'ONDOUSDT')
        :param levels: Liste von GridLevel-Objekten
        :param logger: Optionaler Logger
        :param fetch_orders_callback: Funktion, die offene Orders liefert (z.B. aus WS)
        """
        self.symbol = symbol
        self.levels = levels
        self.logger = logger or logging.getLogger(f"OrderSync-{symbol}")
        self.fetch_orders_callback = fetch_orders_callback

    # --------------------------------------------------------------------------
    async def fetch_exchange_orders(self):
        """Holt offene Orders über Callback oder liefert leere Liste."""
        if not self.fetch_orders_callback:
            self.logger.warning("[OrderSync] Kein fetch_orders_callback definiert – nutze leere Orderliste.")
            return []

        try:
            orders = self.fetch_orders_callback()  # synchrone Callback-Funktion
            count = len(orders)
            self.logger.debug(f"[OrderSync] {count} offene Orders aus Cache/WS empfangen.")
            return orders
        except Exception as e:
            self.logger.error(f"[OrderSync] Fehler beim Abruf offener Orders: {e}")
            return []

    # --------------------------------------------------------------------------
    def match_orders(self, exchange_orders):
        """Vergleicht Exchange-Orders mit Grid-Leveln."""
        matched, missing, obsolete = [], [], []

        for level in self.levels:
            match = next(
                (o for o in exchange_orders if abs(float(o.get("price", 0)) - level.price) < 1e-8),
                None,
            )
            if match:
                matched.append(match)
                level.status = "open"
                level.order_id = match.get("orderId")
            else:
                missing.append(level)

        for o in exchange_orders:
            if not any(getattr(l, "order_id", None) == o.get("orderId") for l in self.levels):
                obsolete.append(o)

        return matched, missing, obsolete

    # --------------------------------------------------------------------------
    async def sync_orders(self, dry_run: bool = True):
        """
        Führt die Synchronisation durch.
        - dry_run=True → Nur prüfen & loggen
        - dry_run=False → Tatsächliches Nachsetzen/Löschen (nur wenn verfügbar)
        """
        exchange_orders = await self.fetch_exchange_orders()
        matched, missing, obsolete = self.match_orders(exchange_orders)

        self.logger.info(
            f"[OrderSync] MATCHED={len(matched)} | MISSING={len(missing)} | OBSOLETE={len(obsolete)}"
        )

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

        # === Real-Mode: hier würden create/cancel-Calls kommen ===
        for lvl in missing:
            try:
                await lvl.create_order()
                self.logger.info(f"[OrderSync] Neue Order gesetzt @ {lvl.price}")
            except Exception as e:
                self.logger.error(f"[OrderSync] Fehler beim Setzen @ {lvl.price}: {e}")

        for o in obsolete:
            try:
                # Hier wäre z.B. self.client.cancel_order()
                self.logger.info(f"[OrderSync] Überflüssige Order gelöscht ID={o.get('orderId')}")
            except Exception as e:
                self.logger.error(f"[OrderSync] Fehler beim Löschen ID={o.get('orderId')}: {e}")

        return {
            "matched": len(matched),
            "missing": len(missing),
            "obsolete": len(obsolete),
            "mode": "live",
        }
