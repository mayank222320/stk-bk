import numpy as np
import pandas as pd


def calculate_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume."""
    obv = (np.sign(close.diff()) * volume).fillna(0).cumsum()
    return obv

def calculate_cmf(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, window: int = 21) -> pd.Series:
    """Chaikin Money Flow."""
    mfm = ((close - low) - (high - close)) / (high - low).replace(0, np.nan)
    cmf = (mfm * volume).rolling(window).sum() / volume.rolling(window).sum()
    return cmf

def calculate_ud_ratio(close: pd.Series, volume: pd.Series, window: int = 50) -> float:
    """Up/Down Volume Ratio."""
    if len(close) < window + 1:
        return float('nan')
    diff = close.diff().tail(window)
    vol = volume.tail(window)
    up_vol = vol[diff > 0].sum()
    dn_vol = vol[diff < 0].sum()
    if dn_vol == 0:
        return float('inf') if up_vol > 0 else 1.0
    return float(up_vol / dn_vol)

def calculate_delivery_ratio(delivery_5d_avg: float, delivery_60d_baseline: float) -> float:
    """Delivery % relative to its own baseline."""
    if delivery_60d_baseline == 0 or pd.isna(delivery_60d_baseline):
        return float('nan')
    return float(delivery_5d_avg / delivery_60d_baseline)

def flow_metrics(df: pd.DataFrame) -> dict:
    """Computes flow metrics."""
    if len(df) < 51:
        return {"obv": "UNAVAILABLE", "cmf": "UNAVAILABLE", "ud_ratio": "UNAVAILABLE"}

    obv = calculate_obv(df["Close"], df["Volume"])
    cmf = calculate_cmf(df["High"], df["Low"], df["Close"], df["Volume"])
    ud_ratio = calculate_ud_ratio(df["Close"], df["Volume"])

    return {
        "obv": float(obv.iloc[-1]) if not pd.isna(obv.iloc[-1]) else "UNAVAILABLE",
        "cmf": float(cmf.iloc[-1]) if not pd.isna(cmf.iloc[-1]) else "UNAVAILABLE",
        "ud_ratio": float(ud_ratio) if not pd.isna(ud_ratio) else "UNAVAILABLE"
    }
