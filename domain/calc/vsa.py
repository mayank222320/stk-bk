import pandas as pd

from domain.calc.indicators import atr


def vsa_classify(df: pd.DataFrame) -> str:
    """
    Quantified VSA — effort vs result
    """
    if len(df) < 20:
        return "UNAVAILABLE"

    r = df["High"] - df["Low"]
    atr_series = atr(df["High"], df["Low"], df["Close"])

    if atr_series.iloc[-1] == 0 or pd.isna(atr_series.iloc[-1]):
        return "NEUTRAL"

    rr = r.iloc[-1] / atr_series.iloc[-1]

    vol_avg = df["Volume"].rolling(20).mean()
    if vol_avg.iloc[-1] == 0 or pd.isna(vol_avg.iloc[-1]):
        return "NEUTRAL"

    vr = df["Volume"].iloc[-1] / vol_avg.iloc[-1]

    if r.iloc[-1] == 0:
        cp = 0.5
    else:
        cp = (df["Close"].iloc[-1] - df["Low"].iloc[-1]) / r.iloc[-1]

    up = df["Close"].iloc[-1] > df["Close"].iloc[-2]

    if vr > 1.8 and rr < 0.8 and cp > 0.6:
        return "ABSORPTION_STOPPING_VOLUME"
    if vr > 1.8 and rr < 0.8 and cp < 0.4:
        return "DISTRIBUTION_SUPPLY"
    if vr > 2.5 and rr > 1.8 and cp > 0.7:
        return "CLIMACTIC_BUYING"
    if vr > 2.5 and rr > 1.8 and cp < 0.3:
        return "SELLING_CLIMAX"
    if vr < 0.7 and rr < 0.6 and up:
        return "NO_DEMAND"
    if vr < 0.7 and rr < 0.6 and not up:
        return "NO_SUPPLY"
    if vr > 1.5 and rr > 1.2 and up and cp > 0.7:
        return "PROFESSIONAL_BUYING"

    return "NEUTRAL"
