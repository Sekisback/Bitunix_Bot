# 🤖 Bitunix Trading Bot

Ein modularer, erweiterbarer Trading-Bot für die **Bitunix Futures API** mit WebSocket-Echtzeit-Datenverarbeitung.

Vollständig in **Python** entwickelt, nutzt ausschließlich offizielle REST- und WebSocket-Endpunkte.  
Event-basierte Architektur für minimale Latenz und maximale Stabilität.

---

## ✨ Features

- ✅ **Echtzeit WebSocket-Datenverarbeitung** - Event-basiert statt Polling
- ✅ **Automatisches Reconnect** - Stabile Verbindung auch bei Netzwerkproblemen
- ✅ **DRY RUN Mode** - Realistische Simulation mit TP/SL-Tracking
- ✅ **Multi-Coin Support** - Separate Config pro Symbol
- ✅ **Modulare Strategien** - Indicators, Signals, Trading-Logic getrennt
- ✅ **Position-Management** - Verhindert Doppel-Positionen automatisch
- ✅ **Umfangreiches Logging** - Debug-Mode für Entwicklung

---

## 🧩 Projektstruktur

```
Bitunix_Trading_Bot/
│
├── core/                        # API-Module (direkt an Bitunix API angebunden)
│   ├── config.py                # Lädt API-Keys & Verbindungsdaten
│   ├── open_api_http_future_private.py   # Private Order-Methoden
│   ├── open_api_http_future_public.py    # Öffentliche Marktendpunkte
│   ├── open_api_ws_future_public.py      # WebSocket Public (mit Auto-Reconnect)
│   ├── open_api_ws_future_private.py     # WebSocket Private
│   └── error_codes.py           # Fehlerhandling
│
├── strategies/                  # Trading-Strategien
│   └── EMA_Touch/               # EMA21 Touch-Strategie
│       ├── bot.py               # Haupt-Bot (WebSocket-basiert)
│       ├── config/              # Coin-Configs (YAML)
│       │   ├── ONDOUSDT.yaml
│       │   ├── XRPUSDT.yaml
│       │   └── BTCUSDT.yaml
│       ├── indicators/          # Technische Indikatoren
│       │   ├── ema.py           # EMA-Berechnung
│       │   └── adx.py           # ADX Trendfilter
│       ├── signals/             # Signal-Generierung
│       │   ├── signal_generator.py
│       │   └── ema21_touch.py   # EMA21 Touch-Detection
│       ├── trading/             # Order-Management
│       │   ├── order_execution.py
│       │   └── position_manager.py
│       └── utils/               # Hilfsfunktionen
│           ├── config_loader.py
│           ├── kline_fetcher.py
│           └── websocket_kline_manager.py  # WebSocket Kline-Handler
│
├── test_files/                  # Test-Scripts
├── .gitignore
├── requirements.txt
└── README.md
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
source .venv/bin/activate  # Linux/Mac
# oder
.venv\Scripts\activate     # Windows
```

### 3️⃣ Abhängigkeiten installieren
```bash
pip install -r requirements.txt
```

### 4️⃣ Konfiguration

#### API-Keys (config.yaml im Root)
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

⚠️ **Wichtig:** `config.yaml` steht in `.gitignore` - niemals committen!

---

## 🚀 EMA Touch Strategie

### Strategie-Konzept

Die **EMA21 Touch-Strategie** handelt präzise Berührungen der 21-EMA-Linie:

**Entry-Bedingungen:**
- Preis berührt EMA21 (Abstand < 0.05%)
- EMA-Hierarchie bestätigt Trend (21 > 50 > 200 für LONG)
- ADX > 25 (starker Trend)
- EMA-Distanz-Filter aktiv

**Exit:**
- Take Profit: +1.0% (konfigurierbar)
- Stop Loss: -0.5% (konfigurierbar)

### Bot starten

```bash
cd strategies/EMA_Touch
python bot.py --config ONDOUSDT
```

Weitere Coins:
```bash
python bot.py --config XRPUSDT
python bot.py --config BTCUSDT
```

### Config-Datei (Beispiel: ONDOUSDT.yaml)

```yaml
symbol: "ONDOUSDT"

trading:
  interval: "1m"           # Zeitrahmen
  leverage: 5              # Hebel
  dry_run: true            # Simulation (true) oder LIVE (false)
  fixed_qty: null          # Fixe Menge oder null für Auto-Berechnung
  client_id_prefix: "EMA"

indicators:
  ema_fast: 21             # Schnelle EMA
  ema_slow: 50             # Mittlere EMA
  ema_trend: 200           # Trend-EMA
  adx_period: 14           # ADX Periode

trend_filter:
  use_filter: true         # Trendfilter aktivieren
  adx_threshold: 25        # Minimaler ADX-Wert
  ema_distance_threshold: 0.3  # Max Abstand zwischen EMAs (%)

entry:
  touch_threshold_pct: 0.05  # EMA Touch-Zone (%)

risk:
  tp_pct: 0.01             # Take Profit (1%)
  sl_pct: 0.005            # Stop Loss (0.5%)
  fee_pct: 0.0006          # Trading Fees (0.06%)

system:
  backtest_bars: 250       # Buffer für Indikatoren
  timezone_offset: 2       # Europa (MESZ)
  debug: true              # Debug-Logs aktivieren
```

### DRY RUN vs LIVE Mode

**DRY RUN (Simulation):**
```yaml
trading:
  dry_run: true
```
- Keine echten Orders
- Simuliert Position mit TP/SL
- Berechnet theoretische Gewinne/Verluste
- Perfekt für Tests!

**LIVE Mode:**
```yaml
trading:
  dry_run: false
```
- ⚠️ **ECHTE ORDERS!**
- Nutzt echtes Kapital
- Nur nach gründlichen Tests verwenden!

---

## 🔧 Eigene Strategie erstellen

### 1. Neuen Strategie-Ordner anlegen
```bash
mkdir -p strategies/MeineStrategie
cd strategies/MeineStrategie
```

### 2. Module erstellen
```
MeineStrategie/
├── bot.py              # Haupt-Bot
├── config/             # YAML-Configs
├── indicators/         # Deine Indikatoren
├── signals/            # Signal-Logik
├── trading/            # Order-Execution
└── utils/              # Hilfsfunktionen
```

### 3. WebSocket-Manager nutzen

```python
from utils.websocket_kline_manager import WebSocketKlineManager

async def on_new_kline(kline: dict, df: pd.DataFrame):
    """Wird bei jeder neuen Kerze aufgerufen"""
    print(f"Neue Kerze: {kline['close']}")
    
    # Deine Logik hier...
    signal = generate_signal(df)
    if signal:
        place_order(signal)

# Manager erstellen
manager = WebSocketKlineManager(
    symbol="BTCUSDT",
    interval="1m",
    buffer_size=200,
    on_kline_callback=on_new_kline
)

# Starten
await manager.start()
```

---

## 📊 Monitoring & Logs

**Log-Dateien:**
```
logs/
└── EMA_Touch_ONDOUSDT_2025-10-09.log
```

**Debug-Mode aktivieren:**
```yaml
system:
  debug: true
```

**Wichtige Log-Meldungen:**
- `🕯️ Neue Kerze` - Kerze empfangen
- `✅ Signal gefunden` - Entry-Signal erkannt
- `🔒 Aktive Position` - Position läuft
- `✅ TP erreicht` - Take Profit getriggert
- `❌ SL erreicht` - Stop Loss getriggert
- `🔄 Re-Subscribe` - WebSocket Reconnect

---

## ⚠️ Sicherheitshinweise

- ✅ Immer erst **DRY RUN** testen
- ✅ Niemals API-Keys ins Git committen
- ✅ Leverage vorsichtig wählen (Start: 2-3x)
- ✅ Stop Loss IMMER aktiviert lassen
- ✅ Klein starten, dann skalieren
- ⚠️ Trading birgt Verlustrisiken!

---

**Happy Trading!** 📈