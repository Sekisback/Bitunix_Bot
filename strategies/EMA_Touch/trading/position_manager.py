import logging
from typing import Dict, Any, Optional, List


def get_account_balance(client_pri, margin_coin: str = "USDT") -> float:
    """
    Liest verfügbares Guthaben
    
    Args:
        client_pri: OpenApiHttpFuturePrivate Client
        margin_coin: Margin Coin Symbol
    
    Returns:
        Verfügbares Guthaben
    """
    try:
        # Account Daten abrufen
        account = client_pri.get_account(margin_coin=margin_coin)
        # Verfügbarer Betrag
        balance = float(account.get("available", 0.0))
        logging.debug(f"Guthaben: {balance:.2f} {margin_coin}")
        return balance
    except Exception as e:
        logging.error(f"❌ Fehler beim Account-Abruf: {e}")
        return 0.0


def check_active_position(client_pri, symbol: str, margin_coin: str = "USDT") -> bool:
    """
    Prüft ob aktive Position existiert
    
    Args:
        client_pri: OpenApiHttpFuturePrivate Client
        symbol: Trading Symbol
        margin_coin: Margin Coin Symbol
    
    Returns:
        True wenn aktive Position vorhanden
    """
    try:
        positions = client_pri.get_positions(symbol=symbol, margin_coin=margin_coin)
        
        if positions and len(positions) > 0:
            # Prüfe ob irgendeine Position Menge > 0 hat
            has_position = any(
                float(pos.get('qty', 0)) > 0 
                for pos in positions
            )
            return has_position
        
        return False
        
    except Exception as e:
        logging.error(f"❌ Fehler beim Position-Check: {e}")
        return False


def get_position_details(client_pri, symbol: str, margin_coin: str = "USDT") -> Optional[Dict[str, Any]]:
    """
    Holt Details der aktuellen Position
    
    Args:
        client_pri: OpenApiHttpFuturePrivate Client
        symbol: Trading Symbol
        margin_coin: Margin Coin Symbol
    
    Returns:
        Position Details Dict oder None
    """
    try:
        positions = client_pri.get_positions(symbol=symbol, margin_coin=margin_coin)
        
        if positions and len(positions) > 0:
            # Finde aktive Position (qty > 0)
            for pos in positions:
                if float(pos.get('qty', 0)) > 0:
                    return pos
        
        return None
        
    except Exception as e:
        logging.error(f"❌ Fehler beim Abrufen der Position Details: {e}")
        return None


def setup_account(client_pri, symbol: str, leverage: int, margin_coin: str = "USDT"):
    """
    Richtet Account ein (Leverage, Margin Mode)
    
    Args:
        client_pri: OpenApiHttpFuturePrivate Client
        symbol: Trading Symbol
        leverage: Gewünschter Hebel
        margin_coin: Margin Coin Symbol
    """
    try:
        # Leverage setzen
        logging.info(f"⚙️ Setze Leverage auf {leverage}x für {symbol}")
        client_pri.change_leverage(
            symbol=symbol,
            leverage=leverage,
            margin_coin=margin_coin
        )
        
        # Margin Mode auf ISOLATION
        logging.info(f"⚙️ Setze Margin Mode auf ISOLATION für {symbol}")
        client_pri.change_margin_mode(
            symbol=symbol,
            margin_mode="ISOLATION",
            margin_coin=margin_coin
        )
        
        logging.info("✅ Account Setup abgeschlossen")
        
    except Exception as e:
        logging.error(f"❌ Fehler beim Account Setup: {e}")
        raise