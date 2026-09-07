import numpy as np
import pandas as pd


def rs_raw(c: pd.Series) -> float:
    """IBD-style weighted return: recent quarter counts double."""
    if len(c) < 253:
        return np.nan

    def r(n: int) -> float:
        return c.iloc[-1] / c.iloc[-(n+1)] - 1

    return 0.4 * r(63) + 0.2 * r(126) + 0.2 * r(189) + 0.2 * r(252)

def pct_from_52w_high(c: pd.Series) -> float:
    """Returns the percentage the current close is from its 52-week high."""
    if len(c) < 252:
        return np.nan
    high_52w = c.tail(252).max()
    return (high_52w - c.iloc[-1]) / high_52w * 100

def risk_adj_mom(c: pd.Series) -> float:
    """Risk-adjusted momentum."""
    if len(c) < 64:
        return np.nan
    ret = (c.iloc[-1] / c.iloc[-64] - 1)
    vol = c.pct_change().tail(63).std() * np.sqrt(252)
    if vol == 0:
        return np.nan
    return ret / vol
