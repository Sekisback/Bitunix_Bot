# Bitunix GRID Bot – Konfigurationshandbuch

Dieses Handbuch erklärt **alle Parameter** der Grid-Bot-Konfiguration Schritt für Schritt.  
Jede Einstellung wird beschrieben mit:
- **Funktion** – was sie macht  
- **Empfohlene Werte** oder typische Beispiele  
- **Worauf der Trader achten muss**

---

## 🧠 1. SYSTEMKONFIGURATION

### `system.debug`
Aktiviert detaillierte Debug-Ausgaben in der Konsole und Log-Datei.  
**Empfehlung:** `true` für Tests, `false` für Livebetrieb.

### `system.update_interval`
Zeitintervall (Sekunden) zwischen den Grid-Updates im Hauptloop.  
**Empfehlung:** 3–10 Sekunden.

### `system.reconnect_interval`
Sekunden zwischen automatischen Verbindungsversuchen bei WebSocket-/API-Abbrüchen.  
**Empfehlung:** 5–15 Sekunden.

### `system.backtest_bars`
Maximale Anzahl historischer Candles für Backtests (Bitunix-Limit = 200).  
**Empfehlung:** 200.

### `system.timezone_offset`
Zeitzonen-Offset für Log-Ausgaben.  
**Beispiel:** `2` für Europa/Berlin (Sommerzeit).

### `system.log_to_file`
Aktiviert das Schreiben von Log-Dateien.  
**Empfehlung:** `true`.

### `system.log_level`
Log-Level für Konsolen- und Datei-Logs.  
**Werte:** `DEBUG`, `INFO`, `WARNING`, `ERROR`.

---

## 🗾 2. LOGGING-EINSTELLUNGEN

### `logging.log_dir`
Verzeichnis, in dem Log-Dateien gespeichert werden.  
**Empfehlung:** `logs`.

### `logging.filename_pattern`
Dateinamen-Muster für Log-Dateien.  
**Beispiel:** `GRID_{symbol}_{date}.log` → `GRID_ONDOUSDT_2025-10-10.log`.

### `logging.rotate_daily`
Tägliche Logrotation aktivieren.  
**Empfehlung:** `true`.

### `logging.max_size_mb`
Maximale Größe einer Log-Datei in MB.  
**Empfehlung:** 10.

---

## ⚙️ 3. TRADING-GRUNDEINSTELLUNGEN

### `trading.dry_run`
Simulationsmodus – keine echten Orders.  
**Empfehlung:** `true` zum Testen, `false` für Livebetrieb.

### `trading.grid_direction`
Handelsrichtung des Grids:  
- `long` → kauft unten, verkauft oben  
- `short` → verkauft oben, kauft unten  
- `both` → beidseitig (Hedge-Grid)

### `trading.client_id_prefix`
Präfix für Order-IDs (z. B. `GRID_BTC`).

---

## 📊 4. GRID-PARAMETER

### `grid.lower_price` / `grid.upper_price`
Definieren den Preisbereich des Grids.  
**Hinweis:** `upper_price` muss größer als `lower_price` sein.

### `grid.grid_levels`
Anzahl der Preisstufen zwischen unterer und oberer Grenze.  
**Empfehlung:** 10–30.

### `grid.grid_mode`
Verteilung der Preisstufen:  
- `arithmetic` → gleiche Abstände  
- `geometric` → prozentuale Abstände

### `grid.min_price_step`
Kleinster Preis-Schritt (Tick-Größe).  
**Beispiel:** `0.000001` für ONDO.

### `grid.base_order_size`
Grund-Ordergröße in USDT oder Coin-Einheiten.  
**Beispiel:** `50` für 50 USDT pro Order.

### `grid.active_reorder`
Nach Fill automatisch wieder Order am selben Level platzieren.  
**Empfehlung:** `true` für klassisches Grid-Trading.

### `grid.tp_mode`
Take-Profit-Berechnung:  
- `percent` → fester Prozentsatz  
- `next_grid` → nächstes Grid-Level als TP

### `grid.take_profit_pct`
Prozentwert für TP bei `tp_mode: percent`.  
**Beispiel:** `0.003` = 0,3 %.

### `grid.sl_mode`
Stop-Loss-Modus:  
- `percent`, `fixed`, `none`.

### `grid.stop_loss_pct`
Stop-Loss-Abstand in Prozent (bei `sl_mode: percent`).  
**Beispiel:** `0.01` = 1 %.

### `grid.rebalance_interval`
Intervall (Sekunden) für automatischen Grid-Neuaufbau.  
**Empfehlung:** `300` (5 Minuten) bis `3600` (1 Stunde).

---

## 💸 5. RISIKO & GEBÜHREN

### `risk.include_fees`
Wenn `true`, werden Handelsgebühren bei der Ordergröße berücksichtigt.

### `risk.fee_side`
Art der Gebührenberechnung:  
- `maker` → Limit-Order  
- `taker` → Marktorder.

### `risk.maker_fee_pct` / `risk.taker_fee_pct`
Prozentsätze der jeweiligen Gebühren.  
**Beispiel:** `0.0006` = 0,06 %.

---

## 💰 6. MARGIN & HEBELEINSTELLUNGEN

### `margin.mode`
Margin-Typ:  
- `isolated` → Risiko auf diese Position beschränkt  
- `cross` → gesamtes Konto-Guthaben als Sicherung.

### `margin.leverage`
Hebel für diese Strategie.  
**Beispiel:** `3` = 3x Hebel.

### `margin.auto_reduce_only`
Wenn `true`, werden nur bestehende Positionen reduziert (keine neuen).

---

## 🧬 7. STRATEGIEVERHALTEN

### `strategy.entry_on_touch`
Order wird direkt beim Erreichen des Grid-Preises platziert.  
**Empfehlung:** `true` für reaktiven Handel.

---

## 💳 8. Coin-spezifische Einstellungen (Beispiel ONDOUSDT)

Nur diese Werte anpassen:

```yaml
symbol: "ONDOUSDT"

grid:
  lower_price: 0.85
  upper_price: 0.95
  grid_levels: 20
  base_order_size: 50

risk:
  include_fees: true
  fee_side: "taker"

margin:
  mode: "isolated"
  leverage: 5
```

---

## ✅ Zusammenfassung für Trader

| Bereich | Wichtigste Punkte |
|----------|------------------|
| **System/Logging** | Logs aktivieren, `logs/`-Ordner vorhanden halten |
| **Trading** | Immer mit `dry_run=true` starten |
| **Grid** | Preisbereich und Levelzahl realistisch wählen |
| **Risk** | Gebühren korrekt angeben, sonst falsche Ordergrößen |
| **Margin** | Hebel nur moderat einsetzen |
| **Strategy** | `entry_on_touch=true` für aktive Reaktion, `false` für konservativ |

