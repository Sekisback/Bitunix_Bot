# strategies/GRID/models/config_models.py (KORRIGIERT)
"""
Pydantic Config Models mit Hedge-Validierung

FIXES:
- ✅ HedgeConfig hat jetzt model_validator
- ✅ Validierung von trigger_offset, partial_levels, fixed_size_ratio
"""
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Literal, Optional
from enum import Enum
from typing import List


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
    debug: bool = False
    update_interval: int = Field(default=5, ge=1, le=60)
    reconnect_interval: int = Field(default=5, ge=1, le=30)
    backtest_bars: int = Field(default=200, ge=10, le=500)
    timezone_offset: int = Field(default=2, ge=-12, le=14)
    log_to_file: bool = True
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


class LoggingConfig(BaseModel):
    log_dir: str = "logs"
    filename_pattern: str = "GRID_{symbol}_{date}.log"
    rotate_daily: bool = True
    max_size_mb: int = Field(default=10, ge=1, le=100)


class TradingConfig(BaseModel):
    dry_run: bool = True
    grid_direction: GridDirection = GridDirection.BOTH
    client_id_prefix: str = Field(default="GRID", min_length=1, max_length=20)


class GridConfig(BaseModel):
    upper_price: float = Field(gt=0, description="Obere Preisgrenze")
    lower_price: float = Field(gt=0, description="Untere Preisgrenze")
    grid_levels: int = Field(ge=2, le=100)
    grid_mode: GridMode = GridMode.ARITHMETIC
    min_price_step: float = Field(default=0.0000001, gt=0)
    base_order_size: float = Field(gt=0)
    active_rebuy: bool = True
    tp_mode: TPMode = TPMode.PERCENT
    take_profit_pct: float = Field(default=0.003, gt=0, lt=1)
    sl_mode: SLMode = SLMode.PERCENT
    stop_loss_pct: float = Field(default=0.01, gt=0, lt=1)
    stop_loss_price: Optional[float] = Field(default=None, gt=0)
    rebalance_interval: int = Field(default=300, ge=60, le=3600)

    @field_validator("upper_price")
    @classmethod
    def validate_price_range(cls, v, info):
        """Prüft ob upper > lower"""
        if "lower_price" in info.data:
            lower = info.data["lower_price"]
            if v <= lower:
                raise ValueError(
                    f"upper_price ({v}) muss größer als lower_price ({lower}) sein"
                )
        return v

    @model_validator(mode="after")
    def cross_check_prices(self):
        """Basisprüfung: upper_price > lower_price"""
        if self.upper_price <= self.lower_price:
            raise ValueError(
                f"upper_price ({self.upper_price}) muss größer als lower_price ({self.lower_price}) sein"
            )
        return self


class RiskConfig(BaseModel):
    include_fees: bool = False
    fee_side: Literal["maker", "taker"] = "maker"
    maker_fee_pct: float = Field(default=0.00014, ge=0, lt=0.1)
    taker_fee_pct: float = Field(default=0.00014, ge=0, lt=0.1)


class MarginConfig(BaseModel):
    mode: Literal["CROSS", "ISOLATION"] = "ISOLATION"
    leverage: int = Field(default=3, ge=1, le=125)
    auto_reduce_only: bool = False


class HedgeConfig(BaseModel):
    """
    Hedge-Konfiguration mit Validierung
    
    ✅ FIX: Vollständige Validierung hinzugefügt
    """
    enabled: bool = False
    preemptive_hedge: bool = False
    mode: Literal["direct", "dynamic", "reversal"] = "direct"  # ✅ Literal statt str
    trigger_offset: float = Field(default=1.0, gt=0, description="Muss > 0 sein")
    partial_levels: List[float] = [0.5, 0.75, 1.0]
    close_on_reentry: bool = True
    size_mode: Literal["net_position", "fixed"] = "net_position"  # ✅ Literal statt str
    fixed_size_ratio: float = Field(default=0.5, gt=0, le=1, description="Zwischen 0 und 1")

    @model_validator(mode='after')
    def validate_hedge_logic(self):
        """
        Prüft Hedge-spezifische Regeln
        
        ✅ FIX: Vollständige Validierung
        """
        # 1️⃣ Dynamic-Mode braucht partial_levels
        if self.mode == "dynamic" and not self.partial_levels:
            raise ValueError("mode='dynamic' benötigt partial_levels")
        
        # 2️⃣ Prüfe partial_levels Werte (falls vorhanden)
        if self.partial_levels:
            for i, lvl in enumerate(self.partial_levels):
                if not (0 < lvl <= 1):
                    raise ValueError(
                        f"partial_levels[{i}] = {lvl} ist ungültig (muss zwischen 0 und 1 liegen)"
                    )
            
            # 3️⃣ Sortiere partial_levels aufsteigend
            if self.partial_levels != sorted(self.partial_levels):
                import warnings
                warnings.warn(
                    f"partial_levels sind nicht sortiert, sortiere automatisch: {self.partial_levels}"
                )
                self.partial_levels = sorted(self.partial_levels)
        
        # 4️⃣ Warnung bei unrealistischen Werten
        if self.trigger_offset > 5:
            import warnings
            warnings.warn(
                f"⚠️ trigger_offset={self.trigger_offset} sehr hoch (normal: 1-3)"
            )
        
        # 5️⃣ size_mode=fixed braucht sinnvollen fixed_size_ratio
        if self.size_mode == "fixed" and self.fixed_size_ratio == 0:
            raise ValueError("size_mode='fixed' mit fixed_size_ratio=0 ist sinnlos")
        
        return self


class StrategyConfig(BaseModel):
    entry_on_touch: bool = True


# === Haupt-Config ===
class GridBotConfig(BaseModel):
    symbol: str = Field(min_length=3, max_length=20)
    system: SystemConfig = Field(default_factory=SystemConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    trading: TradingConfig = Field(default_factory=TradingConfig)
    grid: GridConfig
    risk: RiskConfig = Field(default_factory=RiskConfig)
    margin: MarginConfig = Field(default_factory=MarginConfig)
    hedge: HedgeConfig = Field(default_factory=HedgeConfig)  # ✅ Mit Validierung
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)

    @model_validator(mode='after')
    def validate_cross_field_logic(self):
        """Prüft Abhängigkeiten zwischen Feldern"""
        
        # 1️⃣ SL fixed → stop_loss_price muss gesetzt sein
        if self.grid.sl_mode == SLMode.FIXED and self.grid.stop_loss_price is None:
            raise ValueError("stop_loss_price muss gesetzt sein bei sl_mode='fixed'")

        # 2️⃣ upper/lower Relation prüfen
        if self.grid.upper_price <= self.grid.lower_price:
            raise ValueError(
                f"upper_price ({self.grid.upper_price}) muss größer als lower_price ({self.grid.lower_price}) sein"
            )

        # 3️⃣ FIXED Stop-Loss Richtung prüfen
        if self.grid.sl_mode == SLMode.FIXED and self.grid.stop_loss_price is not None:
            direction = self.trading.grid_direction

            if direction == GridDirection.SHORT and self.grid.stop_loss_price <= self.grid.upper_price:
                raise ValueError(
                    f"Bei grid_direction = 'short' und sl_mode = 'fixed', muss stop_loss_price ({self.grid.stop_loss_price}) "
                    f"> upper_price ({self.grid.upper_price}) sein"
                )

            if direction == GridDirection.LONG and self.grid.stop_loss_price >= self.grid.lower_price:
                raise ValueError(
                    f"Bei grid_direction = 'long' und sl_mode = 'fixed', muss stop_loss_price ({self.grid.stop_loss_price}) "
                    f"< lower_price ({self.grid.lower_price}) sein"
                )

        # 4️⃣ Warnung bei hohem Hebel + vielen Levels
        if self.margin.leverage > 10 and self.grid.grid_levels > 50:
            import warnings
            warnings.warn(
                f"⚠️ Hohes Risiko: Hebel={self.margin.leverage} + {self.grid.grid_levels} Levels"
            )

        return self