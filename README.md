# 🤖 Bitunix Trading Bot V2

Ein modularer, erweiterbarer Trading-Bot für die **Bitunix Futures API**.  
Dieser Bot wurde vollständig in **Python** entwickelt und nutzt ausschließlich offizielle REST- und WebSocket-Endpunkte.  
Ziel: Eine klare, wartbare Struktur für den produktiven Handel, Tests und Cluster-Setups.

---

## 🧩 Projektstruktur

```
Bitunix_Trading_Bot/
│
├── core/                        # Zentrale API-Module (unverändert, direkt an Bitunix angebunden)
│   ├── config.py                # Lädt API-Keys & Verbindungsdaten
│   ├── open_api_http_future_private.py   # Alle privaten Order-Methoden (place, modify, cancel, etc.)
│   ├── open_api_http_future_public.py    # Öffentliche Marktendpunkte (Ticker, Depth, Funding)
│   ├── open_api_http_sign.py    # Signaturerstellung für REST
│   ├── open_api_ws_future_public.py      # Öffentliche WebSocket-Verbindungen
│   ├── open_api_ws_future_private.py     # Private WebSocket-Verbindungen (Orders, Positionen)
│   ├── open_api_ws_sign.py      # Signaturerstellung für WS
│   ├── error_codes.py           # Einheitliches Fehlerhandling
│   └── README.md                # Kurze Beschreibung der Core-Module
│
├── strategies/                  # Deine Strategien (jeder Coin, jede Logik als eigene Datei)
│   ├── strategy_template.py     # Universelles Template zum Erstellen neuer Strategien
│   ├── test_limitbuy.py         # Beispiel: Limit-Buy mit TP/SL
│   └── ...
│
├── .gitignore                   # Ignoriert Secrets, Cache, venv etc.
├── requirements.txt             # Python-Abhängigkeiten
└── README.md                    # (diese Datei)
```

---

## ⚙️ Installation

### 1️⃣ Repository klonen
```bash
git clone https://github.com/Sekisback/Bitunix_Bot.git
cd Bitunix_Bot
```

### 2️⃣ Virtuelle Umgebung erstellen
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3️⃣ Abhängigkeiten installieren
```bash
pip install -r requirements.txt
```

### 4️⃣ Konfiguration vorbereiten

Erstelle im Projektordner eine Datei **`config.yaml`**:

```yaml
credentials:
  api_key: "DEIN_API_KEY"
  secret_key: "DEIN_SECRET_KEY"

http:
  uri_prefix: "https://fapi.bitunix.com"

websocket:
  public_uri: "wss://ws.bitunix.com/market"
  private_uri: "wss://ws.bitunix.com/private"
  reconnect_interval: 5
```

---

## 🚀 Beispiel: Limit-Buy-Strategie

Datei: `strategies/test_limitbuy.py`

```python
import asyncio
import logging
from core.config import Config
from core.open_api_http_future_private import OpenApiHttpFuturePrivate

async def main():
    SYMBOL = "AKEUSDT"
    QTY = "1000"
    PRICE = "0.0015"
    TP = "0.0017"
    SL = "0.00148"

    cfg = Config()
    client = OpenApiHttpFuturePrivate(cfg)

    result = client.place_order(
        symbol=SYMBOL,
        side="BUY",
        order_type="LIMIT",
        qty=QTY,
        price=PRICE,
        tp_price=TP,
        sl_price=SL,
        trade_side="OPEN",
        effect="GTC"
    )

    print(result)

if __name__ == "__main__":
    asyncio.run(main())
```

Start:
```bash
python3 strategies/test_limitbuy.py
```

---

## 🧠 Prinzip

- **Keine zentrale Steuerung:** Jede Strategie ist ein eigenständiges Skript.  
- **Klarer Core:** Nur `core/` enthält API-Funktionalität.  
- **Einheitliche Schnittstelle:** Alle Strategien arbeiten mit denselben Defs.  
- **Einfache Erweiterung:** Kopiere `strategy_template.py`, ändere Parameter → neue Strategie.

---

## 🧩 Beispiel für Cluster-Trading

Wenn du mehrere Coins parallel handeln willst:

```
strategies/
├── cluster_btc.py
├── cluster_eth.py
└── cluster_ake.py
```

Jede Datei kann eigenständig gestartet werden:
```bash
python3 strategies/cluster_btc.py
python3 strategies/cluster_eth.py
```

---

## ⚠️ Sicherheitshinweis

- Verwende **niemals** deine echten API-Keys in öffentlichen Repos.  
- Für Tests: nutze **Sub-Accounts oder Sandbox-Modus** (sofern verfügbar).  
- Implementiere vor Live-Handel eine **Dry-Run-Option**.

---

## 📜 Lizenz

MIT License  
(c) 2025 Sekisback  

---

## ❤️ Mitwirken

Pull Requests und Issues sind willkommen.  
Wenn du Erweiterungen (z. B. Trailing Stop, Grid-Trading, Cluster-Synchronisierung) planst,  
kannst du eine neue Branch öffnen und deine Änderung vorschlagen.

---

## 📬 Kontakt

**GitHub:** [Sekisback](https://github.com/Sekisback)  
**Projekt:** [Bitunix_Bot](https://github.com/Sekisback/Bitunix_Bot)
