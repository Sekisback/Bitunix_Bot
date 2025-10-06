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
    ORDER_ID    = None                  # z. B. "1975173216989917184"
    CLIENT_ID   = "Bitunixbot_123"      # ← KORRIGIERT: jetzt clientId
    NEW_PRICE   = "0.00155"             # Neuer Preis (required für LIMIT)
    NEW_QTY     = "2000"                # Neue Menge (required)
    NEW_TP      = None                  # Optional: neuer TP-Trigger
    NEW_SL      = "0.00149"             # Optional: neuer SL-Trigger

    logging.info(f"Starte Order-Modification für {CLIENT_ID}")

    # === API-Client laden ===
    cfg = Config()
    client = OpenApiHttpFuturePrivate(cfg)

    try:
        # === Request vorbereiten ===
        result = client.modify_order(
            order_id=ORDER_ID,
            client_id=CLIENT_ID,              # ← KORRIGIERT
            price=NEW_PRICE,
            qty=NEW_QTY,
            tp_price=NEW_TP,                  # ← KORRIGIERT
            sl_price=NEW_SL                   # ← KORRIGIERT
        )

        logging.info(f"✅ Order erfolgreich geändert: {result}")

    except Exception as e:
        logging.error(f"❌ Fehler bei Order-Änderung: {e}")

if __name__ == "__main__":
    asyncio.run(main())