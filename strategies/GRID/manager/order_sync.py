# file: strategies/GRID/manager/order_sync.py
import time
import logging
import asyncio
import sys
from pathlib import Path

GRID_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(GRID_DIR))
from utils.constants import PRICE_TOLERANCE


class OrderSync:
    """Synchronisiert erwartete Grid-Orders mit echten Orders am Exchange"""

    def __init__(self, symbol, levels, logger: logging.Logger, client=None, size: float = None, grid_direction: str = "both"):
        self.symbol = symbol
        self.levels = levels
        self.logger = logger
        self.client = client
        self.size = size or 0.0
        self.grid_direction = grid_direction
        self.fetch_orders_callback = None
        self._sync_lock = asyncio.Lock()

    async def fetch_exchange_orders(self):
        """Holt offene Orders über Callback oder HTTP-Fallback"""
        if self.fetch_orders_callback:
            try:
                return self.fetch_orders_callback()
            except Exception as e:
                self.logger.error(f"[OrderSync] Fehler bei fetch_orders_callback: {e}")
                return []
        return []

    def match_orders(self, exchange_orders):
        """
        Vergleicht Exchange-Orders mit Grid-Levels
        Performance: O(n) statt O(n²) durch Dict-Lookup
        """
        matched, missing, obsolete = [], [], []
        
        # Performance-Optimierung: Dict mit Preis als Key
        order_dict = {}
        for o in exchange_orders:
            price = float(o.get("price", 0))
            # Runde auf Grid-Genauigkeit
            rounded_price = round(price, 8)
            order_dict[rounded_price] = o
        
        # Prüfe alle Grid-Levels
        for lvl in self.levels:
            if not lvl.active and not lvl.filled:
                rounded_level_price = round(lvl.price, 8)
                
                # O(1) Lookup statt O(n) nested loop
                matched_order = order_dict.get(rounded_level_price)
                
                # Fallback: Toleranz-Check bei Float-Ungenauigkeit
                if not matched_order:
                    for price, order in order_dict.items():
                        if abs(price - rounded_level_price) < PRICE_TOLERANCE:
                            matched_order = order
                            break
                
                if matched_order:
                    lvl.order_id = matched_order.get("orderId")
                    lvl.active = True
                    matched.append(lvl)
                else:
                    missing.append(lvl)
        
        # Finde obsolete Orders (nicht in Grid)
        level_prices = {round(l.price, 8) for l in self.levels}
        for o in exchange_orders:
            price = round(float(o.get("price", 0)), 8)
            if price not in level_prices:
                # Doppelcheck mit Toleranz
                is_in_grid = any(abs(price - lp) < PRICE_TOLERANCE for lp in level_prices)
                if not is_in_grid:
                    obsolete.append(o)
        
        return matched, missing, obsolete

    async def sync_orders(self, dry_run: bool = True):
        """Führt Synchronisation durch (mit Race Condition Fix)"""
        async with self._sync_lock:
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
            
            # Real-Mode: Fehlende Orders setzen
            for lvl in missing:
                try:
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
                    
                    trade_side = "OPEN" if self.grid_direction == "both" else "OPEN"
                    tp_price = lvl.tp if lvl.tp else None
                    sl_price = lvl.sl if lvl.sl else None
                    
                    params = dict(
                        symbol=self.symbol, side=lvl.side, order_type="LIMIT", qty=size, price=lvl.price,
                        trade_side=trade_side, tp_stop_type="MARK_PRICE", sl_stop_type="MARK_PRICE",
                        client_id=client_id,
                    )
                    
                    if tp_price:
                        params["tp_price"] = tp_price
                    if sl_price:
                        params["sl_price"] = sl_price
                    
                    self.logger.info(
                        f"[OrderSync] 🟢 Setze echte Order @ {lvl.price} | side={lvl.side} | "
                        f"trade_side={trade_side} | size={size} | TP={tp_price} | SL={sl_price}"
                    )
                    
                    result = self.client.place_order(**params)
                    lvl.order_id = result.get("orderId") if isinstance(result, dict) else str(result)
                    lvl.active = True
                    self.logger.info(f"[OrderSync] ✅ Order gesetzt ID={lvl.order_id} @ {lvl.price} (TP={tp_price}, SL={sl_price})")
                    
                except Exception as e:
                    self.logger.error(f"[OrderSync] Fehler beim Setzen @ {lvl.price}: {e}")
            
            # Obsolete Orders aufräumen (optional)
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
