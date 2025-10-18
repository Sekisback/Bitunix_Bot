# strategies/GRID/manager/grid_calculator.py
"""
GridCalculator - Preisgrid-Berechnung isoliert
Zuständig für:
- Preisraster-Generierung (arithmetisch/geometrisch)
- Tick-Rundung
- Grid-Hash-Berechnung (Cache)
"""

import hashlib
import logging
from typing import List
from models.config_models import GridMode


class GridCalculator:
    """
    Berechnet Preisgitter basierend auf Grid-Config
    """

    def __init__(self, grid_config, logger: logging.Logger = None):
        """
        Args:
            grid_config: GridConfig-Objekt aus Pydantic
            logger: Optional Logger
        """
        self.config = grid_config
        self.logger = logger or logging.getLogger("GridCalculator")
        
        # Cache
        self._cached_prices: List[float] = []
        self._cache_hash: str = ""

    def calculate_price_list(self, force_refresh: bool = False) -> List[float]:
        """
        Generiert Liste von Preisniveaus
        
        Args:
            force_refresh: Cache ignorieren und neu berechnen
        
        Returns:
            Liste von gerundeten Preisen
        """
        # === Cache-Check ===
        current_hash = self._compute_config_hash()
        
        if not force_refresh and self._cached_prices and self._cache_hash == current_hash:
            self.logger.debug("Preisraster aus Cache")
            return self._cached_prices
        
        # === Neu berechnen ===
        lower = float(self.config.lower_price)
        upper = float(self.config.upper_price)
        n = int(self.config.grid_levels)
        mode = self.config.grid_mode
        
        if mode == GridMode.linear:
            prices = self._linear_grid(lower, upper, n)
        elif mode == GridMode.logarithmisch:
            prices = self._logarithmisch_grid(lower, upper, n)
        else:
            raise ValueError(f"Unbekannter grid_mode: {mode}")
        
        # Tick-Rundung
        prices = [self.round_to_tick(p) for p in prices]
        
        # Cache speichern
        self._cached_prices = prices
        self._cache_hash = current_hash
        
        # self.logger.info(f"Preisraster berechnet: {len(prices)} Levels ({mode.value})")
        return prices

    def _linear_grid(self, lower: float, upper: float, n: int) -> List[float]:
        """
        Gleichmäßige Preisabstände
        
        Args:
            lower: Untere Grenze
            upper: Obere Grenze
            n: Anzahl Zwischenschritte
        
        Returns:
            Liste mit n+1 Preisen
        """
        step = (upper - lower) / n
        return [lower + i * step for i in range(n + 1)]

    def _logarithmisch_grid(self, lower: float, upper: float, n: int) -> List[float]:
        """
        Prozentuale Preisabstände (logarithmisch)
        
        Args:
            lower: Untere Grenze
            upper: Obere Grenze
            n: Anzahl Zwischenschritte
        
        Returns:
            Liste mit n+1 Preisen
        """
        ratio = (upper / lower) ** (1.0 / n)
        return [lower * (ratio ** i) for i in range(n + 1)]

    def round_to_tick(self, price: float) -> float:
        """
        Rundet Preis auf kleinste Tick-Größe
        
        Args:
            price: Ursprünglicher Preis
        
        Returns:
            Gerundeter Preis
        """
        tick = float(self.config.min_price_step)
        return round(round(price / tick) * tick, 12)

    def _compute_config_hash(self) -> str:
        """
        Berechnet Hash aus Grid-Config für Cache-Prüfung
        
        Returns:
            MD5-Hash der relevanten Config-Parameter
        """
        config_str = (
            f"{self.config.lower_price}|"
            f"{self.config.upper_price}|"
            f"{self.config.grid_levels}|"
            f"{self.config.grid_mode.value}|"
            f"{self.config.min_price_step}"
        )
        return hashlib.md5(config_str.encode()).hexdigest()

    def get_level_count(self) -> int:
        """Anzahl der Grid-Levels (n+1)"""
        return self.config.grid_levels + 1

    def get_grid_span(self) -> float:
        """Gesamte Grid-Spanne"""
        return self.config.upper_price - self.config.lower_price

    def get_average_step(self) -> float:
        """Durchschnittlicher Preis-Abstand"""
        return self.get_grid_span() / self.config.grid_levels

    def invalidate_cache(self):
        """Erzwingt Neuberechnung beim nächsten Aufruf"""
        self._cache_hash = ""
        self.logger.debug("Preisraster-Cache invalidiert")
