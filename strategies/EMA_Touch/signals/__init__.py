"""
Signal-Generierung für EMA Touch Strategie
"""

from .ema21_touch import check_ema21_touch, generate_trade_signal

__all__ = [
    'check_ema21_touch',
    'generate_trade_signal'
]