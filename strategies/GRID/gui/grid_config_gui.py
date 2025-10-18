#!/usr/bin/env python3
"""
GRID Bot Config GUI - Step 2: Chart mit Candlesticks
Rechts: Menu | Links: Live Chart
"""

import tkinter as tk
from tkinter import ttk
import sys
import threading
import yaml
from pathlib import Path
import pandas as pd
import mplfinance as mpf
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


# Pfade
root_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(root_dir))

from core.config import Config
from core.open_api_http_future_public import OpenApiHttpFuturePublic


class GridConfigGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("GRID Bot Config GUI")
        # Sauberes Beenden abfangen
        self._running = True
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        
        # Maximiere Fenster beim Start (plattformübergreifend)
        self._maximize_window()
        
        # API Setup
        self.api_config = Config()
        self.client_pub = OpenApiHttpFuturePublic(self.api_config)
        
        # Pfade
        self.root_dir = Path(__file__).parent.parent   # eine Ebene über /gui/
        self.config_dir = self.root_dir / "configs"

        # Flags
        self.use_local_configs = False  # Start im API-Modus

        # Auswahl
        self.selected_coin = tk.StringVar()
        self.selected_timeframe = tk.StringVar(value="15M")
        
        # Chart-Canvas
        self.chart_canvas = None
        self._chart_initialized = False
        
        # Timeframe-Mapping (GUI -> API)
        self.timeframe_map = {
            "1M": "1m",
            "5M": "5m",
            "15M": "15m",
            "1H": "1h",
            "4H": "4h",
            "1D": "1d"
        }
        
        # Style für alle Comboboxen
        style = ttk.Style()
        style.configure("TCombobox", 
                    padding=4)  # Innenabstand oben/unten
        
        # Optional: Schriftgröße auch über Style
        style.configure("TCombobox", padding=6)
        
        # Layout erstellen
        self._create_layout()

        # ⭐ Chart-Canvas HIER erstellen (vor _load_coins)
        self._setup_chart()
        
        # Coins laden
        self._load_coins()
    
    def _maximize_window(self):
        """Fenstergröße setzen und mittig positionieren"""
        width, height = 1600, 900
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = int((screen_w / 2) - (width / 2))
        y = int((screen_h / 2) - (height / 2))
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    
    def _create_layout(self):
        """Erstellt das Hauptlayout: Links Chart, Rechts Menu"""
        
        # ===== LINKS: Chart-Bereich =====
        self.chart_frame = tk.Frame(self.root, bg="#1e1e1e")
        self.chart_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
       
        # ===== RECHTS: Menu-Bereich =====
        self.menu_frame = tk.Frame(self.root, bg="#1f1f1f", width=300)
        self.menu_frame.pack(side=tk.RIGHT, fill=tk.Y)
        self.menu_frame.pack_propagate(False)  # Fixiere Breite
        
        # Menu-Inhalt
        self._create_menu()
    
    def _create_menu(self):
        """Erstellt das rechte Menu"""
        
        # Padding Container für alles
        content = tk.Frame(self.menu_frame, bg="#1f1f1f")
        content.pack(fill=tk.BOTH, expand=True, padx=15)
        
        # Header
        header = tk.Label(
            content,
            text="GRID Bot Config",
            font=("Arial", 16, "bold"),
            bg="#1f1f1f",
            fg="#ffffff",
            anchor="center"
        )
        header.pack(fill=tk.X, pady=(5, 0))
        
        # Separator
        ttk.Separator(content, orient='horizontal').pack(fill='x', pady=(5, 0))

        # === COIN SELECTOR + MODE SWITCH (eine Zeile) ===
        coin_row = tk.Frame(content, bg="#2b2b2b")
        coin_row.pack(fill=tk.X, pady=(10, 10))

        self.coin_dropdown = ttk.Combobox(
            coin_row,
            textvariable=self.selected_coin,
            state="readonly",
            width=10,
            font=("Arial", 14)
        )
        self.coin_dropdown.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.coin_dropdown.bind("<<ComboboxSelected>>", self._on_coin_select)

        self.mode_button = tk.Button(
            coin_row,
            text="🌐",
            font=("Arial", 12),
            bg="#4a4a4a",
            fg="#ffffff",
            activebackground="#5c5c5c",
            relief="raised",
            bd=2,
            width=2,
            command=self._toggle_source_mode
        )
        self.mode_button.pack(side=tk.RIGHT, fill=tk.Y, pady=0)


        # === TIMEFRAME BUTTONS (alle 6 in einer Reihe, flach) ===
        tf_container = tk.Frame(content, bg="#2b2b2b")
        tf_container.pack(fill=tk.X, pady=(5, 20))

        # Alle 6 Buttons in einer Reihe mit Grid für gleiche Größe
        tf_row = tk.Frame(tf_container, bg="#2b2b2b")
        tf_row.pack(fill=tk.X)
        
        # Grid konfigurieren: 6 Spalten mit gleichem Gewicht
        for col in range(6):
            tf_row.grid_columnconfigure(col, weight=1, uniform="tf")
        
        # Button-Größe: flach
        btn_h = 1
        
        for i, tf in enumerate(["1M", "5M", "15M", "1H", "4H", "1D"]):
            btn = tk.Button(
                tf_row,
                text=tf,
                height=btn_h,
                font=("Arial", 10, "bold"),
                bg="#3a3a3a",
                fg="#ffffff",
                activebackground="#5c5c5c",
                relief="flat",
                command=lambda t=tf: self._on_timeframe_select(t)
            )
            # Grid-Position: Zeile 0, Spalte i, mit 2px Abstand
            padx = (0, 2) if i < 5 else (0, 0)
            btn.grid(row=0, column=i, sticky="ew", padx=padx)

                    
        # === STATUS ===
        self.status_label = tk.Label(
            content,
            text="ℹ️ Bereit...",
            font=("Arial", 10),
            bg="#1f1f1f",
            fg="#888888",
            wraplength=260,
            justify=tk.LEFT,
            anchor="w"
        )
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X, pady=10)

    def _setup_chart(self):
        """Erstellt Chart-Canvas einmalig"""
        import matplotlib.pyplot as plt
        
        self.fig, self.ax = plt.subplots(figsize=(13, 9), dpi=120, facecolor="#2e2e2e")
        self.ax.set_facecolor("#2e2e2e")
        
        self.chart_canvas = FigureCanvasTkAgg(self.fig, master=self.chart_frame)
        self.chart_canvas.get_tk_widget().configure(bg="#2e2e2e")
        self.chart_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    
    def _load_coins(self):
        """Lädt Coin-Liste von Bitunix API"""
        self._update_status("⏳ Lade Coins...")
        
        try:
            # API Call
            response = self.client_pub.get_trading_pairs()
            
            # Response parsen
            if isinstance(response, dict):
                data = response.get("data", [])
            elif isinstance(response, list):
                data = response
            else:
                data = []
            
            # Symbole extrahieren
            self.coins = [pair.get("symbol", "") for pair in data if "symbol" in pair]
            self.coins.sort()
            
            # Dropdown füllen
            self.coin_dropdown['values'] = self.coins
            
            # Default: BTCUSDT wenn vorhanden
            if "BTCUSDT" in self.coins:
                self.coin_dropdown.set("BTCUSDT")
            elif self.coins:
                self.coin_dropdown.set(self.coins[0])
            
            self._update_status(f"✅ {len(self.coins)} Coins geladen")
            
            # Initial Chart laden
            if self.coins:
                self._load_chart()
            
        except Exception as e:
            self._update_status(f"❌ Fehler: {e}")
            print(f"Error loading coins: {e}")
    
    def _toggle_source_mode(self):
        """Zwischen API-Mode und lokalem Config-Mode umschalten"""
        self.use_local_configs = not self.use_local_configs

        if self.use_local_configs:
            self.mode_button.config(text="📂")
            self._load_local_configs()
        else:
            self.mode_button.config(text="🌐")
            self._load_coins()


    def _load_local_configs(self):
        """Lädt YAML-Dateien aus dem Config-Ordner"""
        try:
            yaml_files = sorted([f.name for f in self.config_dir.glob("*.yaml")])
            self.coin_dropdown["values"] = yaml_files
            if yaml_files:
                self.coin_dropdown.set(yaml_files[0])
                self._on_coin_select(None)
            else:
                self._update_status("❌ Keine YAML-Dateien gefunden")
        except Exception as e:
            self._update_status(f"❌ Fehler beim Laden: {e}")


    def _on_coin_select(self, event):
        """Reagiert auf Auswahl im Dropdown"""
        name = self.selected_coin.get()

        if self.use_local_configs and name.endswith(".yaml"):
            file_path = self.config_dir / name
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f)

                coin = cfg.get("symbol", "").strip('"')
                if not coin:
                    self._update_status("⚠️ Kein Symbol in YAML gefunden")
                    return

                # Setze Coin im Dropdown, damit Chart den richtigen Wert nutzt
                self.selected_coin.set(coin)

                self._update_status(f"📂 {name} geladen ({coin})")

                # Chart für Symbol aus YAML laden
                self._load_chart()

            except Exception as e:
                self._update_status(f"❌ YAML-Fehler: {e}")
        else:
            # Normaler Coin von API
            coin = name
            self._update_status(f"📊 {coin} | {self.selected_timeframe.get()}")
            self._load_chart()

    
    def _on_timeframe_select(self, timeframe):
        """Callback wenn Timeframe ausgewählt wird"""
        self.selected_timeframe.set(timeframe)
        coin = self.selected_coin.get()
        self._update_status(f"📊 {coin} | {timeframe}")
        
        # Chart aktualisieren
        self._load_chart()    


    def _load_chart(self):
        """Startet Thread für API-Call"""
        threading.Thread(target=self._load_chart_thread, daemon=True).start()


    def _load_chart_thread(self):
        """Lädt Daten im Hintergrund, aktualisiert Chart im Main-Thread"""
        coin = self.selected_coin.get()
        tf = self.selected_timeframe.get()
        if not coin:
            return

        self._update_status(f"⏳ Lade Chart für {coin} | {tf}...")

        try:
            api_tf = self.timeframe_map.get(tf, "15m")
            response = self.client_pub.get_kline(symbol=coin, interval=api_tf, limit=200)
            if not response:
                self._update_status(f"❌ Keine Daten für {coin}")
                return

            df = pd.DataFrame(response)
            if "time" in df.columns:
                df.rename(columns={"time": "timestamp"}, inplace=True)
            if "quoteVol" in df.columns:
                df.rename(columns={"quoteVol": "volume"}, inplace=True)

            df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df.dropna(inplace=True)

            if df.empty:
                self._update_status("❌ Keine gültigen Daten")
                return

            # Update im Main-Thread
            self.root.after(0, lambda: self._update_chart(df, coin, tf))

        except Exception as e:
            self._update_status(f"❌ Fehler: {e}")
            import traceback; traceback.print_exc()


    def _update_chart(self, df, coin, tf):
        """Aktualisiert bestehenden Chart im TradingView-Style ohne Flackern"""
        import matplotlib.pyplot as plt

        # === Update ohne Neuzeichnen des Canvas ===
        self.ax.clear()

        # === Kerzenfarben definieren ===
        mc = mpf.make_marketcolors(
            up='#3172e5',     # ⬆️ steigende Candle
            down='#b8b8b8',   # ⬇️ fallende Candle
            wick={'up':'#3172e5','down':'#b8b8b8'},
            edge='inherit',
            volume='inherit'
        )

        # Stil mit diesen Farben kombinieren
        s = mpf.make_mpf_style(
            base_mpf_style='nightclouds',
            marketcolors=mc
        )

        # Format: Uhrzeit für < 1 Tag, Datum für 1D
        time_format = "%H:%M" if tf != "1D" else "%d.%b"

        mpf.plot(
            df.sort_index(ascending=True),
            type="candle",
            style=s,
            ax=self.ax,
            volume=False,
            datetime_format=time_format,
            xrotation=0
        )

        # === TradingView-Look ===
        # Kein Y-Label
        self.ax.set_ylabel("")

        # Kein Rahmen
        for spine in self.ax.spines.values():
            spine.set_visible(False)

        # Horizontale Linien leicht gestrichelt
        self.ax.grid(True, axis="y", color="#404040", linestyle="--", linewidth=0.6)
        # Vertikale Linien aus
        self.ax.grid(False, axis="x")

        # Achsen-Ticks
        self.ax.tick_params(colors="#cccccc", labelsize=8, pad=1)
        self.ax.title.set_color("#ffffff")

        # Weniger Rand unten
        self.ax.margins(x=0.02, y=0.05)
        self.fig.subplots_adjust(left=0.05, right=0.985, top=0.99, bottom=0.04)


        # Flackerfreies Redraw
        self.chart_canvas.draw()

        # Status + Auto-Refresh
        self._update_status(f"✅ {coin}  | {tf}  |")
        if self._running:
            self._after_id = self.root.after(30000, self._load_chart)

    def _update_status(self, message):
        """Aktualisiert Status-Label"""
        self.status_label.config(text=message)
        self.root.update_idletasks()
    
    def run(self):
        """Startet die GUI"""
        self.root.mainloop()

    def _on_close(self):
        """Beendet Auto-Refresh, Canvas und GUI vollständig"""
        self._running = False

        # geplanten Auto-Refresh abbrechen
        try:
            if hasattr(self, "_after_id"):
                self.root.after_cancel(self._after_id)
        except Exception:
            pass

        # Matplotlib-Canvas sauber schließen
        try:
            import matplotlib.pyplot as plt
            plt.close("all")
        except Exception:
            pass

        # Tk-Fenster zerstören
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass

        # Programm wirklich beenden
        import sys
        sys.exit(0)



if __name__ == "__main__":
    app = GridConfigGUI()
    app.run()