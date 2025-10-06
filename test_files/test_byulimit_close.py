import asyncio
import logging
import sys
import os

# WICHTIG: Pfad zum Hauptverzeichnis hinzufügen
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.config import Config
from core.open_api_http_future_private import OpenApiHttpFuturePrivate

# Logging-Konfiguration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

async def main():
    # === Konfiguration ===
    SYMBOL      = "AKEUSDT"
    ORDER_ID    = None 
    CLIENT_ID   = "Bitunixbot_123" # Mit Client-ID stornieren
    
    logging.info(f"Starte Order-Stornierung für {SYMBOL}")

    # === API-Client laden ===
    cfg = Config()
    client = OpenApiHttpFuturePrivate(cfg)

    try:
        # === Order-Liste erstellen ===
        order_list = []
        
        # Entweder Order-ID ODER Client-ID verwenden
        if ORDER_ID:
            order_list.append({"orderId": ORDER_ID})
        elif CLIENT_ID:
            order_list.append({"clientId": CLIENT_ID})
        else:
            raise ValueError("Entweder ORDER_ID oder CLIENT_ID muss gesetzt sein")
        
        # === Orders stornieren ===
        result = client.cancel_orders(
            symbol=SYMBOL,
            order_list=order_list
        )

        # === Ergebnis auswerten ===
        success_list = result.get("successList", [])
        failure_list = result.get("failureList", [])

        if success_list:
            logging.info(f"✅ Erfolgreich storniert: {success_list}")
        
        if failure_list:
            for fail in failure_list:
                logging.error(
                    f"❌ Fehler bei Order {fail.get('orderId') or fail.get('clientId')}: "
                    f"{fail.get('errorMsg')} (Code: {fail.get('errorCode')})"
                )

    except Exception as e:
        logging.error(f"❌ Fehler bei Order-Stornierung: {e}")

if __name__ == "__main__":
    asyncio.run(main())