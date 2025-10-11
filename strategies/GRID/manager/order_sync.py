# file: strategies/GRID/manager/order_sync.py
import time
import logging
import asyncio
import sys
from pathlib import Path

GRID_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(GRID_DIR))
from utils.constants import PRICE_TOLERANCE
from utils.exceptions import OrderSyncError, OrderPlacementError, OrderCancellationError


class OrderSync:
    """Synchronisiert erwartete Grid-Orders mit echten Orders am Exchange"""

    def __init__(self, symbol, levels, logger: logging.Logger, client=None, size: float = None, 
                 grid_direction: str = "both", cancel_obsolete: bool = False):
        self.symbol = symbol
        self.levels = levels
        self.logger = logging.getLogger("OrderSync")
        self.client = client
        self.size = size or 0.0
        self.grid_direction = grid_direction
        self.fetch_orders_callback = None
        self._sync_lock = asyncio.Lock()
        self.cancel_obsolete = cancel_obsolete  # Obsolete Orders löschen?

    async def fetch_exchange_orders(self):
        """Holt offene Orders über Callback oder HTTP-Fallback"""
        if self.fetch_orders_callback:
            try:
                return self.fetch_orders_callback()
            except Exception as e:
                self.logger.error(f"fetch_orders_callback error: {e}")
                return []
        return []

    def match_orders(self, exchange_orders):
        """
        Vergleicht Exchange-Orders mit Grid-Levels
        Performance: O(n) durch Dict-Lookup
        """
        matched, missing, obsolete = [], [], []
        
        # Dict mit Preis als Key für O(1) Lookup
        order_dict = {}
        for o in exchange_orders:
            price = float(o.get("price", 0))
            rounded_price = round(price, 8)
            order_dict[rounded_price] = o
        
        # Prüfe alle Grid-Levels
        for lvl in self.levels:
            if not lvl.active and not lvl.filled:
                rounded_level_price = round(lvl.price, 8)
                matched_order = order_dict.get(rounded_level_price)
                
                # Fallback: Toleranz-Check
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
        
        # Finde obsolete Orders
        level_prices = {round(l.price, 8) for l in self.levels}
        for o in exchange_orders:
            price = round(float(o.get("price", 0)), 8)
            if price not in level_prices:
                is_in_grid = any(abs(price - lp) < PRICE_TOLERANCE for lp in level_prices)
                if not is_in_grid:
                    obsolete.append(o)
        
        return matched, missing, obsolete

    async def sync_orders(self, dry_run: bool = True):
        """Führt Synchronisation durch"""
        async with self._sync_lock:
            try:
                exchange_orders = await self.fetch_exchange_orders()
                matched, missing, obsolete = self.match_orders(exchange_orders)
                
                self.logger.info(
                    f"MATCHED={len(matched)} | MISSING={len(missing)} | OBSOLETE={len(obsolete)}"
                )
                
                if dry_run:
                    self.logger.info("Dry-Run aktiv")
                    for lvl in missing:
                        self.logger.debug(f"[DryRun] Order @ {lvl.price}")
                    for o in obsolete:
                        self.logger.debug(f"[DryRun] Cancel ID={o.get('orderId')}")
                    return {
                        "matched": len(matched),
                        "missing": len(missing),
                        "obsolete": len(obsolete),
                        "mode": "dry_run",
                    }
                
                # Real-Mode: Fehlende Orders setzen
                placed_count = 0
                for lvl in missing:
                    try:
                        if self.grid_direction == "long" and lvl.side == "SELL":
                            continue
                        if self.grid_direction == "short" and lvl.side == "BUY":
                            continue
                        
                        client_id = f"GRID_{lvl.index}_{int(time.time())}"
                        size = self.size or 0.0
                        if size <= 0.0:
                            continue
                        
                        trade_side = "OPEN"
                        tp_price = lvl.tp if lvl.tp else None
                        sl_price = lvl.sl if lvl.sl else None
                        
                        params = dict(
                            symbol=self.symbol, side=lvl.side, order_type="LIMIT", 
                            qty=size, price=lvl.price, trade_side=trade_side, 
                            tp_stop_type="MARK_PRICE", sl_stop_type="MARK_PRICE",
                            client_id=client_id,
                        )
                        
                        if tp_price:
                            params["tp_price"] = tp_price
                        if sl_price:
                            params["sl_price"] = sl_price
                        
                        self.logger.info(f"🟢 Order @ {lvl.price} | {lvl.side} | TP={tp_price} | SL={sl_price}")
                        
                        result = self.client.place_order(**params)
                        lvl.order_id = result.get("orderId") if isinstance(result, dict) else str(result)
                        lvl.active = True
                        placed_count += 1
                        self.logger.info(f"✅ Order ID={lvl.order_id}")
                        
                    except Exception as e:
                        raise OrderPlacementError(f"Order @ {lvl.price} fehlgeschlagen: {e}")
                
                # Obsolete Orders löschen (wenn aktiviert)
                cancelled_count = 0
                if self.cancel_obsolete and obsolete:
                    for o in obsolete:
                        try:
                            order_id = o.get("orderId")
                            self.logger.info(f"🗑️ Cancel ID={order_id}")
                            
                            # Cancel Order via API
                            cancel_result = self.client.cancel_orders(
                                symbol=self.symbol,
                                order_list=[{"orderId": order_id}]
                            )
                            
                            # Prüfe Erfolg
                            success_list = cancel_result.get("successList", [])
                            if success_list:
                                cancelled_count += 1
                                self.logger.info(f"✅ Cancelled ID={order_id}")
                            else:
                                failure_list = cancel_result.get("failureList", [])
                                if failure_list:
                                    error_msg = failure_list[0].get("errorMsg", "Unknown")
                                    self.logger.warning(f"⚠️ Cancel failed: {error_msg}")
                        
                        except Exception as e:
                            raise OrderCancellationError(f"Cancel ID={o.get('orderId')} fehlgeschlagen: {e}")
                
                return {
                    "matched": len(matched),
                    "missing": len(missing),
                    "obsolete": len(obsolete),
                    "placed": placed_count,
                    "cancelled": cancelled_count,
                    "mode": "live",
                }
            
            except (OrderPlacementError, OrderCancellationError) as e:
                self.logger.error(f"OrderSync Error: {e}")
                raise OrderSyncError(str(e))
            except Exception as e:
                self.logger.exception(f"Unexpected OrderSync error: {e}")
                raise OrderSyncError(f"Sync fehlgeschlagen: {e}")
