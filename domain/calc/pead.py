import pandas as pd


def pead_52w(c: pd.Series) -> str:
    """
    PEAD_52W (dummy implementation).
    Simple momentum near highs for now, since earnings dates aren't easily available.
    """
    if len(c) < 252:
        return "UNAVAILABLE"

    high_52w = c.tail(252).max()
    pct_from_high = (high_52w - c.iloc[-1]) / high_52w * 100

    if pct_from_high <= 8:
        return "MOMENTUM_NEAR_HIGH"
    return "NO_SIGNAL"
