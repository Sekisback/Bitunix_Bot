#!/usr/bin/env python3
"""
GRID Bot Config GUI - Step 1: Grundgerüst
Rechts: Menu | Links: Chart-Placeholder
"""

import tkinter as tk
from tkinter import ttk
import sys
from pathlib import Path

# Pfade
root_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(root_dir))

from core.config import Config
from core.open_api_http_future_public import OpenApiHttpFuturePublic


class GridConfigGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("GRID Bot Config GUI")
        
        # Maximiere Fenster beim Start (plattformübergreifend)
        self._maximize_window()
        
        # API Setup
        self.api_config = Config()
        self.client_pub = OpenApiHttpFuturePublic(self.api_config)
        
        # Daten
        self.coins = []
        self.selected_coin = tk.StringVar()
        self.selected_timeframe = tk.StringVar(value="15M")
        
        # Layout erstellen
        self._create_layout()
        
        # Coins laden
        self._load_coins()
    
    def _maximize_window(self):
        """Maximiert Fenster plattformübergreifend"""
        try:
            # Linux/Unix
            self.root.attributes('-zoomed', True)
        except:
            try:
                # Windows
                self.root.state('zoomed')
            except:
                # Fallback: Bildschirmgröße setzen
                screen_width = self.root.winfo_screenwidth()
                screen_height = self.root.winfo_screenheight()
                self.root.geometry(f"{screen_width}x{screen_height}+0+0")
    
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
        content.pack(fill=tk.BOTH, expand=True, padx=15, pady=20)
        
        # Header
        header = tk.Label(
            content,
            text="⚙️ GRID Bot Config",
            font=("Arial", 16, "bold"),
            bg="#2b2b2b",
            fg="#ffffff",
            anchor="w"
        )
        header.pack(fill=tk.X, pady=(0, 20))
        
        # Separator
        ttk.Separator(content, orient='horizontal').pack(fill='x', pady=10)
        
        # === COIN SELECTOR ===
        coin_label = tk.Label(
            content,
            text="📈 Coin auswählen:",
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
        self.coin_dropdown.pack(anchor="w", pady=(0, 20))
        self.coin_dropdown.bind("<<ComboboxSelected>>", self._on_coin_select)
        
        # === TIMEFRAME SELECTOR ===
        timeframe_label = tk.Label(
            content,
            text="⏱️ Timeframe:",
            font=("Arial", 12),
            bg="#2b2b2b",
            fg="#ffffff",
            anchor="w"
        )
        timeframe_label.pack(fill=tk.X, pady=(10, 5))
        
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
        
        # Separator
        ttk.Separator(content, orient='horizontal').pack(fill='x', pady=20)
        
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
            if "BTCUSDT" in self.coins:
                self.coin_dropdown.set("BTCUSDT")
            elif self.coins:
                self.coin_dropdown.set(self.coins[0])
            
            self._update_status(f"✅ {len(self.coins)} Coins geladen")
            
        except Exception as e:
            self._update_status(f"❌ Fehler: {e}")
            print(f"Error loading coins: {e}")
    
    def _on_coin_select(self, event):
        """Callback wenn Coin ausgewählt wird"""
        coin = self.selected_coin.get()
        tf = self.selected_timeframe.get()
        self._update_status(f"📊 {coin} | {tf}")
        print(f"Selected: {coin} @ {tf}")
        
        # TODO Step 2: Chart laden
    
    def _on_timeframe_select(self, timeframe):
        """Callback wenn Timeframe ausgewählt wird"""
        self.selected_timeframe.set(timeframe)
        coin = self.selected_coin.get()
        self._update_status(f"📊 {coin} | {timeframe}")
        print(f"Timeframe changed: {timeframe}")
        
        # TODO Step 2: Chart aktualisieren
    
    def _update_status(self, message):
        """Aktualisiert Status-Label"""
        self.status_label.config(text=message)
        self.root.update_idletasks()
    
    def run(self):
        """Startet die GUI"""
        self.root.mainloop()


if __name__ == "__main__":
    app = GridConfigGUI()
    app.run()