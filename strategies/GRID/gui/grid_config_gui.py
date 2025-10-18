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
        # Coin-Dropdown
        style.configure("TCombobox", padding=4, arrowsize=14, font=("Arial", 12))
        # Parameter-Dropdowns 
        style.configure("Grid.TCombobox", padding=(4, 1, 2, 1), relief="flat",  arrowsize=12, font=("Arial", 9))
        
        # Layout erstellen
        self._create_layout()

        # Chart-Canvas HIER erstellen (vor _load_coins)
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
        self.chart_frame = tk.Frame(
            self.root, 
            highlightthickness=1,
            highlightcolor="#4a4a4a",
            highlightbackground="#4a4a4a"
            )
        self.chart_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
       
        # ===== RECHTS: Menu-Bereich =====
        self.menu_frame = tk.Frame(
            self.root, 
            bg="#1f1f1f", 
            width=300,
            highlightthickness=1,
            highlightcolor="#4a4a4a",
            highlightbackground="#4a4a4a"
            )
        self.menu_frame.pack(side=tk.RIGHT, fill=tk.Y)
        self.menu_frame.pack_propagate(False)  # Fixiere Breite
        
        # Menu-Inhalt
        self._create_menu()
    
    def _create_menu(self):
        """Erstellt das rechte Menu"""
        
        # === Hauptcontainer ===
        content = tk.Frame(self.menu_frame, bg="#1f1f1f")
        content.pack(fill=tk.BOTH, expand=True, padx=15)
        
        # === HEADER ===
        header = tk.Label(
            content,
            text="------------------ GRID BOT CONFIG -------------------",
            font=("Arial", 12),
            bg="#1f1f1f",
            fg="#5c5c5c",
            anchor="center"
        )
        header.pack(fill=tk.X, pady=(5, 0))
        
        # === COIN SELECTOR + SPEICHERN + RESET + MODE BUTTONS ===
        coin_row = tk.Frame(content, bg="#2b2b2b")
        coin_row.pack(fill=tk.X, pady=(10, 10))

        # Coin-Auswahl (etwas schmaler, um Platz für 3 Buttons zu lassen)
        self.coin_dropdown = ttk.Combobox(
            coin_row,
            textvariable=self.selected_coin,
            state="readonly",
            width=12,
            font=("Arial", 13)
        )
        self.coin_dropdown.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.coin_dropdown.bind("<<ComboboxSelected>>", self._on_coin_select)

        # 💾 SPEICHERN
        self.save_button = tk.Button(
            coin_row,
            text="💾",
            font=("Arial", 12),
            bg="#4a4a4a",
            fg="#ffffff",
            activebackground="#5c5c5c",
            relief="raised",
            bd=0,
            width=2,
            command=self._save_current_config
        )
        self.save_button.pack(side=tk.RIGHT, fill=tk.Y, pady=0, padx=(0, 4))

        # 🔁 RESET (Defaults aus config_schema.yaml)
        self.reset_button = tk.Button(
            coin_row,
            text="🔁",
            font=("Arial", 12),
            bg="#4a4a4a",
            fg="#ffffff",
            activebackground="#5c5c5c",
            relief="raised",
            bd=0,
            width=2,
            command=self._reset_to_defaults
        )
        self.reset_button.pack(side=tk.RIGHT, fill=tk.Y, pady=0, padx=(0, 4))

        # 🌐 MODE SWITCH (API ↔ Local Config)
        self.mode_button = tk.Button(
            coin_row,
            text="🌐",
            font=("Arial", 12),
            bg="#4a4a4a",
            fg="#ffffff",
            activebackground="#5c5c5c",
            relief="raised",
            bd=0,
            width=2,
            command=self._toggle_source_mode
        )
        self.mode_button.pack(side=tk.RIGHT, fill=tk.Y, pady=0, padx=(0, 4))

        # === TIMEFRAME BUTTONS ===
        tf_container = tk.Frame(content, bg="#2b2b2b")
        tf_container.pack(fill=tk.X, pady=(5, 20))

        tf_row = tk.Frame(tf_container, bg="#2b2b2b")
        tf_row.pack(fill=tk.X)

        for col in range(6):
            tf_row.grid_columnconfigure(col, weight=1, uniform="tf")

        for i, tf in enumerate(["1M", "5M", "15M", "1H", "4H", "1D"]):
            btn = tk.Button(
                tf_row,
                text=tf,
                height=1,
                font=("Arial", 10, "bold"),
                bg="#3a3a3a",
                fg="#ffffff",
                activebackground="#5c5c5c",
                relief="flat",
                command=lambda t=tf: self._on_timeframe_select(t)
            )
            padx = (0, 2) if i < 5 else (0, 0)
            btn.grid(row=0, column=i, sticky="ew", padx=padx)

        # === GRID PARAMETER SECTION ===
        grid_section = tk.Frame(content, bg="#1f1f1f")
        grid_section.pack(fill=tk.X, pady=(0, 10))

        title = tk.Label(
            grid_section,
            text="------------------- GRID-PARAMETER -------------------",
            font=("Arial", 10),
            fg="#888888",
            bg="#1f1f1f",
            anchor="center"
        )
        title.pack(fill=tk.X, pady=(0, 5))

        form_frame = tk.Frame(grid_section, bg="#1f1f1f")
        form_frame.pack(fill=tk.X, pady=(0, 0))

        # === GRID DIRECTION (aus config_schema.yaml -> trading:) ===
        try:
            schema_path = self.root_dir / "gui" / "config_schema.yaml"
            with open(schema_path, "r", encoding="utf-8") as f:
                schema_data = yaml.safe_load(f)

            trading_schema = schema_data.get("trading", {})
            grid_dir_field = trading_schema.get("grid_direction", {})

            if isinstance(grid_dir_field, dict):
                grid_dir_options = grid_dir_field.get("options", []) or grid_dir_field.get("enum", [])
                grid_dir_label = grid_dir_field.get("label", "Grid Direction")
                grid_dir_default = grid_dir_field.get("default", None)
            else:
                grid_dir_options = []
                grid_dir_label = "Grid Direction"
                grid_dir_default = None

            if not grid_dir_options or not isinstance(grid_dir_options, list):
                grid_dir_options = ["long", "short"]
            if not grid_dir_default and grid_dir_options:
                grid_dir_default = grid_dir_options[0]

            grid_dir_display = [opt.upper() for opt in grid_dir_options]
            self.grid_dir_map = {opt.upper(): opt for opt in grid_dir_options}

        except Exception as e:
            print("⚠️ Fehler beim Laden von trading.grid_direction:", e)
            grid_dir_options = ["long", "short"]
            grid_dir_label = "Grid Direction"
            grid_dir_default = "long"
            grid_dir_display = [opt.upper() for opt in grid_dir_options]
            self.grid_dir_map = {opt.upper(): opt for opt in grid_dir_options}

        row = tk.Frame(form_frame, bg="#1f1f1f")
        row.pack(fill=tk.X, pady=5)

        default_display = grid_dir_default.upper() if grid_dir_default else ""
        self.grid_dir_var = tk.StringVar(value=default_display)
        grid_dir_dropdown = ttk.Combobox(
            row,
            textvariable=self.grid_dir_var,
            values=grid_dir_display,
            state="readonly",
            width=12,
            style="Grid.TCombobox"
        )
        grid_dir_dropdown.pack(side=tk.LEFT, fill=tk.X, expand=False, padx=(0, 6))

        lbl = tk.Label(
            row,
            text=grid_dir_label,
            font=("Arial", 10),
            bg="#1f1f1f",
            fg="#888888",
            anchor="w"
        )
        lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # === GRID MODE (aus config_schema.yaml -> grid:) ===
        try:
            schema_path = self.root_dir / "gui" / "config_schema.yaml"
            with open(schema_path, "r", encoding="utf-8") as f:
                schema_data = yaml.safe_load(f)

            grid_schema = schema_data.get("grid", {})
            grid_mode_field = grid_schema.get("grid_mode", {})

            if isinstance(grid_mode_field, dict):
                grid_mode_options = grid_mode_field.get("options", []) or grid_mode_field.get("enum", [])
                grid_mode_label = grid_mode_field.get("label", "Grid Mode")
                grid_mode_default = grid_mode_field.get("default", None)
            else:
                grid_mode_options = []
                grid_mode_label = "Grid Mode"
                grid_mode_default = None

            if not grid_mode_options or not isinstance(grid_mode_options, list):
                grid_mode_options = ["linear", "logarithmic"]
            if not grid_mode_default and grid_mode_options:
                grid_mode_default = grid_mode_options[0]

            grid_mode_display = [opt.upper() for opt in grid_mode_options]
            self.grid_mode_map = {opt.upper(): opt for opt in grid_mode_options}

        except Exception as e:
            print("⚠️ Fehler beim Laden von grid.grid_mode:", e)
            grid_mode_options = ["linear", "logarithmic"]
            grid_mode_label = "Grid Mode"
            grid_mode_default = "linear"
            grid_mode_display = [opt.upper() for opt in grid_mode_options]
            self.grid_mode_map = {opt.upper(): opt for opt in grid_mode_options}

        row = tk.Frame(form_frame, bg="#1f1f1f")
        row.pack(fill=tk.X, pady=5)

        default_display_mode = grid_mode_default.upper() if grid_mode_default else ""
        self.grid_mode_var = tk.StringVar(value=default_display_mode)
        grid_mode_dropdown = ttk.Combobox(
            row,
            textvariable=self.grid_mode_var,
            values=grid_mode_display,
            state="readonly",
            width=12,
            style="Grid.TCombobox"
        )
        grid_mode_dropdown.pack(side=tk.LEFT, fill=tk.X, expand=False, padx=(0, 6))

        lbl = tk.Label(
            row,
            text=grid_mode_label,
            font=("Arial", 10),
            bg="#1f1f1f",
            fg="#888888",
            anchor="w"
        )
        lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

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

    def _save_current_config(self):
            """Speichert aktuelle GUI-Werte in die aktive oder neue YAML-Datei"""
            try:
                symbol = self.selected_coin.get()
                if not symbol:
                    self._update_status("⚠️ Kein Symbol ausgewählt")
                    return

                # === GUI-Werte holen ===
                trading = {
                    "grid_direction": self.grid_dir_map.get(self.grid_dir_var.get(), "").lower()
                }
                grid = {
                    "grid_mode": self.grid_mode_map.get(self.grid_mode_var.get(), "").lower()
                }

                config_data = {
                    "symbol": symbol,
                    "trading": trading,
                    "grid": grid
                }

                # === Zielpfad bestimmen ===
                if self.use_local_configs and hasattr(self, "current_config_path") and self.current_config_path:
                    save_path = self.current_config_path
                else:
                    save_path = self.config_dir / f"{symbol}.yaml"

                # === YAML schreiben ===
                with open(save_path, "w", encoding="utf-8") as f:
                    yaml.dump(config_data, f, sort_keys=False, allow_unicode=True)

                self._update_status(f"💾 Gespeichert: {save_path.name}")

            except Exception as e:
                print(f"❌ Fehler beim Speichern: {e}")
                self._update_status("❌ Fehler beim Speichern der Config")


    def _reset_to_defaults(self):
        """Setzt GUI-Parameter auf die Default-Werte aus config_schema.yaml zurück"""
        try:
            schema_path = self.root_dir / "gui" / "config_schema.yaml"
            with open(schema_path, "r", encoding="utf-8") as f:
                schema_data = yaml.safe_load(f)

            trading = schema_data.get("trading", {})
            grid = schema_data.get("grid", {})

            # Grid Direction
            if "grid_direction" in trading and hasattr(self, "grid_dir_var"):
                default_val = trading["grid_direction"].get("default", None)
                if default_val:
                    self.grid_dir_var.set(default_val.upper())

            # Grid Mode
            if "grid_mode" in grid and hasattr(self, "grid_mode_var"):
                default_val = grid["grid_mode"].get("default", None)
                if default_val:
                    self.grid_mode_var.set(default_val.upper())

            # Aktive Config zurücksetzen
            self.current_config_path = None
            self.use_local_configs = False
            self._update_status("🔄 Auf Standardwerte zurückgesetzt")

        except Exception as e:
            print(f"⚠️ Fehler beim Zurücksetzen auf Defaults: {e}")
            self._update_status("⚠️ Fehler beim Zurücksetzen auf Defaults")


    def _toggle_source_mode(self):
        """Zwischen API-Mode und lokalem Config-Mode umschalten"""
        self.use_local_configs = not self.use_local_configs

        if self.use_local_configs:
            self.mode_button.config(text="📂")
            self._load_local_configs()
            self._update_status("📂 Lokale Configs geladen")
        else:
            self.mode_button.config(text="🌐")
            self._load_coins()
            self._update_status("🌐 API-Modus aktiviert")


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
            print(f"Fehler beim Laden lokaler Configs: {e}")


if __name__ == "__main__":
    app = GridConfigGUI()
    app.run()