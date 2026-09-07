import numpy as np
import pandas as pd


def adx(high_s: pd.Series, low_s: pd.Series, close_s: pd.Series, n: int = 14) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Average Directional Index with Wilder smoothing.
    Returns: (adx_series, plus_di, minus_di)
    """
    up = high_s.diff()
    dn = -low_s.diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)

    tr_series = pd.concat(
        [high_s - low_s, (high_s - close_s.shift(1)).abs(), (low_s - close_s.shift(1)).abs()],
        axis=1,
    ).max(axis=1)
    atr_series = tr_series.ewm(alpha=1.0 / n, adjust=False).mean().replace(0, np.nan)

    pdi = (
        100.0
        * pd.Series(plus_dm, index=high_s.index).ewm(alpha=1.0 / n, adjust=False).mean()
        / atr_series
    )
    mdi = (
        100.0
        * pd.Series(minus_dm, index=high_s.index).ewm(alpha=1.0 / n, adjust=False).mean()
        / atr_series
    )

    dx_denom = (pdi + mdi).replace(0, np.nan)
    dx = 100.0 * (pdi - mdi).abs() / dx_denom
    adx_series = dx.ewm(alpha=1.0 / n, adjust=False).mean().clip(lower=0.0, upper=100.0)
    return adx_series, pdi, mdi
