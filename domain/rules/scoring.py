from typing import Any

import pandas as pd

from domain.calc.indicators import atr, macd, rsi


def score_universe(symbols: list[str], frames: dict[str, pd.DataFrame], regime: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Score the universe based on deterministic rules suited to a 2-10 day hold.
    Applies exclusions: illiquid.
    """
    out = []

    nifty_close = regime.get("nifty")

    for sym in symbols:
        df = frames.get(sym)
        if df is None or len(df) < 200:
            continue

        c = df["Close"]
        e20 = c.ewm(span=20, adjust=False).mean()
        e50 = c.ewm(span=50, adjust=False).mean()

        r = float(rsi(c).iloc[-1])
        _, _, hist = macd(c)

        a = float(atr(df["High"], df["Low"], c).iloc[-1])
        atr_pct = a / float(c.iloc[-1]) * 100

        vol_ratio = float(df["Volume"].tail(5).mean() / df["Volume"].tail(20).mean())
        turnover_cr = float(c.iloc[-1]) * float(df["Volume"].tail(5).mean()) / 10000000.0

        # RS rank vs Nifty 500 equivalent (using regime nifty as proxy if available)
        rs20 = 1.0
        if nifty_close is not None and len(nifty_close) >= 21 and len(c) >= 21:
            try:
                sym_ret = c.iloc[-1] / c.iloc[-21]
                idx_ret = nifty_close.iloc[-1] / nifty_close.iloc[-21]
                rs20 = float(sym_ret / idx_ret)
            except Exception:
                pass

        # Weekly uptrend
        wk = c.resample("W").last()
        if len(wk) >= 20:
            wk_e20 = wk.ewm(span=20, adjust=False).mean()
            weekly_ok = bool(wk.iloc[-1] > wk_e20.iloc[-1])
        else:
            weekly_ok = False

        s = 0
        why = []

        cmp_ = float(c.iloc[-1])
        e20_ = float(e20.iloc[-1])
        e50_ = float(e50.iloc[-1])

        if cmp_ > e20_ > e50_:
            s += 20
            why.append("trend stack")

        if float(e50.iloc[-1]) > float(e50.iloc[-6]):
            s += 10
            why.append("EMA50 rising")

        if weekly_ok:
            s += 15
            why.append("weekly uptrend")

        if 50 <= r <= 68:
            s += 15
            why.append(f"RSI {r:.0f}")
        elif r > 72:
            s -= 15
            why.append("overbought")

        if float(hist.iloc[-1]) > 0 > float(hist.iloc[-3]):
            s += 10
            why.append("MACD turn")

        if rs20 > 1.02:
            s += 15
            why.append("beating Nifty")

        if vol_ratio > 1.2:
            s += 10
            why.append("volume expanding")

        if 1.5 <= atr_pct <= 6:
            s += 5
        else:
            s -= 10
            why.append("volatility unsuitable")

        if turnover_cr < 5:
            s -= 40
            why.append("illiquid")

        high20 = float(c.tail(20).max())
        dist = (high20 - cmp_) / cmp_ * 100

        if dist < 3:
            setup = "BREAKOUT"
        elif abs(cmp_ - e20_) / cmp_ < 0.02:
            setup = "PULLBACK"
        else:
            setup = "MOMENTUM_CONTINUATION"

        out.append({
            "symbol": sym,
            "score": s,
            "setup_type": setup,
            "reasons": why,
            "cmp": round(cmp_, 2),
            "rsi": round(r, 1),
            "atr": round(a, 2),
            "suggested_stop": round(cmp_ - 1.5 * a, 2),
            "turnover_cr": round(turnover_cr, 1)
        })

    return sorted(out, key=lambda x: -x["score"])
