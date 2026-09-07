import numpy as np
import pandas as pd


def volume_profile(df: pd.DataFrame, bins: int = 30, lookback: int = 60) -> dict:
    """
    Volume Profile - returns Point of Control (POC), Value Area High (VAH), and Value Area Low (VAL).
    Calculates 70% value area around POC.
    """
    if len(df) < 1:
        return {"poc": "UNAVAILABLE", "vah": "UNAVAILABLE", "val": "UNAVAILABLE", "position": "UNAVAILABLE"}
    d = df.tail(lookback)
    if not all(col in d.columns for col in ["High", "Low", "Close", "Volume"]):
        return {"poc": "UNAVAILABLE", "vah": "UNAVAILABLE", "val": "UNAVAILABLE", "position": "UNAVAILABLE"}

    typical = (d["High"] + d["Low"] + d["Close"]) / 3
    if typical.isnull().all() or d["Volume"].sum() == 0:
        return {"poc": "UNAVAILABLE", "vah": "UNAVAILABLE", "val": "UNAVAILABLE", "position": "UNAVAILABLE"}

    hist, edges = np.histogram(typical.dropna(), bins=bins, weights=d["Volume"].dropna())

    if hist.sum() == 0:
        return {"poc": "UNAVAILABLE", "vah": "UNAVAILABLE", "val": "UNAVAILABLE", "position": "UNAVAILABLE"}

    i = int(hist.argmax())
    poc = (edges[i] + edges[i+1]) / 2
    order, cum, sel = hist.argsort()[::-1], 0, []

    for j in order:
        sel.append(int(j))
        cum += hist[j]
        if cum >= 0.70 * hist.sum():
            break

    vah = float(edges[max(sel)+1])
    val = float(edges[min(sel)])

    last_close = float(d["Close"].iloc[-1])

    position = "in_value"
    if last_close > vah:
        position = "above_value"
    elif last_close < val:
        position = "below_value"

    return {
        "poc": round(poc, 2),
        "vah": round(vah, 2),
        "val": round(val, 2),
        "position": position
    }
