import pandas as pd


def swing_points(high_s: pd.Series, low_s: pd.Series, k: int = 3) -> tuple[pd.Series, pd.Series]:
    """Fractal pivots: a high with k lower highs on both sides (and vice versa)."""
    ph = high_s[high_s == high_s.rolling(2 * k + 1, center=True).max()].dropna()
    pl = low_s[low_s == low_s.rolling(2 * k + 1, center=True).min()].dropna()
    return ph, pl


def get_swing_structure(high_s: pd.Series, low_s: pd.Series, k: int = 3) -> str:
    """Returns HH_HL, LH_LL, or RANGE based on the last two swing pivots."""
    ph, pl = swing_points(high_s, low_s, k)
    if len(ph) < 2 or len(pl) < 2:
        return "UNKNOWN"

    if ph.iloc[-1] > ph.iloc[-2] and pl.iloc[-1] > pl.iloc[-2]:
        return "HH_HL"
    if ph.iloc[-1] < ph.iloc[-2] and pl.iloc[-1] < pl.iloc[-2]:
        return "LH_LL"
    else:
        return "RANGE"
