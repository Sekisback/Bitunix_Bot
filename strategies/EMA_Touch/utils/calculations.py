import logging
from typing import Tuple


def get_symbol_info(client_pub, symbol: str) -> dict:
    """
    Holt Trading Pair Informationen für ein Symbol
    
    Args:
        client_pub: Public API Client
        symbol: Trading Symbol (z.B. "BTCUSDT")
    
    Returns:
        Dict mit Symbol-Infos (basePrecision, minTradeVolume, etc.)
    """
    try:
        # Trading Pair Info abrufen
        pair_info = client_pub.get_trading_pairs(symbols=symbol)
        
        # Prüfe ob Daten vorhanden
        if not pair_info or len(pair_info) == 0:
            raise ValueError(f"Keine Trading Pair Info für {symbol} gefunden")
        
        # Erste (und einzige) Position
        info = pair_info[0]
        
        # Extrahiere relevante Infos
        base_precision = int(info['basePrecision'])
        min_trade_volume = float(info['minTradeVolume'])
        
        logging.debug(f"📊 Symbol Info: Precision={base_precision}, Min Volume={min_trade_volume}")
        
        return {
            'base_precision': base_precision,
            'quote_precision': int(info['quotePrecision']),
            'min_trade_volume': min_trade_volume,
            'max_leverage': int(info['maxLeverage']),
            'min_leverage': int(info['minLeverage'])
        }
        
    except Exception as e:
        logging.error(f"❌ Fehler beim Abrufen der Symbol Info: {e}")
        raise


def calc_trade_parameters(client_pub, 
                         symbol: str, 
                         balance: float, 
                         current_price: float, 
                         leverage: int, 
                         tp_pct: float, 
                         sl_pct: float, 
                         total_fees: float,
                         fixed_qty: float = None) -> float:
    """
    Berechnet Trade-Parameter (qty in Coins)
    TP/SL werden später im Signal berechnet!
    
    Args:
        client_pub: Public API Client für Symbol Info
        symbol: Trading Symbol
        balance: Verfügbares Guthaben
        current_price: Aktueller Preis
        leverage: Hebel
        tp_pct: Take Profit Prozent (auf Margin)
        sl_pct: Stop Loss Prozent (auf Margin)
        total_fees: Gesamte Gebühren (Entry + Exit)
        fixed_qty: Feste Menge (None = automatisch berechnen)
    
    Returns:
        qty_coins: Menge in Coins
    """
    # Prüfe Preis
    if current_price <= 0:
        raise ValueError("current_price must be > 0")

    # Symbol Info abrufen (für Precision)
    symbol_info = get_symbol_info(client_pub, symbol)
    base_precision = symbol_info['base_precision']
    min_trade_volume = symbol_info['min_trade_volume']

    # Kaufkraft immer berechnen (für Debug-Ausgabe)
    buying_power = balance * leverage

    # === QTY BESTIMMEN ===
    if fixed_qty is not None:
        # Feste Menge aus Config verwenden
        qty_coins = round(fixed_qty, base_precision)
        logging.debug(f"📌 Nutze feste Menge aus Config: {qty_coins}")
    else:
        # Automatisch berechnen
        # Positionsgröße in Coins (ungerundet)
        qty_coins_raw = buying_power / current_price
        
        # Mit korrekter Precision runden
        qty_coins = round(qty_coins_raw, base_precision)
        
        # Mindestmenge prüfen
        if qty_coins < min_trade_volume:
            logging.warning(f"⚠️ Berechnete Menge {qty_coins} < minTradeVolume {min_trade_volume}")
            qty_coins = min_trade_volume
            logging.debug(f"📊 Menge auf Minimum angepasst: {qty_coins}")
    
    # Tatsächliche Positionsgröße in USDT
    position_size_usdt = qty_coins * current_price
    
    # Tatsächlich verwendete Margin
    margin_to_use = position_size_usdt / leverage

    # DEBUG Ausgabe (ohne TP/SL)
    logging.debug("=" * 60)
    logging.debug(f"📊 Trade-Berechnung:")
    logging.debug("=" * 60)
    logging.debug(f"Guthaben:       {balance:.2f} USDT")
    logging.debug(f"Hebel:          {leverage}x")
    logging.debug(f"Kaufkraft:      {buying_power:.2f} USDT")
    logging.debug(f"Preis:          {current_price:.5f} USDT")
    logging.debug(f"Precision:      {base_precision} Nachkommastellen")
    logging.debug(f"Min Volume:     {min_trade_volume}")
    logging.debug(f"Menge:          {qty_coins} Coins")
    logging.debug(f"Position:       {position_size_usdt:.2f} USDT")
    logging.debug(f"Margin:         {margin_to_use:.2f} USDT")
    logging.debug("=" * 60)

    return qty_coins


def generate_client_id(prefix: str) -> str:
    """
    Generiert eindeutige Client ID für Orders
    
    Format: {prefix}_{timestamp}_{random}
    Beispiel: EMA_TOUCH_ONDO_1728392847_a3f9d2b1
    
    Args:
        prefix: Prefix aus Config (z.B. "EMA_TOUCH_ONDO")
    
    Returns:
        Eindeutige Client ID
    """
    import time
    import uuid
    
    timestamp = int(time.time())
    random_id = uuid.uuid4().hex[:8]
    
    return f"{prefix}_{timestamp}_{random_id}"