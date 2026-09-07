# market_data feature: yfinance as data verification layer only.
# Gemini is the primary research source; yfinance cross-verifies numeric data.

import asyncio
import json
from datetime import datetime
from typing import Any

SIGNIFICANT_DIVERGENCE_PCT = 2.0  # flag if price differs by more than 2%


async def fetch_for_verification(symbol: str) -> dict[str, Any]:
    """
    Pull raw numeric data from yfinance for cross-verification with Gemini's research.
    Falls back to nsepython if yfinance fails.
    Returns None values for unavailable fields — never raises.
    """
    result = await _fetch_yfinance(symbol)
    if result:
        return result

    result = await _fetch_nsepython(symbol)
    if result:
        return result

    return {
        "symbol": symbol.upper(),
        "cmp": None,
        "open": None,
        "high": None,
        "low": None,
        "volume": None,
        "change_pct": None,
        "prev_close": None,
        "week_52_high": None,
        "week_52_low": None,
        "source": "unavailable",
        "error": "All data sources failed — Gemini data will be used as-is",
    }


async def fetch_verification_batch(symbols: list[str]) -> dict[str, dict[str, Any]]:
    """Fetch verification data for all symbols concurrently."""
    results = await asyncio.gather(*[fetch_for_verification(s) for s in symbols])
    return {r["symbol"]: r for r in results}


def cross_check(
    symbol: str,
    yf_price: float | None,
    nse_price: float | None,
) -> dict[str, Any]:
    """
    Compare yfinance reported price against nse.
    Returns a verdict dict:
      - match: True/False
      - divergence_pct: numeric divergence
      - verdict: "match" | "significant_divergence" | "unverifiable"
      - note: human-readable explanation
    """
    if yf_price is None or nse_price is None:
        return {
            "match": None,
            "divergence_pct": None,
            "verdict": "unverifiable",
            "note": "one of the sources is unavailable",
            "yfinance_price": yf_price,
            "nse_price": nse_price,
        }

    divergence = abs(yf_price - nse_price) / max(yf_price, 1e-9) * 100

    if divergence <= SIGNIFICANT_DIVERGENCE_PCT:
        verdict = "match"
        note = f"Prices align within {divergence:.2f}% — data verified."
    else:
        verdict = "significant_divergence"
        note = (
            f"⚠️ Divergence of {divergence:.2f}% detected "
            f"(yfinance: ₹{yf_price}, nse: ₹{nse_price}). "
        )

    return {
        "match": divergence <= SIGNIFICANT_DIVERGENCE_PCT,
        "divergence_pct": round(divergence, 2),
        "verdict": verdict,
        "note": note,
        "yfinance_price": yf_price,
        "nse_price": nse_price,
    }


def format_verification_block(symbol: str, check: dict[str, Any]) -> str:
    """Format cross-check result for injection into the final Gemini prompt."""
    return (
        f"[Data Verification — {symbol}]\n"
        f"  yfinance CMP : ₹{check['yfinance_price']}\n"
        f"  NSE CMP      : ₹{check['nse_price']}\n"
        f"  Verdict      : {check['verdict'].upper()}\n"
        f"  Note         : {check['note']}\n"
    )


# ─────────────────────── yfinance ───────────────────────
async def _fetch_yfinance(symbol: str) -> dict[str, Any] | None:
    try:
        import yfinance as yf  # type: ignore

        loop = asyncio.get_event_loop()
        ticker = await loop.run_in_executor(None, yf.Ticker, symbol.upper() + ".NS")
        info = await loop.run_in_executor(None, lambda: ticker.info)
        hist = await loop.run_in_executor(
            None, lambda: ticker.history(period="5d", interval="1d")
        )

        if hist.empty:
            return None

        last = hist.iloc[-1]
        prev = hist.iloc[-2] if len(hist) > 1 else last
        cmp = float(last["Close"])
        prev_close = float(prev["Close"])
        change_pct = round((cmp - prev_close) / prev_close * 100, 2) if prev_close else 0

        return {
            "symbol": symbol.upper(),
            "cmp": cmp,
            "open": float(last["Open"]),
            "high": float(last["High"]),
            "low": float(last["Low"]),
            "volume": int(last["Volume"]),
            "change_pct": change_pct,
            "prev_close": prev_close,
            "week_52_high": info.get("fiftyTwoWeekHigh"),
            "week_52_low": info.get("fiftyTwoWeekLow"),
            "avg_volume_5d": info.get("averageVolume"),
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "timestamp": datetime.utcnow().isoformat(),
            "source": "yfinance",
        }
    except Exception as exc:
        print(f"[yfinance] Failed for {symbol}: {exc}")
        return None


# ─────────────────────── nsepython ───────────────────────
async def _fetch_nsepython(symbol: str) -> dict[str, Any] | None:
    try:
        from nsepython import nse_eq  # type: ignore

        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, nse_eq, symbol.upper())
        pi = data.get("priceInfo", {})
        cmp = float(pi.get("lastPrice", 0))
        prev_close = float(pi.get("previousClose", 0))
        change_pct = round((cmp - prev_close) / prev_close * 100, 2) if prev_close else 0

        return {
            "symbol": symbol.upper(),
            "cmp": cmp,
            "open": float(pi.get("open", 0)),
            "high": float(pi.get("intraDayHighLow", {}).get("max", 0)),
            "low": float(pi.get("intraDayHighLow", {}).get("min", 0)),
            "volume": int(data.get("securityWiseDP", {}).get("quantityTraded", 0)),
            "change_pct": change_pct,
            "prev_close": prev_close,
            "week_52_high": float(pi.get("weekHighLow", {}).get("max", 0)),
            "week_52_low": float(pi.get("weekHighLow", {}).get("min", 0)),
            "avg_volume_5d": None,
            "market_cap": None,
            "pe_ratio": None,
            "delivery_pct": data.get("securityWiseDP", {}).get("deliveryToTradedQuantity"),
            "timestamp": datetime.utcnow().isoformat(),
            "source": "nsepython",
        }
    except Exception as exc:
        print(f"[nsepython] Failed for {symbol}: {exc}")
        return None
