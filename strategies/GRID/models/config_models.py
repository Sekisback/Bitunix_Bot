# strategies/GRID/models/config_models.py
"""
Pydantic Models für Grid Trading Config
Validiert alle Parameter aus base.yaml + Coin-Configs
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Literal, Optional
from enum import Enum


# === Enums für typsichere Auswahl ===
class GridMode(str, Enum):
    ARITHMETIC = "arithmetic"
    GEOMETRIC = "geometric"


class GridDirection(str, Enum):
    LONG = "long"
    SHORT = "short"
    BOTH = "both"


class TPMode(str, Enum):
    PERCENT = "percent"
    NEXT_GRID = "next_grid"


class SLMode(str, Enum):
    PERCENT = "percent"
    FIXED = "fixed"
    NONE = "none"


# === Config-Sektionen ===
class SystemConfig(BaseModel):
    """Systemeinstellungen (Logging, Update-Intervalle, etc.)"""
    debug: bool = False
    update_interval: int = Field(default=5, ge=1, le=60)
    reconnect_interval: int = Field(default=5, ge=1, le=30)
    backtest_bars: int = Field(default=200, ge=10, le=500)
    timezone_offset: int = Field(default=2, ge=-12, le=14)
    log_to_file: bool = True
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


class LoggingConfig(BaseModel):
    """Logging-Konfiguration"""
    log_dir: str = "logs"
    filename_pattern: str = "GRID_{symbol}_{date}.log"
    rotate_daily: bool = True
    max_size_mb: int = Field(default=10, ge=1, le=100)


class TradingConfig(BaseModel):
    """Trading-Einstellungen"""
    dry_run: bool = True
    grid_direction: GridDirection = GridDirection.BOTH
    client_id_prefix: str = Field(default="GRID", min_length=1, max_length=20)


class GridConfig(BaseModel):
    """Grid-Parameter (Preise, Levels, TP/SL)"""
    # Preisgrenzen
    upper_price: float = Field(gt=0, description="Obere Preisgrenze")
    lower_price: float = Field(gt=0, description="Untere Preisgrenze")
    
    # Grid-Struktur
    grid_levels: int = Field(ge=2, le=100, description="Anzahl Grid-Levels")
    grid_mode: GridMode = GridMode.ARITHMETIC
    min_price_step: float = Field(default=0.0000001, gt=0)
    
    # Order-Größe
    base_order_size: float = Field(gt=0, description="Ordergröße in USDT")
    active_rebuy: bool = True
    
    # Take-Profit
    tp_mode: TPMode = TPMode.PERCENT
    take_profit_pct: float = Field(default=0.003, gt=0, lt=1)
    
    # Stop-Loss
    sl_mode: SLMode = SLMode.PERCENT
    stop_loss_pct: float = Field(default=0.01, gt=0, lt=1)
    stop_loss_price: Optional[float] = Field(default=None, gt=0)
    
    # Rebalancing
    rebalance_interval: int = Field(default=300, ge=60, le=3600)

    @field_validator("upper_price")
    @classmethod
    def validate_price_range(cls, v, info):
        """Prüft ob upper > lower"""
        if "lower_price" in info.data:
            lower = info.data["lower_price"]
            if v <= lower:
                raise ValueError(
                    f"upper_price ({v}) muss größer als "
                    f"lower_price ({lower}) sein"
                )
        return v


class RiskConfig(BaseModel):
    """Risiko-Management und Gebühren"""
    include_fees: bool = False
    fee_side: Literal["maker", "taker"] = "maker"
    maker_fee_pct: float = Field(default=0.00014, ge=0, lt=0.1)
    taker_fee_pct: float = Field(default=0.00014, ge=0, lt=0.1)


class MarginConfig(BaseModel):
    """Margin- und Hebel-Einstellungen"""
    mode: Literal["isolated", "cross"] = "isolated"
    leverage: int = Field(default=3, ge=1, le=125)
    auto_reduce_only: bool = False


class StrategyConfig(BaseModel):
    """Strategie-Verhalten"""
    entry_on_touch: bool = True


# === Haupt-Config ===
class GridBotConfig(BaseModel):
    """Vollständige Grid-Bot-Konfiguration"""
    
    symbol: str = Field(min_length=3, max_length=20)
    
    system: SystemConfig = Field(default_factory=SystemConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    trading: TradingConfig = Field(default_factory=TradingConfig)
    grid: GridConfig
    risk: RiskConfig = Field(default_factory=RiskConfig)
    margin: MarginConfig = Field(default_factory=MarginConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)

    @model_validator(mode='after')
    def validate_cross_field_logic(self):
        """Prüft Abhängigkeiten zwischen Feldern"""
        
        # SL fixed → stop_loss_price muss gesetzt sein
        if self.grid.sl_mode == SLMode.FIXED:
            if self.grid.stop_loss_price is None:
                raise ValueError(
                    "stop_loss_price muss gesetzt sein bei sl_mode='fixed'"
                )
        
        # Warnung bei hohem Hebel + vielen Levels
        if self.margin.leverage > 10 and self.grid.grid_levels > 50:
            import warnings
            warnings.warn(
                f"⚠️ Hohes Risiko: Hebel={self.margin.leverage} "
                f"+ {self.grid.grid_levels} Levels"
            )
        
        return self