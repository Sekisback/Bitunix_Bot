"""
=============================================================
🧠 Bitunix Trading Strategy Template
=============================================================
Dieses Skript dient als Vorlage für alle zukünftigen Strategien.
Jede Strategie:
 - nutzt ausschließlich den core/ API-Zugriff
 - kann 1:1 dupliziert und für verschiedene Coins angepasst werden
 - enthält ein einfaches Beispiel für eine Orderplatzierung
=============================================================
"""

import asyncio
import logging
import sys
import os

# WICHTIG: Pfad zum Hauptverzeichnis hinzufügen (VOR den anderen Imports!)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.config import Config
from core.open_api_http_future_private import OpenApiHttpFuturePrivate

# Logging-Konfiguration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


async def main():
    """
    Hauptfunktion der Strategie.
    Hier werden z. B. Marktlogik, Parameter, Trigger oder Cluster-Trading umgesetzt.
    """

    # === 🧩 Konfiguration der Strategie ===
    SYMBOL = "AKEUSDT"     # Coin-Paar
    SIDE = "BUY"           # BUY oder SELL
    ORDER_TYPE = "LIMIT"   # MARKET oder LIMIT
    QTY = "1000"           # Ordermenge
    PRICE = "0.0015"       # Nur für LIMIT erforderlich sonst None
    TP = None              # Optional: Take-Profit
    SL = "0.00148"         # Optional: Stop-Loss

    logging.info(f"Starte Strategie für {SYMBOL} → {SIDE} {ORDER_TYPE} {QTY}")

    # === 🔑 API-Client laden ===
    cfg = Config()
    client = OpenApiHttpFuturePrivate(cfg)

    # === 💰 Beispiel-Order senden ===
    try:
        result = client.place_order(
            symbol=SYMBOL,
            side=SIDE,
            order_type=ORDER_TYPE,
            qty=QTY,
            price=PRICE,
            tp_price=TP,
            sl_price=SL,
            trade_side="OPEN",   # Position eröffnen
            effect="GTC",        # Gültig bis Cancel
        )

        logging.info(f"✅ Order erfolgreich platziert: {result}")

    except Exception as e:
        logging.error(f"❌ Fehler bei Orderplatzierung: {e}")


if __name__ == "__main__":
    asyncio.run(main())
