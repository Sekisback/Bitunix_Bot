import pandas as pd
import logging
from typing import Dict, Optional

# Absolute Imports
from indicators import check_ema_hierarchy, check_trend_strength


def check_ema21_touch(df: pd.DataFrame, 
                     ema_fast: int = 21,
                     threshold_pct: float = 0.05) -> dict:
    """
    Prüft ob Preis nahe an EMA21 ist (Touch)
    
    Args:
        df: DataFrame mit Preisen und EMAs
        ema_fast: Schnelle EMA Periode
        threshold_pct: Max Abstand in % (0.05 = 0.05%)
    
    Returns:
        Dict mit is_touch, distance_pct, side
    """
    # Aktueller Preis
    current_price = df['close'].iloc[-1]
    # EMA21 Wert
    ema_val = df[f'ema_{ema_fast}'].iloc[-1]
    
    # Prüfe auf gültige Werte
    if pd.isna(current_price) or pd.isna(ema_val) or ema_val <= 0:
        return {
            "is_touch": False,
            "distance_pct": 999.0,
            "side": None
        }
    
    # Abstand in Prozent
    distance_pct = abs((current_price - ema_val) / ema_val * 100)
    
    # Touch wenn innerhalb threshold
    is_touch = distance_pct <= threshold_pct
    
    # Seite bestimmen (von welcher Seite nähert sich Preis?)
    if current_price >= ema_val:
        side = " oben"  # Preis kommt von oben
    else:
        side = " unten"  # Preis kommt von unten
    
    #logging.debug(f"EMA{ema_fast} Touch Check: Preis={current_price:.5f}, EMA={ema_val:.5f}, Abstand={distance_pct:.3f}%, Touch={is_touch}")
    
    return {
        "is_touch": is_touch,
        "distance_pct": distance_pct,
        "side": side
    }


def generate_trade_signal(df: pd.DataFrame, config: dict) -> dict:
    """
    Generiert Trade Signal basierend auf allen Bedingungen
    
    Args:
        df: DataFrame mit Preisen und Indikatoren
        config: Config Dictionary mit allen Parametern
    
    Returns:
        Dict mit signal ("LONG", "SHORT", None), reason, tp, sl, entry_price
    """
    # Config Werte extrahieren
    use_filter = config['trend_filter']['use_filter']
    adx_threshold = config['trend_filter']['adx_threshold']
    ema_distance_threshold = config['trend_filter']['ema_distance_threshold']
    ema_fast = config['indicators']['ema_fast']
    ema_slow = config['indicators']['ema_slow']
    ema_trend = config['indicators']['ema_trend']
    touch_threshold = config['entry']['touch_threshold_pct']
    leverage = config['trading']['leverage']
    tp_pct = config['risk']['tp_pct']
    sl_pct = config['risk']['sl_pct']
    fee_pct = config['risk']['fee_pct']
    
    # Gesamte Gebühren
    total_fees = fee_pct * 2
    
    # 2. EMA Hierarchie IMMER prüfen (auch wenn Filter aus)
    hierarchy = check_ema_hierarchy(df, fast=ema_fast, slow=ema_slow, trend=ema_trend, debug=False)
    
    # Setup Info für bessere Meldungen
    if hierarchy["long_ok"]:
        setup_type = "Long Setup vorhanden, aber"
    elif hierarchy["short_ok"]:
        setup_type = "Short Setup vorhanden, aber"
    else:
        setup_type = "Kein Setup vorhanden, und"
    
    # 1. Trendfilter prüfen (wenn aktiviert)
    if use_filter:
        trend_check = check_trend_strength(
            df,
            adx_threshold=adx_threshold,
            ema_distance_threshold=ema_distance_threshold,
            ema_fast=ema_fast,
            ema_slow=ema_slow
        )
        
        if not trend_check["is_trending"]:
            # Bessere Reason mit Setup-Info
            return {
                "signal": None,
                "reason": f"{setup_type} Trend zu schwach: {trend_check['reason']}",
                "tp": None,
                "sl": None,
                "entry_price": None
            }
    
    # 3. EMA Touch prüfen
    touch = check_ema21_touch(df, ema_fast=ema_fast, threshold_pct=touch_threshold)

    if touch["is_touch"]:
        logging.info("=" * 60)
        logging.info("👆 EMA21 TOUCH ERKANNT!")
        logging.info("=" * 60)
        logging.info(f"Touch Side:     {touch['side']}")
        logging.info(f"Distanz:        {touch['distance_pct']:.3f}%")
        logging.info(f"Long möglich:   {'✅ JA' if hierarchy['long_ok'] else '❌ NEIN'}")
        logging.info(f"Short möglich:  {'✅ JA' if hierarchy['short_ok'] else '❌ NEIN'}")
        logging.info(f"EMA{ema_fast}:  {hierarchy[f'ema{ema_fast}']:.5f}")
        logging.info(f"EMA{ema_slow}:  {hierarchy[f'ema{ema_slow}']:.5f}")
        logging.info(f"EMA{ema_trend}: {hierarchy[f'ema{ema_trend}']:.5f}")
        logging.info(f"Hierarchie:     {hierarchy['reason']}")
        
        # Prüfe ob Signal kommt
        will_trade = False
        if hierarchy["long_ok"] and touch["side"] == "from_above":
            will_trade = True
            logging.info("➡️ LONG Signal wird generiert!")
        elif hierarchy["short_ok"] and touch["side"] == "from_below":
            will_trade = True
            logging.info("➡️ SHORT Signal wird generiert!")
        else:
            logging.info("❌ KEIN Signal - Bedingungen:")
            if not hierarchy["long_ok"] and not hierarchy["short_ok"]:
                logging.info("   • EMA Hierarchie nicht erfüllt")
            if hierarchy["long_ok"] and touch["side"] != "from_above":
                logging.info(f"   • Long Setup, aber Touch {touch['side']} (braucht from_above)")
            if hierarchy["short_ok"] and touch["side"] != "from_below":
                logging.info(f"   • Short Setup, aber Touch {touch['side']} (braucht from_below)")
        
        logging.info("=" * 60)
    
    # Aktueller Preis
    current_price = df['close'].iloc[-1]
    # EMA50 für Stop Loss
    ema_slow_val = df[f'ema_{ema_slow}'].iloc[-1]
    
    # TP/SL auf Margin-Basis berechnen (Hebel UND Gebühren berücksichtigen)
    # Gebühren in Prozent auf Positionsgröße
    fee_impact = total_fees
    
    # TP: Gewünschter Gewinn auf Margin + Gebühren
    # z.B. 1% auf Margin = 1% / Hebel Preisänderung + Gebühren
    tp_price_pct = (tp_pct / leverage) + fee_impact
    
    # SL: Gewünschter Verlust auf Margin + Gebühren
    # z.B. 0.5% auf Margin = 0.5% / Hebel Preisänderung + Gebühren
    sl_price_pct = (sl_pct / leverage) + fee_impact
    
    # === LONG SIGNAL ===
    if hierarchy["long_ok"] and touch["is_touch"] and touch["side"] == "from_above":
        # TP: Preisänderung inkl. Gebühren
        tp_price = current_price * (1 + tp_price_pct)
        
        # SL: Preisänderung inkl. Gebühren
        sl_calculated = current_price * (1 - sl_price_pct)
        # Nutze EMA50 wenn es einen besseren (höheren) SL ergibt
        sl_price = max(ema_slow_val, sl_calculated)
        
        return {
            "signal": "LONG",
            "reason": f"EMA Hierarchie OK + Touch EMA{ema_fast} von oben",
            "tp": tp_price,
            "sl": sl_price,
            "entry_price": current_price
        }
    
    # === SHORT SIGNAL ===
    elif hierarchy["short_ok"] and touch["is_touch"] and touch["side"] == "from_below":
        # TP: Preisänderung inkl. Gebühren
        tp_price = current_price * (1 - tp_price_pct)
        
        # SL: Preisänderung inkl. Gebühren
        sl_calculated = current_price * (1 + sl_price_pct)
        # Nutze EMA50 wenn es einen besseren (niedrigeren) SL ergibt
        sl_price = min(ema_slow_val, sl_calculated)
        
        return {
            "signal": "SHORT",
            "reason": f"EMA Hierarchie OK + Touch EMA{ema_fast} von unten",
            "tp": tp_price,
            "sl": sl_price,
            "entry_price": current_price
        }
    
    # === KEIN SIGNAL ===
    else:
        reasons = []
        if not hierarchy["long_ok"] and not hierarchy["short_ok"]:
            reasons.append("Keine EMA Hierarchie")
        if not touch["is_touch"]:
            reasons.append(f"Kein EMA{ema_fast} Touch (Abstand: {touch['distance_pct']:.3f}%)")
        
        return {
            "signal": None,
            "reason": " | ".join(reasons) if reasons else "Keine Bedingung erfüllt",
            "tp": None,
            "sl": None,
            "entry_price": None
        }