import logging
from typing import Dict, Any, Optional


def place_order_dryrun(signal: dict, qty: float, balance: float, leverage: int, fee_pct: float):
    """
    Simuliert Order-Platzierung (DRY RUN)
    
    Args:
        signal: Trade Signal Dict
        qty: Order Menge in Coins
        balance: Verfügbares Guthaben
        leverage: Hebel
        fee_pct: Gebühr pro Trade-Seite
    """
    if not signal or signal["signal"] is None:
        logging.debug("❌ Kein Trade Signal")
        return
    
    # Order Details
    side = signal["signal"]  # "LONG" oder "SHORT"
    entry = signal["entry_price"]
    tp = signal["tp"]
    sl = signal["sl"]
    
    # Position Size
    position_size = qty * entry
    # Margin benötigt (= Kontogröße für diese Position)
    margin_used = position_size / leverage
       
    # Berechne Gewinn/Verlust auf MARGIN-Basis (nicht Position)
    if side == "LONG":
        # Preisdifferenz zu TP/SL
        tp_diff = tp - entry
        sl_diff = entry - sl
        
        # Gewinn/Verlust in USDT (auf gesamte Menge)
        profit_usdt = tp_diff * qty
        loss_usdt = sl_diff * qty
        
        # Prozent bezogen auf MARGIN
        profit_pct = (profit_usdt / margin_used) * 100
        loss_pct = (loss_usdt / margin_used) * 100
        
    else:  # SHORT
        # Preisdifferenz zu TP/SL
        tp_diff = entry - tp
        sl_diff = sl - entry
        
        # Gewinn/Verlust in USDT (auf gesamte Menge)
        profit_usdt = tp_diff * qty
        loss_usdt = sl_diff * qty
        
        # Prozent bezogen auf MARGIN
        profit_pct = (profit_usdt / margin_used) * 100
        loss_pct = (loss_usdt / margin_used) * 100
       
    # ins Log schreiben    
    logging.info("=" * 60)
    logging.info("🎯 DRY RUN - ORDER SIMULATION")
    logging.info("=" * 60)
    logging.info(f"Signal:         {side}")
    logging.info(f"Grund:          {signal['reason']}")
    logging.info(f"Entry Preis:    {entry:.5f} USDT")
    logging.info(f"Menge:          {qty} Coins")
    logging.info(f"Position Größe: {position_size:.2f} USDT")
    logging.info(f"Hebel:          {leverage}x")
    logging.info(f"Margin:         {margin_used:.2f} USDT")
    logging.info(f"Take Profit:    {tp:.5f} USDT")
    logging.info(f"Stop Loss:      {sl:.5f} USDT")
    logging.info(f"Potentieller Gewinn: +{profit_usdt:.2f} USDT ({profit_pct:.2f}% auf Margin)")
    logging.info(f"Potentieller Verlust: -{loss_usdt:.2f} USDT ({loss_pct:.2f}% auf Margin)")
    logging.info(f"Risk/Reward Ratio: 1:{(profit_usdt/loss_usdt):.2f}")
    logging.info("=" * 60)
    logging.info("⚠️ DRY RUN MODE - Keine echte Order platziert!")
    logging.info("=" * 60)


def place_order_live(client_pri, 
                    signal: dict, 
                    qty: float,
                    client_id: str,
                    symbol: str) -> Dict[str, Any]:
    """
    Platziert echte Order auf Bitunix (LIVE MODE)
    
    Args:
        client_pri: OpenApiHttpFuturePrivate Client
        signal: Trade Signal Dict
        qty: Order Menge in Coins
        client_id: Eindeutige Client Order ID
        symbol: Trading Symbol
    
    Returns:
        API Response (Order Details)
    
    Raises:
        Exception: Wenn Order fehlschlägt
    """
    if not signal or signal["signal"] is None:
        raise ValueError("Kein gültiges Signal für Live Order")
    
    side = signal["signal"]  # "LONG" oder "SHORT"
    entry = signal["entry_price"]
    tp = signal["tp"]
    sl = signal["sl"]
    
    # Bitunix Side Mapping
    if side == "LONG":
        order_side = "BUY"
    else:
        order_side = "SELL"
    
    logging.info("=" * 60)
    logging.info(f"🚀 LIVE ORDER - {side}")
    logging.info("=" * 60)
    logging.info(f"Symbol:      {symbol}")
    logging.info(f"Side:        {order_side}")
    logging.info(f"Menge:       {qty}")
    logging.info(f"Entry:       {entry:.5f}")
    logging.info(f"TP:          {tp:.5f}")
    logging.info(f"SL:          {sl:.5f}")
    logging.info(f"Client ID:   {client_id}")
    
    try:
        # Order platzieren mit TP/SL
        response = client_pri.place_order(
            symbol=symbol,
            side=order_side,
            order_type="MARKET",
            qty=str(qty),
            trade_side="OPEN",
            effect="GTC",
            client_id=client_id,
            reduce_only=False,
            # Take Profit
            tp_price=str(tp),
            tp_stop_type="LAST_PRICE",
            tp_order_type="MARKET",
            # Stop Loss
            sl_price=str(sl),
            sl_stop_type="LAST_PRICE",
            sl_order_type="MARKET"
        )
        
        logging.info("✅ Order erfolgreich platziert!")
        logging.info(f"Order ID:    {response.get('orderId', 'N/A')}")
        logging.info(f"Status:      {response.get('status', 'N/A')}")
        logging.info("=" * 60)
        
        return response
        
    except Exception as e:
        logging.error("=" * 60)
        logging.error(f"❌ FEHLER beim Order platzieren: {e}")
        logging.error("=" * 60)
        raise