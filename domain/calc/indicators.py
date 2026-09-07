"""
Pure mathematical implementations of technical indicators.
Pure functions: take Pandas Series / DataFrames, return Series / tuples.
Zero external I/O, no network or database dependencies.
"""
import numpy as np
import pandas as pd


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """
    Relative Strength Index with Wilder smoothing (alpha=1/n).
    Formula: RSI = 100 - 100 / (1 + RS)
    where RS = Wilder_EMA(gain, n) / Wilder_EMA(loss, n)
    """
    d = close.diff()
    up = d.clip(lower=0)
    dn = (-d).clip(lower=0)
    roll_up = up.ewm(alpha=1.0 / n, adjust=False).mean()
    roll_dn = dn.ewm(alpha=1.0 / n, adjust=False).mean()

    # When roll_dn == 0 (no losses), RSI is 100
    rs = roll_up / roll_dn
    res = 100.0 - (100.0 / (1.0 + rs))
    res = res.fillna(100.0).clip(lower=0.0, upper=100.0)
    return res


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    """
    Average True Range using Wilder smoothing.
    TR = max(H - L, |H - Close_prev|, |L - Close_prev|)
    ATR = Wilder_EMA(TR, n)
    """
    pc = close.shift(1)
    tr1 = high - low
    tr2 = (high - pc).abs()
    tr3 = (low - pc).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False).mean()


def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Moving Average Convergence Divergence.
    Returns: (macd_line, signal_line, histogram)
    """
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    line = ema_fast - ema_slow
    sig = line.ewm(span=signal, adjust=False).mean()
    hist = line - sig
    return line, sig, hist


def bbands(
    close: pd.Series,
    n: int = 20,
    k: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Bollinger Bands.
    Returns: (upper_band, middle_band, lower_band)
    """
    mid = close.rolling(n).mean()
    std = close.rolling(n).std()
    upper = mid + (k * std)
    lower = mid - (k * std)
    return upper, mid, lower


def adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    n: int = 14,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Average Directional Index with Wilder smoothing.
    Returns: (adx_series, plus_di, minus_di)
    """
    up = high.diff()
    dn = -low.diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)

    tr_series = pd.concat(
        [high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()],
        axis=1,
    ).max(axis=1)
    atr_series = tr_series.ewm(alpha=1.0 / n, adjust=False).mean().replace(0, np.nan)

    pdi = (
        100.0
        * pd.Series(plus_dm, index=high.index).ewm(alpha=1.0 / n, adjust=False).mean()
        / atr_series
    )
    mdi = (
        100.0
        * pd.Series(minus_dm, index=high.index).ewm(alpha=1.0 / n, adjust=False).mean()
        / atr_series
    )

    dx_denom = (pdi + mdi).replace(0, np.nan)
    dx = 100.0 * (pdi - mdi).abs() / dx_denom
    adx_series = dx.ewm(alpha=1.0 / n, adjust=False).mean().clip(lower=0.0, upper=100.0)
    return adx_series, pdi, mdi


def ema(close: pd.Series, span: int) -> pd.Series:
    """Exponential Moving Average."""
    return close.ewm(span=span, adjust=False).mean()


def sma(close: pd.Series, window: int) -> pd.Series:
    """Simple Moving Average."""
    return close.rolling(window).mean()
