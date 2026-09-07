import pandas as pd


def calculate_iv_rank(iv_current: float, iv_52w_min: float, iv_52w_max: float) -> float:
    """IV Rank calculation."""
    if iv_52w_max == iv_52w_min:
        return 0.0
    return ((iv_current - iv_52w_min) / (iv_52w_max - iv_52w_min)) * 100.0

def calculate_iv_percentile(iv_current: float, iv_history: pd.Series) -> float:
    """IV Percentile calculation."""
    if len(iv_history) == 0:
        return float('nan')
    return float((iv_history < iv_current).mean() * 100.0)

def calculate_futures_basis(fut_price: float, spot_price: float) -> float:
    """Futures basis %."""
    if spot_price == 0:
        return float('nan')
    return ((fut_price - spot_price) / spot_price) * 100.0

def calculate_rollover_pct(oi_rolled: float, oi_total: float) -> float:
    """Rollover %."""
    if oi_total == 0:
        return float('nan')
    return (oi_rolled / oi_total) * 100.0

def interpret_oi_buildup(price_change_pct: float, oi_change_pct: float) -> str:
    """
    OI build-up interpretation.
    """
    if price_change_pct > 0 and oi_change_pct > 0:
        return "LONG_BUILDUP"
    elif price_change_pct > 0 and oi_change_pct < 0:
        return "SHORT_COVERING"
    elif price_change_pct < 0 and oi_change_pct > 0:
        return "SHORT_BUILDUP"
    elif price_change_pct < 0 and oi_change_pct < 0:
        return "LONG_UNWINDING"
    return "NEUTRAL"
