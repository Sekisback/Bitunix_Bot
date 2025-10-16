#!/usr/bin/env python3
"""
GRID Bot Config GUI - Step 2: Chart mit Candlesticks
Rechts: Menu | Links: Live Chart
"""

import tkinter as tk
from tkinter import ttk
import sys
import threading
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
        
        # Daten
        self.coins = []
        self.selected_coin = tk.StringVar()
        self.selected_timeframe = tk.StringVar(value="15M")
        
        # Chart-Canvas
        self.chart_canvas = None
        
        # Timeframe-Mapping (GUI -> API)
        self.timeframe_map = {
            "1M": "1m",
            "5M": "5m",
            "15M": "15m",
            "1H": "1H",
            "4H": "4H",
            "1D": "1D"
        }
        
        # Style für alle Comboboxen
        style = ttk.Style()
        style.configure("TCombobox", 
                    padding=4)  # Innenabstand oben/unten
        
        # Optional: Schriftgröße auch über Style
        style.configure("TCombobox", 
                    font=("Arial", 12),
                    padding=8)
        
        # Layout erstellen
        self._create_layout()
        
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
        
        # Placeholder für Chart
        self.chart_label = tk.Label(
            self.chart_frame, 
            text="📊 Chart kommt hier hin...\n(Step 2)",
            font=("Arial", 24),
            bg="#1e1e1e",
            fg="#ffffff"
        )
        self.chart_label.pack(expand=True)
        
        # ===== RECHTS: Menu-Bereich =====
        self.menu_frame = tk.Frame(self.root, bg="#2b2b2b", width=300)
        self.menu_frame.pack(side=tk.RIGHT, fill=tk.Y)
        self.menu_frame.pack_propagate(False)  # Fixiere Breite
        
        # Menu-Inhalt
        self._create_menu()
    
    def _create_menu(self):
        """Erstellt das rechte Menu"""
        
        # Padding Container für alles
        content = tk.Frame(self.menu_frame, bg="#2b2b2b")
        content.pack(fill=tk.BOTH, expand=True, padx=15)
        
        # Header
        header = tk.Label(
            content,
            text="GRID Bot Config",
            font=("Arial", 16, "bold"),
            bg="#2b2b2b",
            fg="#ffffff",
            anchor="center"
        )
        header.pack(fill=tk.X, pady=(5, 0))
        
        # Separator
        ttk.Separator(content, orient='horizontal').pack(fill='x', pady=(5, 0))
        
        # === COIN SELECTOR ===
        coin_label = tk.Label(
            content,
            text="Coin auswählen:",
            font=("Arial", 12),
            bg="#2b2b2b",
            fg="#ffffff",
            anchor="w"
        )
        coin_label.pack(fill=tk.X, pady=(10, 5))
        
        self.coin_dropdown = ttk.Combobox(
            content,
            textvariable=self.selected_coin,
            state="readonly",
            width=32,  # 3 Buttons (10) + 2 Abstände (1+1)
            font=("Arial", 11)
        )
        self.coin_dropdown.pack(anchor="w")
        self.coin_dropdown.bind("<<ComboboxSelected>>", self._on_coin_select)
        
        # === TIMEFRAME SELECTOR ===
        timeframe_label = tk.Label(
            content,
            font=("Arial", 12),
            bg="#2b2b2b",
            fg="#ffffff",
            anchor="w"
        )
        timeframe_label.pack(fill=tk.X, pady=(0, 5))
        
        # Timeframe Buttons Frame (2 Reihen)
        tf_container = tk.Frame(content, bg="#2b2b2b")
        tf_container.pack(anchor="w", pady=(0, 20))
        
        # Erste Reihe: 1M, 5M, 15M
        tf_row1 = tk.Frame(tf_container, bg="#2b2b2b")
        tf_row1.pack(anchor="w")
        
        for tf in ["1M", "5M", "15M"]:
            btn = tk.Button(
                tf_row1,
                text=tf,
                width=10,
                font=("Arial", 10),
                bg="#3d3d3d",
                fg="#ffffff",
                activebackground="#4d4d4d",
                command=lambda t=tf: self._on_timeframe_select(t)
            )
            btn.pack(side=tk.LEFT, padx=2, pady=2)
        
        # Zweite Reihe: 1H, 4H, 1D
        tf_row2 = tk.Frame(tf_container, bg="#2b2b2b")
        tf_row2.pack(anchor="w")
        
        for tf in ["1H", "4H", "1D"]:
            btn = tk.Button(
                tf_row2,
                text=tf,
                width=10,
                font=("Arial", 10),
                bg="#3d3d3d",
                fg="#ffffff",
                activebackground="#4d4d4d",
                command=lambda t=tf: self._on_timeframe_select(t)
            )
            btn.pack(side=tk.LEFT, padx=2, pady=2)
               
        # === STATUS ===
        self.status_label = tk.Label(
            content,
            text="ℹ️ Bereit...",
            font=("Arial", 10),
            bg="#2b2b2b",
            fg="#888888",
            wraplength=260,
            justify=tk.LEFT,
            anchor="w"
        )
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X, pady=10)
    
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
            if "ONDOUSDT" in self.coins:
                self.coin_dropdown.set("ONDOUSDT")
            elif self.coins:
                self.coin_dropdown.set(self.coins[0])
            
            self._update_status(f"✅ {len(self.coins)} Coins geladen")
            
            # Initial Chart laden
            if self.coins:
                self._load_chart()
            
        except Exception as e:
            self._update_status(f"❌ Fehler: {e}")
            print(f"Error loading coins: {e}")
    
    def _on_coin_select(self, event):
        """Callback wenn Coin ausgewählt wird"""
        coin = self.selected_coin.get()
        tf = self.selected_timeframe.get()
        self._update_status(f"📊 {coin} | {tf}")
        
        # Chart laden
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
        """Lädt Daten im Hintergrund, zeichnet Chart im Main-Thread"""
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

            # ⚙️ Fix für FutureWarning
            df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)

            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df.dropna(inplace=True)

            if df.empty:
                self._update_status("❌ Keine gültigen Daten")
                return

            # Chart-Zeichnung IM MAIN-THREAD ausführen
            self.root.after(0, lambda: self._draw_chart(df, coin, tf))

        except Exception as e:
            self._update_status(f"❌ Fehler: {e}")
            import traceback; traceback.print_exc()
    
    def _draw_chart(self, df, coin, tf):
        """Zeichnet Chart im GUI-Thread (TradingView-Stil, kompakt ohne Rand)"""
        import matplotlib.pyplot as plt

        # Alten Canvas entfernen
        if self.chart_canvas:
            self.chart_canvas.get_tk_widget().destroy()
        if hasattr(self, "chart_label") and self.chart_label.winfo_exists():
            self.chart_label.destroy()

        # 🎨 Etwas hellerer Hintergrund (#121212 → #1c1c1c)
        fig, ax = plt.subplots(figsize=(9, 4.5), dpi=100, facecolor="#1c1c1c")
        ax.set_facecolor("#1c1c1c")


        # Chart plotten auf definierter Achse
        mpf.plot(
            df.sort_index(ascending=True),
            type="candle",
            style="nightclouds",
            ax=ax,
            volume=False,
            datetime_format="%H:%M",
            xrotation=0,
        )

        # === TradingView-Style ===
        for spine in ax.spines.values():
            spine.set_visible(False)

        ax.grid(True, axis="y", color="#333333", linestyle="-", linewidth=0.4)
        ax.grid(False, axis="x")

        ax.tick_params(colors="#cccccc", labelsize=8, pad=1)
        ax.title.set_color("#ffffff")

        # Kein zusätzlicher Rand
        fig.subplots_adjust(left=0.03, right=0.985, top=0.94, bottom=0.04)
        ax.margins(x=0.02, y=0.05)

        # Canvas in GUI einbetten
        self.chart_canvas = FigureCanvasTkAgg(fig, master=self.chart_frame)
        self.chart_canvas.draw()
        self.chart_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Status & Auto-Refresh
        self._update_status(f"✅ {coin} | {tf} | {len(df)} Bars")
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