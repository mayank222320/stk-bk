# technical_indicators.py
# Calculates precise technical indicators from yfinance OHLCV data.
# These exact values are injected into the AI prompt so it uses real numbers
# instead of guessing from text descriptions.
# The AI is also instructed to cross-verify against its Gemini Search results.

import asyncio
from datetime import datetime, timezone
from typing import Any
import pandas as pd

SIGNIFICANT_DIVERGENCE_PCT = 2.0


async def fetch_technical_indicators(symbol: str) -> dict[str, Any]:
    """
    Downloads 6 months of daily + weekly OHLCV data for `symbol` (NSE).
    Calculates:
      - RSI(14), MACD(12,26,9), Bollinger Bands(20,2), ATR(14)
      - EMA 9/20/50/200, SMA 50/200, VWAP (approximate daily)
      - Weekly trend context (above/below weekly EMA 20)
      - Volume analysis: avg 5-day vs today's volume
    Returns a dict of precise values, or a partial dict on error.
    Never raises — always returns something.
    """
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, _compute_indicators, symbol)
        return result
    except Exception as exc:
        print(f"[TechnicalIndicators] Failed for {symbol}: {exc}")
        return {"symbol": symbol, "error": str(exc), "source": "failed"}


def _compute_indicators(symbol: str) -> dict[str, Any]:
    """Sync worker — runs in threadpool executor."""
    import yfinance as yf  # type: ignore

    ns = symbol.upper() + ".NS"

    # ── Daily data (6 months) ──────────────────────────────────────
    ticker = yf.Ticker(ns)
    df = ticker.history(period="6mo", interval="1d", auto_adjust=True)
    if df is None or df.empty or len(df) < 30:
        return {"symbol": symbol, "error": "Insufficient daily data", "source": "yfinance"}

    df = df.copy()

    from domain.calc.indicators import rsi as calc_rsi, atr as calc_atr, macd as calc_macd, bbands as calc_bbands, ema as calc_ema, sma as calc_sma
    from domain.calc.adx import adx as calc_adx
    from domain.calc.relative_strength import rs_raw, pct_from_52w_high, risk_adj_mom
    from domain.calc.pivots import swing_points, get_structure
    from domain.calc.pead import pead_52w

    # RSI (Wilder smoothed)
    rsi_series = calc_rsi(df["Close"], n=14)
    rsi = round(float(rsi_series.iloc[-1]), 2) if not rsi_series.empty and not pd.isna(rsi_series.iloc[-1]) else None

    # MACD (12, 26, 9)
    macd_line, sig_line, hist_line = calc_macd(df["Close"], fast=12, slow=26, signal=9)
    macd_val = round(float(macd_line.iloc[-1]), 3) if not macd_line.empty else None
    macd_sig = round(float(sig_line.iloc[-1]), 3) if not sig_line.empty else None
    macd_hist = round(float(hist_line.iloc[-1]), 3) if not hist_line.empty else None

    # Bollinger Bands (20, 2)
    b_up, b_mid, b_low = calc_bbands(df["Close"], n=20, k=2.0)
    bb_upper = round(float(b_up.iloc[-1]), 2) if not b_up.empty and not pd.isna(b_up.iloc[-1]) else None
    bb_mid = round(float(b_mid.iloc[-1]), 2) if not b_mid.empty and not pd.isna(b_mid.iloc[-1]) else None
    bb_lower = round(float(b_low.iloc[-1]), 2) if not b_low.empty and not pd.isna(b_low.iloc[-1]) else None

    # ATR (Wilder smoothed)
    atr_series = calc_atr(df["High"], df["Low"], df["Close"], n=14)
    atr = round(float(atr_series.iloc[-1]), 2) if not atr_series.empty and not pd.isna(atr_series.iloc[-1]) else None

    # EMAs & SMAs
    close_series = df["Close"]
    ema9 = round(float(calc_ema(close_series, 9).iloc[-1]), 2) if len(close_series) >= 9 else None
    ema20 = round(float(calc_ema(close_series, 20).iloc[-1]), 2) if len(close_series) >= 20 else None
    ema50 = round(float(calc_ema(close_series, 50).iloc[-1]), 2) if len(close_series) >= 50 else None
    ema200 = round(float(calc_ema(close_series, 200).iloc[-1]), 2) if len(close_series) >= 200 else None

    sma50 = round(float(calc_sma(close_series, 50).iloc[-1]), 2) if len(close_series) >= 50 else None
    sma200 = round(float(calc_sma(close_series, 200).iloc[-1]), 2) if len(close_series) >= 200 else None

    cmp = round(float(df["Close"].iloc[-1]), 2)

    # ── Tier 1 Analytics ──────────────────────────────────────
    # ADX
    adx_series, pdi, mdi = calc_adx(df["High"], df["Low"], df["Close"], 14)
    adx_val = round(float(adx_series.iloc[-1]), 2) if not adx_series.empty else None
    
    # Relative Strength
    rs_rating_raw = rs_raw(df["Close"])
    rs_rating = round(float(rs_rating_raw), 4) if not pd.isna(rs_rating_raw) else None
    pct_from_high = pct_from_52w_high(df["Close"])
    pct_from_high = round(float(pct_from_high), 2) if not pd.isna(pct_from_high) else None
    risk_mom = risk_adj_mom(df["Close"])
    risk_mom = round(float(risk_mom), 2) if not pd.isna(risk_mom) else None
    
    # Pivots
    ph, pl = swing_points(df["High"], df["Low"], 3)
    structure = get_structure(ph, pl)
    last_swing_low = round(float(pl.iloc[-1]), 2) if not pl.empty else None
    
    # PEAD
    pead = pead_52w(df["Close"])

    # ── Volume analysis ─────────────────────────────────────────────
    vol_today = int(df["Volume"].iloc[-1])
    vol_5d_avg = int(df["Volume"].tail(5).mean())
    vol_ratio = round(vol_today / vol_5d_avg, 2) if vol_5d_avg else None
    vol_signal = "above_avg" if vol_ratio and vol_ratio > 1.2 else ("below_avg" if vol_ratio and vol_ratio < 0.8 else "average")

    # ── Weekly trend context ─────────────────────────────────────────
    # Compute weekly trend unconditionally using pure EMA(20)
    weekly_trend = "N/A"
    try:
        df_w = ticker.history(period="2y", interval="1wk", auto_adjust=True)
        if df_w is not None and not df_w.empty and len(df_w) >= 20:
            w_ema20 = float(calc_ema(df_w["Close"], 20).iloc[-1])
            weekly_trend = "above_weekly_ema20" if cmp > w_ema20 else "below_weekly_ema20"
    except Exception as e:
        print(f"[TechnicalIndicators] Weekly trend error for {symbol}: {e}")

    # ── MACD signal interpretation ──────────────────────────────────
    macd_cross = "N/A"
    if macd_val is not None and macd_sig is not None:
        if macd_val > macd_sig and macd_hist and macd_hist > 0:
            macd_cross = "bullish_crossover" if macd_hist > 0 else "bullish_above_signal"
        elif macd_val < macd_sig:
            macd_cross = "bearish_below_signal"
        else:
            macd_cross = "neutral"

    # ── RSI interpretation ──────────────────────────────────────────
    rsi_zone = "N/A"
    if rsi is not None:
        if rsi >= 70:
            rsi_zone = "overbought"
        elif rsi <= 30:
            rsi_zone = "oversold"
        elif rsi >= 55:
            rsi_zone = "bullish_momentum"
        elif rsi <= 45:
            rsi_zone = "bearish_momentum"
        else:
            rsi_zone = "neutral"

    # ── Price vs key levels ─────────────────────────────────────────
    price_vs_ema50  = "above" if ema50  and cmp > ema50  else "below"
    price_vs_ema200 = "above" if ema200 and cmp > ema200 else "below"
    price_vs_bb_mid = "above" if bb_mid and cmp > bb_mid else "below"

    return {
        "symbol": symbol.upper(),
        "cmp": cmp,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "source": "yfinance_pandas_ta",

        # ── Momentum ────────────────────────────────────────
        "rsi_14": rsi,
        "rsi_zone": rsi_zone,

        "macd_line": macd_val,
        "macd_signal_line": macd_sig,
        "macd_histogram": macd_hist,
        "macd_interpretation": macd_cross,

        # ── Volatility ──────────────────────────────────────
        "atr_14": atr,
        "bollinger_upper": bb_upper,
        "bollinger_mid": bb_mid,
        "bollinger_lower": bb_lower,
        "price_vs_bollinger_mid": price_vs_bb_mid,

        # ── Trend ───────────────────────────────────────────
        "ema_9":   ema9,
        "ema_20":  ema20,
        "ema_50":  ema50,
        "ema_200": ema200,
        "sma_50":  sma50,
        "sma_200": sma200,
        "price_vs_ema50":  price_vs_ema50,
        "price_vs_ema200": price_vs_ema200,
        "weekly_trend": weekly_trend,

        # ── Volume ──────────────────────────────────────────
        "volume_today":  vol_today,
        "volume_5d_avg": vol_5d_avg,
        "volume_ratio":  vol_ratio,
        "volume_signal": vol_signal,

        # ── Tier 1 ──────────────────────────────────────────
        "adx_14": adx_val,
        "rs_rating_raw": rs_rating,
        "pct_from_52w_high": pct_from_high,
        "risk_adj_mom": risk_mom,
        "structure": structure,
        "last_swing_low": last_swing_low,
        "pead_signal": pead,

        # ── ATR-based stop-loss suggestion ──────────────────
        "atr_stop_loss_1_5x": round(cmp - 1.5 * atr, 2) if atr else None,
        "atr_stop_loss_1x":   round(cmp - atr, 2) if atr else None,
    }


async def fetch_option_chain(symbol: str) -> dict[str, Any]:
    """
    Fetches NSE option chain data via nsepython (free, no API key needed).
    Returns PCR, Max Pain, top Call/Put OI strikes.
    """
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, _compute_option_chain, symbol)
        return result
    except Exception as exc:
        print(f"[OptionChain] Failed for {symbol}: {exc}")
        return {"symbol": symbol, "error": str(exc), "source": "failed"}


def _compute_option_chain(symbol: str) -> dict[str, Any]:
    """Sync worker — runs in threadpool executor."""
    try:
        from nsepython import nse_optionchain_scrapper  # type: ignore
    except ImportError:
        return {"symbol": symbol, "error": "nsepython not installed", "source": "failed"}

    try:
        oc = nse_optionchain_scrapper(symbol.upper())
        records = oc.get("records", {})
        data    = records.get("data", [])
        expiry_dates = records.get("expiryDates", [])
        nearest_expiry = expiry_dates[0] if expiry_dates else "N/A"
        underlying_value = records.get("underlyingValue", None)

        total_call_oi = 0
        total_put_oi  = 0
        call_oi_map   = {}
        put_oi_map    = {}

        for item in data:
            strike = item.get("strikePrice", 0)
            ce = item.get("CE", {})
            pe = item.get("PE", {})
            c_oi = ce.get("openInterest", 0) or 0
            p_oi = pe.get("openInterest", 0) or 0
            total_call_oi += c_oi
            total_put_oi  += p_oi
            if c_oi: call_oi_map[strike] = c_oi
            if p_oi: put_oi_map[strike]  = p_oi

        pcr = round(total_put_oi / total_call_oi, 2) if total_call_oi else None

        # Top 3 Call/Put OI strikes (resistance/support)
        top_call_strikes = sorted(call_oi_map, key=call_oi_map.get, reverse=True)[:3]
        top_put_strikes  = sorted(put_oi_map,  key=put_oi_map.get,  reverse=True)[:3]

        # Max Pain = strike where total OI loss for option buyers is maximum
        max_pain = _calculate_max_pain(data)

        pcr_sentiment = "bullish" if pcr and pcr > 1 else ("bearish" if pcr and pcr < 0.8 else "neutral")

        return {
            "symbol": symbol.upper(),
            "nearest_expiry": nearest_expiry,
            "underlying_value": underlying_value,
            "pcr": pcr,
            "pcr_sentiment": pcr_sentiment,
            "total_call_oi": total_call_oi,
            "total_put_oi": total_put_oi,
            "max_pain": max_pain,
            "top_call_resistance_strikes": top_call_strikes,
            "top_put_support_strikes": top_put_strikes,
            "source": "nsepython_nse",
        }
    except Exception as exc:
        return {"symbol": symbol, "error": str(exc), "source": "nsepython_failed"}


def _calculate_max_pain(data: list) -> float | None:
    """Max Pain = strike where combined OI loss for all option buyers is minimum."""
    try:
        strikes = sorted(set(item["strikePrice"] for item in data if "strikePrice" in item))
        min_loss = float("inf")
        max_pain_strike = None
        for test_price in strikes:
            loss = 0
            for item in data:
                strike = item.get("strikePrice", 0)
                ce_oi = (item.get("CE") or {}).get("openInterest", 0) or 0
                pe_oi = (item.get("PE") or {}).get("openInterest", 0) or 0
                # Call holders lose if test_price < strike
                if test_price < strike:
                    loss += ce_oi * (strike - test_price)
                # Put holders lose if test_price > strike
                if test_price > strike:
                    loss += pe_oi * (test_price - strike)
            if loss < min_loss:
                min_loss = loss
                max_pain_strike = test_price
        return max_pain_strike
    except Exception:
        return None


async def fetch_fii_dii_flows() -> dict[str, Any]:
    """
    Fetches daily FII/DII equity buying/selling data from NSE (free, no API key).
    Returns net buy/sell figures in ₹ Crores.
    """
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, _compute_fii_dii)
        return result
    except Exception as exc:
        return {"error": str(exc), "source": "failed"}


def _compute_fii_dii() -> dict[str, Any]:
    """Fetches FII/DII data from NSE free endpoint."""
    import requests  # type: ignore

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://www.nseindia.com",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        session = requests.Session()
        # Warm up session cookie (NSE requires this)
        session.get("https://www.nseindia.com", headers=headers, timeout=10)

        resp = session.get(
            "https://www.nseindia.com/api/fiidiiTradeReact",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if not data:
            return {"error": "Empty response from NSE FII/DII endpoint", "source": "nse"}

        latest = data[0]  # Most recent trading day

        fii_buy  = float(latest.get("fiiBuy",  0) or 0)
        fii_sell = float(latest.get("fiiSell", 0) or 0)
        dii_buy  = float(latest.get("diiBuy",  0) or 0)
        dii_sell = float(latest.get("diiSell", 0) or 0)

        fii_net = round(fii_buy - fii_sell, 2)
        dii_net = round(dii_buy - dii_sell, 2)

        return {
            "date": latest.get("date", "N/A"),
            "fii_buy_cr":  fii_buy,
            "fii_sell_cr": fii_sell,
            "fii_net_cr":  fii_net,
            "fii_sentiment": "buyer" if fii_net > 0 else "seller",
            "dii_buy_cr":  dii_buy,
            "dii_sell_cr": dii_sell,
            "dii_net_cr":  dii_net,
            "dii_sentiment": "buyer" if dii_net > 0 else "seller",
            "combined_net_cr": round(fii_net + dii_net, 2),
            "source": "nse_fiidii_api",
        }
    except Exception as exc:
        return {"error": str(exc), "source": "nse_fiidii_failed"}


def format_technical_block(indicators: dict) -> str:
    """Formats technical indicators for injection into the Gemini prompt."""
    if indicators.get("error"):
        return f"[Technical Indicators] Unavailable — {indicators['error']}"

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"TECHNICAL INDICATORS (yfinance + pandas-ta) — {indicators.get('timestamp', 'N/A')}",
        "Cross-verify against your Gemini search. Flag any discrepancy > 2%.",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"CMP: ₹{indicators.get('cmp', 'N/A')}",
        "",
        "── Momentum ──",
        f"  RSI(14)       : {indicators.get('rsi_14', 'N/A')} → {indicators.get('rsi_zone', 'N/A').upper()}",
        f"  MACD Line     : {indicators.get('macd_line', 'N/A')}",
        f"  MACD Signal   : {indicators.get('macd_signal_line', 'N/A')}",
        f"  MACD Histogram: {indicators.get('macd_histogram', 'N/A')} → {indicators.get('macd_interpretation', 'N/A').upper()}",
        "",
        "── Tier 1 Analytics ──",
        f"  ADX(14)       : {indicators.get('adx_14', 'N/A')}",
        f"  RS Raw        : {indicators.get('rs_rating_raw', 'N/A')}",
        f"  From 52W High : {indicators.get('pct_from_52w_high', 'N/A')}%",
        f"  Risk Adj Mom  : {indicators.get('risk_adj_mom', 'N/A')}",
        f"  Structure     : {indicators.get('structure', 'N/A')}",
        f"  Swing Low     : ₹{indicators.get('last_swing_low', 'N/A')}",
        f"  PEAD Signal   : {indicators.get('pead_signal', 'N/A')}",
        "",
        "── Volatility ──",
        f"  ATR(14)       : ₹{indicators.get('atr_14', 'N/A')}",
        f"  ATR Stop(1.5x): ₹{indicators.get('atr_stop_loss_1_5x', 'N/A')} ← suggested stop-loss",
        f"  BB Upper      : ₹{indicators.get('bollinger_upper', 'N/A')}",
        f"  BB Mid        : ₹{indicators.get('bollinger_mid', 'N/A')}",
        f"  BB Lower      : ₹{indicators.get('bollinger_lower', 'N/A')}",
        "",
        "── Trend ──",
        f"  EMA 9         : ₹{indicators.get('ema_9', 'N/A')}",
        f"  EMA 20        : ₹{indicators.get('ema_20', 'N/A')}",
        f"  EMA 50        : ₹{indicators.get('ema_50', 'N/A')} ← Price is {indicators.get('price_vs_ema50', 'N/A')} this",
        f"  EMA 200       : ₹{indicators.get('ema_200', 'N/A')} ← Price is {indicators.get('price_vs_ema200', 'N/A')} this",
        f"  Weekly Trend  : {indicators.get('weekly_trend', 'N/A').upper()}",
        "",
        "── Volume ──",
        f"  Today Volume  : {indicators.get('volume_today', 'N/A'):,}" if indicators.get('volume_today') else "  Today Volume  : N/A",
        f"  5-Day Avg Vol : {indicators.get('volume_5d_avg', 'N/A'):,}" if indicators.get('volume_5d_avg') else "  5-Day Avg Vol : N/A",
        f"  Vol Ratio     : {indicators.get('volume_ratio', 'N/A')}x → {indicators.get('volume_signal', 'N/A').upper()}",
    ]
    return "\n".join(lines)


def format_option_chain_block(oc: dict) -> str:
    """Formats option chain data for injection into the Gemini prompt."""
    if oc.get("error"):
        return f"[Option Chain] Unavailable — {oc['error']}"

    return (
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"OPTION CHAIN DATA (NSE) — Expiry: {oc.get('nearest_expiry', 'N/A')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"  Spot Price     : ₹{oc.get('underlying_value', 'N/A')}\n"
        f"  PCR            : {oc.get('pcr', 'N/A')} → {str(oc.get('pcr_sentiment', 'N/A')).upper()}\n"
        f"  Max Pain       : ₹{oc.get('max_pain', 'N/A')} (expiry magnet)\n"
        f"  Top Resistance (Call OI): {oc.get('top_call_resistance_strikes', [])}\n"
        f"  Top Support    (Put OI) : {oc.get('top_put_support_strikes', [])}\n"
    )


def format_fii_dii_block(flows: dict) -> str:
    """Formats FII/DII flows for injection into the Gemini prompt."""
    if flows.get("error"):
        return f"[FII/DII Flows] Unavailable — {flows['error']}"

    fii_emoji = "🟢" if flows.get("fii_sentiment") == "buyer" else "🔴"
    dii_emoji = "🟢" if flows.get("dii_sentiment") == "buyer" else "🔴"

    return (
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"FII/DII INSTITUTIONAL FLOWS — {flows.get('date', 'N/A')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"  {fii_emoji} FII Net : ₹{flows.get('fii_net_cr', 'N/A')} Cr ({flows.get('fii_sentiment', 'N/A').upper()})\n"
        f"  {dii_emoji} DII Net : ₹{flows.get('dii_net_cr', 'N/A')} Cr ({flows.get('dii_sentiment', 'N/A').upper()})\n"
        f"  Combined Net    : ₹{flows.get('combined_net_cr', 'N/A')} Cr\n"
    )
