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
        self.current_config_path = None


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
        # Einheitliches, neutrales Theme aktivieren
        style.theme_use("clam")
        # Coin-Dropdown
        style.configure("TCombobox", padding=4, arrowsize=14, font=("Arial", 12))

        # Style für Comboboxen
        style.configure(
            "Grid.TCombobox",
            font=("Arial", 10),
            padding=(6, 4, 6, 4),
            fieldbackground="#d9d9d9",
            background="#d9d9d9",
            foreground="#000000",
            arrowsize=12
        )
        style.map("Grid.TCombobox",
                font=[("readonly", ("Arial", 10))],
                fieldbackground=[("readonly", "#d9d9d9")],
                background=[("readonly", "#d9d9d9")],
                foreground=[("readonly", "#000000")])

        # Style für Entry-Felder
        style.configure(
            "Grid.TEntry",
            font=("Arial", 10, "bold"),
            padding=(6, 4, 6, 4),
            fieldbackground="#d9d9d9",
            foreground="#000000",
            relief="flat"
        )
                
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
            width=320,
            highlightthickness=1,
            highlightcolor="#4a4a4a",
            highlightbackground="#4a4a4a"
            )
        self.menu_frame.pack(side=tk.RIGHT, fill=tk.Y)
        self.menu_frame.pack_propagate(False)  # Fixiere Breite
        
        # Menu-Inhalt
        self._create_menu()
    
    def _create_menu(self):
        """Erstellt das rechte Menu mit funktionierender Scrollbar"""
        
        # === Hauptcontainer ===
        content = tk.Frame(self.menu_frame, bg="#1f1f1f")
        content.pack(fill=tk.BOTH, expand=True, padx=15)
        
        # === HEADER (oben fixiert) ===
        header = tk.Label(
            content,
            text="------------------ GRID BOT CONFIG -------------------",
            font=("Arial", 12),
            bg="#1f1f1f",
            fg="#5c5c5c",
            anchor="center"
        )
        header.pack(side=tk.TOP, fill=tk.X, pady=(5, 0))
        
        # === COIN SELECTOR + BUTTONS (oben fixiert) ===
        coin_row = tk.Frame(content, bg="#2b2b2b")
        coin_row.pack(side=tk.TOP, fill=tk.X, pady=(10, 10))

        self.coin_dropdown = ttk.Combobox(
            coin_row,
            textvariable=self.selected_coin,
            state="readonly",
            width=12,
            font=("Arial", 13)
        )
        self.coin_dropdown.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.coin_dropdown.bind("<<ComboboxSelected>>", self._on_coin_select)

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

        # === TIMEFRAME BUTTONS (oben fixiert) ===
        tf_container = tk.Frame(content, bg="#2b2b2b")
        tf_container.pack(side=tk.TOP, fill=tk.X, pady=(5, 10))

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

        # === STATUS-LABEL (unten fixiert) ===
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
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 5))

        # =========================================================================
        # SCROLLBARER BEREICH (nimmt restlichen Platz in der Mitte)
        # =========================================================================
        
        # Canvas direkt in content
        canvas = tk.Canvas(content, bg="#1f1f1f", highlightthickness=0)
        
        # Scrollbar (schmaler Balken)
        scrollbar = tk.Scrollbar(
            content, 
            orient="vertical", 
            command=canvas.yview,
            width=8,
            bg="#4a4a4a"
        )
        
        # Scrollable Frame
        scrollable_frame = tk.Frame(canvas, bg="#1f1f1f")
        
        # Canvas Window erstellen
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        
        # Scrollregion updaten
        def update_scroll():
            canvas.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all"))
        
        scrollable_frame.bind("<Configure>", lambda e: update_scroll())
        
        # Canvas-Breite an Window anpassen
        def resize_canvas(event):
            canvas.itemconfig(canvas_window, width=event.width)
        
        canvas.bind("<Configure>", resize_canvas)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Canvas und Scrollbar packen (mit rechtem Padding)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))  # 5px rechts

        # =========================================================================
        # PARAMETER IN scrollable_frame
        # =========================================================================
        
        # === GRID PARAMETER (vollständig YAML-basiert) ===
        grid_section = tk.Frame(scrollable_frame, bg="#1f1f1f")
        grid_section.pack(fill=tk.X, pady=(5, 10))

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
        form_frame.pack(fill=tk.X, pady=(0, 0), padx=(0, 2))

        # === Schema einmalig laden ===
        schema_path = self.root_dir / "gui" / "config_schema.yaml"
        with open(schema_path, "r", encoding="utf-8") as f:
            schema_data = yaml.safe_load(f)

        # --- Hilfsfunktion: Dropdown-Reihe ---
        def create_dropdown_row(parent, section_dict, field_name, var_attr, map_attr):
            field = section_dict.get(field_name, {})
            label_text = field.get("label", field_name.replace("_", " ").title())
            options = field.get("options", field.get("enum", []))
            default = field.get("default", options[0] if options else "")

            row = tk.Frame(parent, bg="#1f1f1f")
            row.pack(fill=tk.X, pady=2)

            lbl = tk.Label(
                row,
                text=label_text,
                font=("Arial", 10),
                bg="#1f1f1f",
                fg="#888888",
                anchor="w",
                width=18
            )
            lbl.pack(side=tk.LEFT, fill=tk.X)

            display_opts = [str(opt).upper() for opt in options]
            setattr(self, map_attr, {opt.upper(): opt for opt in options})

            var = tk.StringVar(value=str(default).upper())
            setattr(self, var_attr, var)

            cb = ttk.Combobox(
                row,
                textvariable=var,
                values=display_opts,
                state="readonly",
                width=18,
                style="Grid.TCombobox"
            )
            cb.pack(side=tk.RIGHT, ipadx=6, ipady=1)

        # === GRID DIRECTION (aus YAML: trading.grid_direction) ===
        trading_schema = schema_data.get("trading", {})
        create_dropdown_row(form_frame, trading_schema, "grid_direction",
                            "grid_dir_var", "grid_dir_map")

        # === GRID MODE (aus YAML: grid.grid_mode) ===
        grid_schema = schema_data.get("grid", {})
        create_dropdown_row(form_frame, grid_schema, "grid_mode",
                            "grid_mode_var", "grid_mode_map")

        # === UPPER PRICE (aus YAML: grid.upper_price) ===
        upper_field = grid_schema.get("upper_price", {})
        upper_label = upper_field.get("label", "Upper Price")
        upper_default = upper_field.get("default", 0.0)

        row = tk.Frame(form_frame, bg="#1f1f1f")
        row.pack(fill=tk.X, pady=4)

        tk.Label(
            row,
            text=upper_label,
            font=("Arial", 10),
            bg="#1f1f1f",
            fg="#888888",
            anchor="w",
            width=18
        ).pack(side=tk.LEFT, fill=tk.X)

        self.upper_price_var = tk.DoubleVar(value=float(upper_default))
        validate_float = (self.root.register(lambda v: v.replace(".", "", 1).isdigit() or v == ""), "%P")

        ttk.Entry(
            row,
            textvariable=self.upper_price_var,
            width=18,
            style="Grid.TEntry",
            validate="key",
            validatecommand=validate_float
        ).pack(side=tk.RIGHT)

        # === LOWER PRICE (aus YAML: grid.lower_price) ===
        lower_field = grid_schema.get("lower_price", {})
        lower_label = lower_field.get("label", "Lower Price")
        lower_default = lower_field.get("default", 0.0)

        row = tk.Frame(form_frame, bg="#1f1f1f")
        row.pack(fill=tk.X, pady=4)

        tk.Label(
            row,
            text=lower_label,
            font=("Arial", 10),
            bg="#1f1f1f",
            fg="#888888",
            anchor="w",
            width=18
        ).pack(side=tk.LEFT, fill=tk.X)

        self.lower_price_var = tk.DoubleVar(value=float(lower_default))
        validate_float = (self.root.register(lambda v: v.replace(".", "", 1).isdigit() or v == ""), "%P")

        ttk.Entry(
            row,
            textvariable=self.lower_price_var,
            width=18,
            style="Grid.TEntry",
            validate="key",
            validatecommand=validate_float
        ).pack(side=tk.RIGHT)

        # === GRID LEVELS (aus YAML: grid.grid_levels) ===
        levels_field = grid_schema.get("grid_levels", {})
        levels_label = levels_field.get("label", "Grid Levels")
        levels_default = levels_field.get("default", 10)
        levels_min = levels_field.get("min", 1)
        levels_max = levels_field.get("max", 200)

        row = tk.Frame(form_frame, bg="#1f1f1f")
        row.pack(fill=tk.X, pady=4)

        tk.Label(
            row,
            text=levels_label,
            font=("Arial", 10),
            bg="#1f1f1f",
            fg="#888888",
            anchor="w",
            width=18
        ).pack(side=tk.LEFT, fill=tk.X)

        def validate_int_in_range(v):
            if v == "":
                return True
            if v.isdigit():
                val = int(v)
                return levels_min <= val <= levels_max
            return False

        validate_int = (self.root.register(validate_int_in_range), "%P")

        self.grid_levels_var = tk.IntVar(value=int(levels_default))
        ttk.Entry(
            row,
            textvariable=self.grid_levels_var,
            width=18,
            style="Grid.TEntry",
            validate="key",
            validatecommand=validate_int
        ).pack(side=tk.RIGHT)

        # ================================================================
        # TRADING PARAMETER (vollständig YAML-basiert)
        # ================================================================
        trading_section = tk.Frame(scrollable_frame, bg="#1f1f1f")
        trading_section.pack(fill=tk.X, pady=(10, 10))

        tk.Label(
            trading_section,
            text="------------------- TRADING-PARAMETER -------------------",
            font=("Arial", 10),
            fg="#888888",
            bg="#1f1f1f",
            anchor="center"
        ).pack(fill=tk.X, pady=(0, 5))

        form_frame_trading = tk.Frame(trading_section, bg="#1f1f1f")
        form_frame_trading.pack(fill=tk.X, pady=(0, 0), padx=(0, 2))

        # === MARGIN MODE (aus YAML: margin.margin_mode) ===
        margin_data = schema_data.get("margin", {}).get("mode", {})
        margin_label = margin_data.get("label", "Margin Mode")
        margin_options = margin_data.get("options", [])
        margin_default = margin_data.get("default", margin_options[0] if margin_options else "")

        # Übersetzungstabelle GUI <-> Config
        margin_display_map = {opt: opt.upper() for opt in margin_options}
        margin_display_values = [margin_display_map.get(opt, opt.upper()) for opt in margin_options]

        row = tk.Frame(form_frame_trading, bg="#1f1f1f")
        row.pack(fill=tk.X, pady=4)

        tk.Label(
            row,
            text=margin_label,
            font=("Arial", 10),
            bg="#1f1f1f",
            fg="#888888",
            anchor="w",
            width=18
        ).pack(side=tk.LEFT, fill=tk.X)

        # Mapping GUI → Config
        self.margin_mode_map = {margin_display_map.get(opt, opt.upper()): opt for opt in margin_options}

        # Defaultanzeige (in Großbuchstaben)
        default_display = margin_display_map.get(margin_default, margin_default.upper())
        self.margin_mode_var = tk.StringVar(value=default_display)

        ttk.Combobox(
            row,
            textvariable=self.margin_mode_var,
            values=margin_display_values,
            state="readonly",
            width=18,
            style="Grid.TCombobox"
        ).pack(side=tk.RIGHT)


        # === LEVERAGE (aus YAML: trading.leverage) ===
        leverage_field = schema_data.get("margin", {}).get("leverage", {})
        leverage_label = leverage_field.get("label", "Leverage")
        leverage_default = leverage_field.get("default", 20)
        leverage_min = leverage_field.get("min", 1)
        leverage_max = leverage_field.get("max", 125)

        row = tk.Frame(form_frame_trading, bg="#1f1f1f")
        row.pack(fill=tk.X, pady=4)

        tk.Label(
            row,
            text=leverage_label,
            font=("Arial", 10),
            bg="#1f1f1f",
            fg="#888888",
            anchor="w",
            width=18
        ).pack(side=tk.LEFT, fill=tk.X)

        def validate_int_in_range(v):
            if v == "":
                return True
            if v.isdigit():
                val = int(v)
                return leverage_min <= val <= leverage_max
            return False

        validate_int = (self.root.register(validate_int_in_range), "%P")

        self.leverage_var = tk.IntVar(value=int(leverage_default))
        ttk.Entry(
            row,
            textvariable=self.leverage_var,
            width=18,
            style="Grid.TEntry",
            validate="key",
            validatecommand=validate_int
        ).pack(side=tk.RIGHT)

        
        # === BASE ORDER SIZE (aus YAML: grid.base_order_size) ===
        base_field = grid_schema.get("base_order_size", {})
        base_label = base_field.get("label", "Base Order Size")
        base_default = base_field.get("default", 0.0)  # wird im API-Modus überschrieben

        row = tk.Frame(form_frame_trading, bg="#1f1f1f")
        row.pack(fill=tk.X, pady=4)

        tk.Label(
            row,
            text=base_label,
            font=("Arial", 10),
            bg="#1f1f1f",
            fg="#888888",
            anchor="w",
            width=18
        ).pack(side=tk.LEFT, fill=tk.X)

        self.base_order_size_var = tk.DoubleVar(value=float(base_default))
        validate_float = (self.root.register(lambda v: v.replace(".", "", 1).isdigit() or v == ""), "%P")

        ttk.Entry(
            row,
            textvariable=self.base_order_size_var,
            width=18,
            style="Grid.TEntry",
            validate="key",
            validatecommand=validate_float
        ).pack(side=tk.RIGHT)


        # === TP SECTION ===
        tp_section_frame = tk.Frame(form_frame_trading, bg="#1f1f1f")
        tp_section_frame.pack(fill=tk.X)

        # === TP MODE (aus YAML: grid.tp_mode) ===
        tp_mode_field = grid_schema.get("tp_mode", {})
        tp_mode_label = tp_mode_field.get("label", "TP Mode")
        tp_mode_options = tp_mode_field.get("options", [])
        tp_mode_default = tp_mode_field.get("default", tp_mode_options[0] if tp_mode_options else "")

        display_map = {"percent": "PROZENT", "next_grid": "NÄCHSTES GRID"}
        tp_mode_display = [display_map.get(opt, opt.upper()) for opt in tp_mode_options]

        row = tk.Frame(tp_section_frame, bg="#1f1f1f")
        row.pack(fill=tk.X, pady=4)

        tk.Label(
            row,
            text=tp_mode_label,
            font=("Arial", 10),
            bg="#1f1f1f",
            fg="#888888",
            anchor="w",
            width=18
        ).pack(side=tk.LEFT, fill=tk.X)

        self.tp_mode_map = {display_map.get(opt, opt.upper()): opt for opt in tp_mode_options}
        default_display = display_map.get(tp_mode_default, tp_mode_default.upper())
        self.tp_mode_var = tk.StringVar(value=default_display)

        cb = ttk.Combobox(
            row,
            textvariable=self.tp_mode_var,
            values=tp_mode_display,
            state="readonly",
            width=18,
            style="Grid.TCombobox"
        )
        cb.pack(side=tk.RIGHT)

        # === TAKE PROFIT PCT ===
        take_profit_field = grid_schema.get("take_profit_pct", {})
        take_profit_label = take_profit_field.get("label", "Take Profit (%)")
        take_profit_default = take_profit_field.get("default", 0.003)
        visible_if = take_profit_field.get("visible_if", {})  # {"tp_mode": "percent"}

        self.take_profit_row = tk.Frame(tp_section_frame, bg="#1f1f1f")

        tk.Label(
            self.take_profit_row,
            text=take_profit_label,
            font=("Arial", 10),
            bg="#1f1f1f",
            fg="#888888",
            anchor="w",
            width=18
        ).pack(side=tk.LEFT, fill=tk.X)

        self.take_profit_var = tk.DoubleVar(value=float(take_profit_default))
        validate_float = (self.root.register(lambda v: v.replace(".", "", 1).isdigit() or v == ""), "%P")

        ttk.Entry(
            self.take_profit_row,
            textvariable=self.take_profit_var,
            width=18,
            style="Grid.TEntry",
            validate="key",
            validatecommand=validate_float
        ).pack(side=tk.RIGHT)

        # --- Sichtbarkeits-Logik TP ---
        def update_take_profit_visibility(*_):
            if not visible_if:
                return
            target_key, required_value = next(iter(visible_if.items()))
            current_display_value = self.tp_mode_var.get()
            current_config_value = self.tp_mode_map.get(current_display_value)
            if target_key == "tp_mode" and current_config_value == required_value:
                if not self.take_profit_row.winfo_ismapped():
                    self.take_profit_row.pack(fill=tk.X, pady=4)
            else:
                if self.take_profit_row.winfo_ismapped():
                    self.take_profit_row.pack_forget()

        self.tp_mode_var.trace_add("write", update_take_profit_visibility)
        update_take_profit_visibility()

        # === SL SECTION ===
        sl_section_frame = tk.Frame(form_frame_trading, bg="#1f1f1f")
        sl_section_frame.pack(fill=tk.X)

        # === SL MODE ===
        sl_mode_field = grid_schema.get("sl_mode", {})
        sl_mode_label = sl_mode_field.get("label", "SL Mode")
        sl_mode_options = sl_mode_field.get("options", [])
        sl_mode_default = sl_mode_field.get("default", sl_mode_options[0] if sl_mode_options else "")

        sl_display_map = {"percent": "PROZENT", "fixed": "FEST", "none": "KEINER"}
        sl_mode_display = [sl_display_map.get(opt, opt.upper()) for opt in sl_mode_options]

        row = tk.Frame(sl_section_frame, bg="#1f1f1f")
        row.pack(fill=tk.X, pady=4)

        tk.Label(
            row,
            text=sl_mode_label,
            font=("Arial", 10),
            bg="#1f1f1f",
            fg="#888888",
            anchor="w",
            width=18
        ).pack(side=tk.LEFT, fill=tk.X)

        self.sl_mode_map = {sl_display_map.get(opt, opt.upper()): opt for opt in sl_mode_options}
        sl_default_display = sl_display_map.get(sl_mode_default, sl_mode_default.upper())
        self.sl_mode_var = tk.StringVar(value=sl_default_display)

        cb_sl = ttk.Combobox(
            row,
            textvariable=self.sl_mode_var,
            values=sl_mode_display,
            state="readonly",
            width=18,
            style="Grid.TCombobox"
        )
        cb_sl.pack(side=tk.RIGHT)

        # === STOP LOSS PCT ===
        stop_loss_pct_field = grid_schema.get("stop_loss_pct", {})
        stop_loss_pct_label = stop_loss_pct_field.get("label", "Stop-Loss (%)")
        stop_loss_pct_default = stop_loss_pct_field.get("default", 1)

        self.stop_loss_pct_row = tk.Frame(sl_section_frame, bg="#1f1f1f")

        tk.Label(
            self.stop_loss_pct_row,
            text=stop_loss_pct_label,
            font=("Arial", 10),
            bg="#1f1f1f",
            fg="#888888",
            anchor="w",
            width=18
        ).pack(side=tk.LEFT, fill=tk.X)

        self.stop_loss_pct_var = tk.DoubleVar(value=float(stop_loss_pct_default))
        ttk.Entry(
            self.stop_loss_pct_row,
            textvariable=self.stop_loss_pct_var,
            width=18,
            style="Grid.TEntry",
            validate="key",
            validatecommand=validate_float
        ).pack(side=tk.RIGHT)

        # === STOP LOSS PRICE ===
        stop_loss_price_field = grid_schema.get("stop_loss_price", {})
        stop_loss_price_label = stop_loss_price_field.get("label", "Stop-Loss Preis")
        stop_loss_price_default = stop_loss_price_field.get("default", 0.8)

        self.stop_loss_price_row = tk.Frame(sl_section_frame, bg="#1f1f1f")

        tk.Label(
            self.stop_loss_price_row,
            text=stop_loss_price_label,
            font=("Arial", 10),
            bg="#1f1f1f",
            fg="#888888",
            anchor="w",
            width=18
        ).pack(side=tk.LEFT, fill=tk.X)

        self.stop_loss_price_var = tk.DoubleVar(value=float(stop_loss_price_default))
        ttk.Entry(
            self.stop_loss_price_row,
            textvariable=self.stop_loss_price_var,
            width=18,
            style="Grid.TEntry",
            validate="key",
            validatecommand=validate_float
        ).pack(side=tk.RIGHT)

        # --- Sichtbarkeitslogik SL ---
        def update_sl_visibility(*args):
            mode = self.sl_mode_var.get()
            if mode == "PROZENT":
                self.stop_loss_pct_row.pack(fill=tk.X, pady=4)
                self.stop_loss_price_row.pack_forget()
            elif mode == "FEST":
                self.stop_loss_price_row.pack(fill=tk.X, pady=4)
                self.stop_loss_pct_row.pack_forget()
            else:
                self.stop_loss_pct_row.pack_forget()
                self.stop_loss_price_row.pack_forget()

        update_sl_visibility()
        self.sl_mode_var.trace_add("write", update_sl_visibility)



        # =========================================================================
        # MOUSEWHEEL BINDING (plattformübergreifend)
        # =========================================================================
        def _on_mousewheel(event):
            """Plattformübergreifendes Scroll-Handling"""
            if event.num == 4:  # Linux scroll up
                canvas.yview_scroll(-1, "units")
            elif event.num == 5:  # Linux scroll down
                canvas.yview_scroll(1, "units")
            else:
                # Windows / macOS
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        # Events binden, aber nur wenn Maus über dem Bereich ist
        def _bind_to_mousewheel(event):
            system = self.root.tk.call('tk', 'windowingsystem')
            if system == 'x11':  # Linux
                canvas.bind_all("<Button-4>", _on_mousewheel)
                canvas.bind_all("<Button-5>", _on_mousewheel)
            else:  # Windows oder macOS
                canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_from_mousewheel(event):
            system = self.root.tk.call('tk', 'windowingsystem')
            if system == 'x11':  # Linux
                canvas.unbind_all("<Button-4>")
                canvas.unbind_all("<Button-5>")
            else:
                canvas.unbind_all("<MouseWheel>")

        scrollable_frame.bind("<Enter>", _bind_to_mousewheel)
        scrollable_frame.bind("<Leave>", _unbind_from_mousewheel)


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
            # === API Call ===
            response = self.client_pub.get_trading_pairs()
            
            # === Response parsen ===
            if isinstance(response, dict):
                data = response.get("data", [])
            elif isinstance(response, list):
                data = response
            else:
                data = []
            
            # === Symbole & minTradeVolume extrahieren ===
            self.coins = []
            self.coin_min_volume = {}  # 🔹 Dictionary für minTradeVolume

            for pair in data:
                symbol = pair.get("symbol", "")
                if symbol:
                    self.coins.append(symbol)
                    try:
                        self.coin_min_volume[symbol] = float(pair.get("minTradeVolume", 0.0))
                    except Exception:
                        self.coin_min_volume[symbol] = 0.0

            self.coins.sort()

            # === Dropdown füllen ===
            self.coin_dropdown["values"] = self.coins

            # === Default: BTCUSDT, falls vorhanden ===
            if "BTCUSDT" in self.coins:
                self.coin_dropdown.set("BTCUSDT")
            elif self.coins:
                self.coin_dropdown.set(self.coins[0])

            self._update_status(f"✅ {len(self.coins)} Coins geladen")

            # === Initial Chart laden ===
            if self.coins:
                self._load_chart()

            # === Initiale Coin-Selektion triggern, damit Base Order Size gesetzt wird ===
            if self.coins:
                try:
                    # Event simulieren → ruft automatisch API-Mode-Logik aus _on_coin_select() auf
                    self._on_coin_select(None)
                except Exception as e:
                    print(f"⚠️ Konnte initiale Coin-Selektion nicht triggern: {e}")


        except Exception as e:
            self._update_status(f"❌ Fehler: {e}")
            print(f"Error loading coins: {e}")

    

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
            # === CONFIG-MODUS (📂) ===
            file_path = self.config_dir / name
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f)

                coin = cfg.get("symbol", "").strip('"')
                if not coin:
                    self._update_status("⚠️ Kein Symbol in YAML gefunden")
                    return

                # Coin im Dropdown setzen, damit Chart den richtigen Wert nutzt
                self.selected_coin.set(coin)
                self._update_status(f"📂 {name} geladen ({coin})")

                # Config-Werte aus YAML auf GUI anwenden
                self._apply_config_values(cfg)

                # Chart für Symbol aus YAML laden
                self._load_chart()

            except Exception as e:
                self._update_status(f"❌ YAML-Fehler: {e}")

        else:
            # === API-MODUS (🌐) ===
            coin = name
            self._update_status(f"📊 {coin} | {self.selected_timeframe.get()}")

            # Chart neu laden
            self._load_chart()

            # --- Base Order Size automatisch mit minTradeVolume belegen ---
            try:
                if hasattr(self, "coin_min_volume") and coin in self.coin_min_volume:
                    min_vol = float(self.coin_min_volume[coin])
                    if hasattr(self, "base_order_size_var"):
                        self.base_order_size_var.set(min_vol)
                        print(f"🔹 Base Order Size für {coin} auf {min_vol} gesetzt")
            except Exception as e:
                print(f"⚠️ Konnte Base Order Size nicht setzen: {e}")


    
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


    def _apply_config_values(self, cfg):
        """Überträgt Werte aus geladener Coin-Config in die GUI-Variablen"""
        try:
            trading = cfg.get("trading", {})
            margin = cfg.get("margin", {})
            grid = cfg.get("grid", {})

            # === TRADING SEKTION ===
            if "grid_direction" in trading and hasattr(self, "grid_dir_var"):
                val = trading["grid_direction"].strip('"')
                if hasattr(self, "grid_dir_map"):
                    for display, real in self.grid_dir_map.items():
                        if real == val:
                            self.grid_dir_var.set(display)
                            break

            # === MARGIN SEKTION ===
            if "margin_mode" in margin and hasattr(self, "margin_mode_var"):
                val = margin["margin_mode"].strip('"')
                display_val = next((k for k, v in self.margin_mode_map.items() if v == val), val.upper())
                self.margin_mode_var.set(display_val)


            if "leverage" in margin and hasattr(self, "leverage_var"):
                try:
                    self.leverage_var.set(int(margin["leverage"]))
                except Exception:
                    pass

            # === GRID SEKTION ===
            if "grid_mode" in grid and hasattr(self, "grid_mode_var"):
                val = grid["grid_mode"].strip('"')
                if hasattr(self, "grid_mode_map"):
                    for display, real in self.grid_mode_map.items():
                        if real == val:
                            self.grid_mode_var.set(display)
                            break

            if "upper_price" in grid and hasattr(self, "upper_price_var"):
                self.upper_price_var.set(float(grid["upper_price"]))

            if "lower_price" in grid and hasattr(self, "lower_price_var"):
                self.lower_price_var.set(float(grid["lower_price"]))

            if "grid_levels" in grid and hasattr(self, "grid_levels_var"):
                self.grid_levels_var.set(int(grid["grid_levels"]))

            if "base_order_size" in grid and hasattr(self, "base_order_size_var"):
                self.base_order_size_var.set(float(grid["base_order_size"]))


            # === TP-Parameter ===
            if "tp_mode" in grid and hasattr(self, "tp_mode_var"):
                val = grid["tp_mode"].strip('"')
                display = next((k for k, v in self.tp_mode_map.items() if v == val), None)
                if display:
                    self.tp_mode_var.set(display)

            if "take_profit_pct" in grid and hasattr(self, "take_profit_var"):
                self.take_profit_var.set(float(grid["take_profit_pct"]))

            # === SL-Parameter ===
            if "sl_mode" in grid and hasattr(self, "sl_mode_var"):
                val = grid["sl_mode"].strip('"')
                display = next((k for k, v in self.sl_mode_map.items() if v == val), None)
                if display:
                    self.sl_mode_var.set(display)

            if "stop_loss_pct" in grid and hasattr(self, "stop_loss_pct_var"):
                self.stop_loss_pct_var.set(float(grid["stop_loss_pct"]))

            if "stop_loss_price" in grid and hasattr(self, "stop_loss_price_var"):
                self.stop_loss_price_var.set(float(grid["stop_loss_price"]))

            # === Sichtbarkeit aktualisieren ===
            try:
                self.root.after(50, lambda: [
                    self.tp_mode_var.set(self.tp_mode_var.get()),
                    self.sl_mode_var.set(self.sl_mode_var.get())
                ])
            except Exception:
                pass

            self._update_status("✅ Config-Werte übernommen")

        except Exception as e:
            print(f"⚠️ Fehler beim Anwenden der Config-Werte: {e}")
            import traceback; traceback.print_exc()
            self._update_status("⚠️ Fehler beim Anwenden der Config-Werte")


    def _save_current_config(self):
        """Speichert aktuelle GUI-Werte in die aktive oder neue YAML-Datei"""
        try:
            symbol = self.selected_coin.get()
            if not symbol:
                self._update_status("⚠️ Kein Symbol ausgewählt")
                return

            # === TRADING SEKTION ===
            trading = {
                "grid_direction": self.grid_dir_map.get(self.grid_dir_var.get(), "").lower()
            }

            # === MARGIN SEKTION ===
            margin = {}
            if hasattr(self, "margin_mode_var"):
                margin["margin_mode"] = self.margin_mode_var.get().lower()
            if hasattr(self, "leverage_var"):
                try:
                    margin["leverage"] = int(self.leverage_var.get())
                except ValueError:
                    margin["leverage"] = 1

            # === GRID SEKTION ===
            grid = {
                "grid_mode": self.grid_mode_map.get(self.grid_mode_var.get(), "").lower(),
                "upper_price": float(self.upper_price_var.get()),
                "lower_price": float(self.lower_price_var.get()),
                "grid_levels": int(self.grid_levels_var.get())
            }

            # === TRADING PARAMETER (innerhalb GRID) ===
            if hasattr(self, "tp_mode_var"):
                grid["tp_mode"] = self.tp_mode_map.get(self.tp_mode_var.get(), "percent")
            if hasattr(self, "take_profit_var"):
                grid["take_profit_pct"] = float(self.take_profit_var.get())

            if hasattr(self, "sl_mode_var"):
                grid["sl_mode"] = self.sl_mode_map.get(self.sl_mode_var.get(), "none")

            if hasattr(self, "stop_loss_pct_var") and self.stop_loss_pct_row.winfo_ismapped():
                grid["stop_loss_pct"] = float(self.stop_loss_pct_var.get())
            if hasattr(self, "stop_loss_price_var") and self.stop_loss_price_row.winfo_ismapped():
                grid["stop_loss_price"] = float(self.stop_loss_price_var.get())
            
            if hasattr(self, "base_order_size_var"):
                grid["base_order_size"] = float(self.base_order_size_var.get())


            # === GESAMTE CONFIG ===
            config_data = {
                "symbol": symbol,
                "trading": trading,
                "margin": margin,
                "grid": grid
            }

            # === ZIELPFAD BESTIMMEN ===
            if self.use_local_configs and hasattr(self, "current_config_path") and self.current_config_path:
                save_path = self.current_config_path
            else:
                save_path = self.config_dir / f"{symbol}.yaml"

            # === YAML SCHREIBEN mit Anführungszeichen für Strings ===
            class QuotedString(str): pass

            def quoted_presenter(dumper, data):
                return dumper.represent_scalar("tag:yaml.org,2002:str", data, style='"')

            yaml.add_representer(QuotedString, quoted_presenter)

            # Strings konvertieren
            def quote_strings(obj):
                if isinstance(obj, dict):
                    return {k: quote_strings(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [quote_strings(i) for i in obj]
                elif isinstance(obj, str):
                    return QuotedString(obj)
                else:
                    return obj

            quoted_data = quote_strings(config_data)

            with open(save_path, "w", encoding="utf-8") as f:
                yaml.dump(quoted_data, f, sort_keys=False, allow_unicode=True)

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


if __name__ == "__main__":
    app = GridConfigGUI()
    app.run()