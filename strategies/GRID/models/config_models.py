# strategies/GRID/models/config_models.py
"""
Pydantic Config Models mit Hedge-Validierung

FIXES:
- ✅ HedgeConfig hat jetzt model_validator
- ✅ Validierung von trigger_offset, partial_levels, fixed_size_ratio
- ✅ Encoding UTF-8
- ✅ Validator in GridBotConfig korrigiert
"""
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Literal, Optional
from enum import Enum
from typing import List


# === Enums für typsichere Auswahl ===
class GridMode(str, Enum):
    LINEAR = "linear"
    LOGARITHMISCH = "logarithmisch"


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
    grid_mode: GridMode = GridMode.linear
    min_price_step: float = Field(default=0.0000001, gt=0)

    base_order_size: float = Field(gt=0)
    active_reorder: bool = True
    reorder_distance_steps: int = Field(default=2, ge=1, le=10)

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
        """Erweiterte Grid-Validierung"""
        
        # 1️⃣ Basisprüfung
        if self.upper_price <= self.lower_price:
            raise ValueError(
                f"upper_price ({self.upper_price}) muss größer als lower_price ({self.lower_price}) sein"
            )
        
        # 2️⃣ Mindestabstand zwischen upper/lower
        price_range = self.upper_price - self.lower_price
        if price_range < self.min_price_step * 10:
            raise ValueError(
                f"Preisbereich ({price_range}) zu klein für {self.grid_levels} Levels "
                f"(min: {self.min_price_step * 10})"
            )
        
        # 3️⃣ Sinnvolle TP/SL Prozentsätze
        if self.tp_mode == TPMode.PERCENT:
            if self.take_profit_pct < 0.001:  # < 0.1%
                import warnings
                warnings.warn(f"⚠️ take_profit_pct={self.take_profit_pct*100:.2f}% sehr niedrig")
            if self.take_profit_pct > 0.1:  # > 10%
                raise ValueError(f"take_profit_pct={self.take_profit_pct*100:.1f}% unrealistisch hoch (max: 10%)")
        
        if self.sl_mode == SLMode.PERCENT:
            if self.stop_loss_pct < 0.005:  # < 0.5%
                import warnings
                warnings.warn(f"⚠️ stop_loss_pct={self.stop_loss_pct*100:.2f}% sehr eng")
            if self.stop_loss_pct > 0.5:  # > 50%
                raise ValueError(f"stop_loss_pct={self.stop_loss_pct*100:.1f}% unrealistisch hoch (max: 50%)")
        
        # 4️⃣ Rebalance-Intervall sinnvoll?
        if self.rebalance_interval < 60:
            raise ValueError(
                f"rebalance_interval={self.rebalance_interval}s zu kurz (min: 60s)"
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
    mode: Literal["direct", "dynamic", "reversal"] = "direct"
    trigger_offset: float = Field(default=1.0, gt=0, description="Muss > 0 sein")
    partial_levels: List[float] = [0.5, 0.75, 1.0]
    close_on_reentry: bool = True
    size_mode: Literal["net_position", "fixed"] = "net_position"
    fixed_size_ratio: float = Field(default=0.5, gt=0, le=1, description="Zwischen 0 und 1")

    @model_validator(mode='after')
    def validate_hedge_logic(self):
        """Prüft Hedge-spezifische Regeln"""
        
        # 1️⃣ Dynamic-Mode braucht partial_levels
        if self.mode == "dynamic" and not self.partial_levels:
            raise ValueError("mode='dynamic' benötigt partial_levels")
        
        # 2️⃣ Prüfe partial_levels Werte
        if self.partial_levels:
            for i, lvl in enumerate(self.partial_levels):
                if not (0 < lvl <= 1):
                    raise ValueError(
                        f"partial_levels[{i}] = {lvl} ist ungültig (muss zwischen 0 und 1 liegen)"
                    )
            
            # Sortiere partial_levels
            if self.partial_levels != sorted(self.partial_levels):
                import warnings
                warnings.warn(
                    f"partial_levels sind nicht sortiert, sortiere automatisch: {self.partial_levels}"
                )
                self.partial_levels = sorted(self.partial_levels)
        
        # 3️⃣ trigger_offset Grenzen
        if self.trigger_offset > 10:
            raise ValueError(
                f"trigger_offset={self.trigger_offset} zu hoch (max: 10, empfohlen: 1-3)"
            )
        
        if self.trigger_offset < 0.1:
            raise ValueError(
                f"trigger_offset={self.trigger_offset} zu niedrig (min: 0.1)"
            )
        
        # 4️⃣ size_mode Validierung
        if self.size_mode == "fixed":
            if self.fixed_size_ratio <= 0 or self.fixed_size_ratio > 2:
                raise ValueError(
                    f"fixed_size_ratio={self.fixed_size_ratio} ungültig (muss 0 < x <= 2 sein)"
                )
        
        # 5️⃣ Reversal-Mode Warnung
        if self.mode == "reversal" and self.size_mode != "net_position":
            import warnings
            warnings.warn(
                "⚠️ reversal-Mode mit size_mode='fixed' kann zu hohem Risiko führen"
            )
        
        # 6️⃣ Preemptive Hedge ohne enabled macht keinen Sinn
        if self.preemptive_hedge and not self.enabled:
            import warnings
            warnings.warn(
                "⚠️ preemptive_hedge=true aber enabled=false → Hedge wird nicht aktiv"
            )
        
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
    hedge: HedgeConfig = Field(default_factory=HedgeConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)

    @model_validator(mode='after')
    def validate_cross_field_logic(self):
        """Prüft Abhängigkeiten zwischen Feldern"""
        
        # ✅ FIX: self.grid.upper_price statt self.upper_price!
        
        # 1️⃣ SL fixed → stop_loss_price muss gesetzt sein
        if self.grid.sl_mode == SLMode.FIXED and self.grid.stop_loss_price is None:
            raise ValueError("stop_loss_price muss gesetzt sein bei sl_mode='fixed'")

        # 2️⃣ upper/lower Relation (schon in GridConfig geprüft, aber nochmal zur Sicherheit)
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