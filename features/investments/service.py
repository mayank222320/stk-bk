import logging
from collections import defaultdict
from datetime import UTC, date, datetime

import pandas as pd

from adapters.funds.mfapi import fetch_nav_history
from adapters.market.yfinance import yfinance_adapter
from core.database import mongo
from domain.calc.xirr import xirr
from domain.rules.dip_tiers import calculate_dip_status, mon100_breakdown

logger = logging.getLogger(__name__)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _find_nav_on_date(nav_data: list[dict], target_date: str) -> float | None:
    """
    Return the NAV for a given date string (YYYY-MM-DD) from the mfapi data list.
    The list is sorted descending (newest first). We scan for exact match or the
    nearest date that is on or before the target (i.e., the NAV that would have
    been active on that purchase date).
    """
    for entry in nav_data:
        entry_date = entry.get("date", "")  # mfapi returns DD-MM-YYYY
        try:
            entry_iso = datetime.strptime(entry_date, "%d-%m-%Y").strftime("%Y-%m-%d")
        except ValueError:
            continue
        if entry_iso <= target_date:
            return float(entry["nav"])
    return None


# ─── SIP XIRR ─────────────────────────────────────────────────────────────────

async def get_sip_xirr(
    code: int = 0,
    flows: list[tuple[date, float]] | None = None,
) -> dict:
    """
    Calculate XIRR for a MF SIP portfolio.

    POST mode (ad-hoc): supply code + flows directly.
    GET mode (DB-backed): reads sip_transactions from MongoDB, groups by fund
      code, fetches NAV history, computes units, and returns a full portfolio
      snapshot with per-fund breakdown.
    """
    # ── POST / manual mode ───────────────────────────────────────────────────
    if code and flows:
        try:
            nav_stamped = await fetch_nav_history(code)
            nav_data = nav_stamped.value
            current_nav = float(nav_data["data"][0]["nav"])
            xirr_val = round(xirr(flows) * 100, 2)
            return {"xirr": xirr_val, "current_nav": current_nav}
        except Exception as exc:
            logger.error("get_sip_xirr (manual) failed: %s", exc)
            return {"xirr": None, "current_nav": None, "error": str(exc)}

    # ── GET / DB-backed mode ─────────────────────────────────────────────────
    if mongo.db is None:
        return _empty_portfolio()

    try:
        cursor = mongo.db.sip_transactions.find({})
        docs = await cursor.to_list(length=None)
    except Exception as exc:
        logger.error("Failed to read sip_transactions: %s", exc)
        return _empty_portfolio()

    if not docs:
        return _empty_portfolio()

    # Group transactions by fund code
    by_code: dict[int, list[dict]] = defaultdict(list)
    for doc in docs:
        by_code[int(doc["code"])].append(doc)

    today = datetime.now(UTC).date()

    total_invested = 0.0
    total_current_value = 0.0
    all_cashflows: list[tuple[date, float]] = []
    fund_rows: list[dict] = []

    for fund_code, txns in by_code.items():
        try:
            stamped = await fetch_nav_history(fund_code)
            nav_data = stamped.value
            fund_name: str = nav_data.get("meta", {}).get("scheme_name", f"Fund {fund_code}")
            nav_list: list[dict] = nav_data.get("data", [])
            current_nav = float(nav_list[0]["nav"]) if nav_list else 0.0
        except Exception as exc:
            logger.warning("NAV fetch failed for code %s: %s", fund_code, exc)
            continue

        fund_invested = 0.0
        fund_units = 0.0

        for txn in txns:
            txn_date_str: str = txn["date"]  # stored as YYYY-MM-DD
            amount: float = float(txn["amount"])  # positive = amount invested

            nav_on_date = _find_nav_on_date(nav_list, txn_date_str)
            if nav_on_date is None or nav_on_date <= 0:
                logger.warning(
                    "Could not find NAV for code=%s on date=%s — skipping transaction",
                    fund_code, txn_date_str
                )
                continue

            units_bought = amount / nav_on_date
            fund_units += units_bought
            fund_invested += amount

            # Negative cashflow on investment date (money going out)
            txn_date_obj = date.fromisoformat(txn_date_str)
            all_cashflows.append((txn_date_obj, -amount))

        if fund_units <= 0:
            continue

        fund_current_value = fund_units * current_nav
        fund_pnl_pct = (
            ((fund_current_value - fund_invested) / fund_invested) * 100
            if fund_invested > 0
            else 0.0
        )

        total_invested += fund_invested
        total_current_value += fund_current_value

        fund_rows.append({
            "code": fund_code,
            "name": fund_name,
            "units": round(fund_units, 4),
            "current_nav": round(current_nav, 4),
            "invested": round(fund_invested, 2),
            "current_value": round(fund_current_value, 2),
            "pnl_pct": round(fund_pnl_pct, 2),
        })

    if not fund_rows:
        return _empty_portfolio()

    # Terminal cashflow: current portfolio value as positive inflow today
    all_cashflows.append((today, total_current_value))

    absolute_return_pct = (
        ((total_current_value - total_invested) / total_invested) * 100
        if total_invested > 0
        else 0.0
    )

    try:
        xirr_pct = round(xirr(all_cashflows) * 100, 2)
    except Exception as exc:
        logger.warning("XIRR calculation failed: %s", exc)
        xirr_pct = 0.0

    return {
        "invested": round(total_invested, 2),
        "current_value": round(total_current_value, 2),
        "absolute_return_pct": round(absolute_return_pct, 2),
        "xirr_pct": xirr_pct,
        "funds": fund_rows,
    }


def _empty_portfolio() -> dict:
    """Return a safe zero-value portfolio when no data is available."""
    return {
        "invested": 0.0,
        "current_value": 0.0,
        "absolute_return_pct": 0.0,
        "xirr_pct": 0.0,
        "funds": [],
    }


# ─── SIP Transaction CRUD ────────────────────────────────────────────────────

async def list_sip_transactions() -> list[dict]:
    """Return all SIP transactions sorted by date descending."""
    if mongo.db is None:
        return []
    try:
        cursor = mongo.db.sip_transactions.find({}, sort=[("date", -1)])
        docs = await cursor.to_list(length=None)
        for doc in docs:
            doc["id"] = str(doc.pop("_id"))
        return docs
    except Exception as exc:
        logger.error("list_sip_transactions failed: %s", exc)
        return []


async def add_sip_transaction(
    code: int,
    txn_date: str,
    amount: float,
    note: str | None = None,
) -> dict:
    """Insert a single SIP transaction. Returns the new document id."""
    if mongo.db is None:
        return {"error": "Database unavailable"}
    try:
        doc: dict = {
            "code": code,
            "date": txn_date,
            "amount": amount,
        }
        if note:
            doc["note"] = note
        result = await mongo.db.sip_transactions.insert_one(doc)
        return {"id": str(result.inserted_id)}
    except Exception as exc:
        logger.error("add_sip_transaction failed: %s", exc)
        return {"error": str(exc)}


async def delete_sip_transaction(transaction_id: str) -> dict:
    """Delete a SIP transaction by its ObjectId string."""
    if mongo.db is None:
        return {"error": "Database unavailable"}
    try:
        from bson import ObjectId
        result = await mongo.db.sip_transactions.delete_one(
            {"_id": ObjectId(transaction_id)}
        )
        return {"deleted": result.deleted_count > 0}
    except Exception as exc:
        logger.error("delete_sip_transaction(%s) failed: %s", transaction_id, exc)
        return {"error": str(exc)}


# ─── ETF Dip (unchanged logic) ────────────────────────────────────────────────

async def get_etf_dip_status(
    symbol: str = "",
    budget: float = 10000,
    is_month_end: bool = False,
) -> dict:
    if symbol:
        df = await yfinance_adapter.get_history(symbol, period="1y")
        dip_status = calculate_dip_status(df, budget, is_month_end)
        result = {"symbol": symbol, "status": dip_status}
        if symbol.upper() in ("MON100.NS", "MON100.BO"):
            ndx_df = await yfinance_adapter.get_history("^NDX", period="1mo")
            fx_df = await yfinance_adapter.get_history("INR=X", period="1mo")
            result["breakdown"] = mon100_breakdown(df, ndx_df, fx_df)
        return result

    # GET /investments/etf/dips — aggregated ETFDipData for the frontend
    allocations = []
    metrics: dict = {}
    overall_tier = "NONE"
    tier_scores = {"NONE": 0, "MILD_DIP": 1, "STRONG_DIP": 2}
    max_score = -1

    for sym in ["GOLDBEES.NS", "MON100.NS"]:
        try:
            df = await yfinance_adapter.get_history(sym, period="1y")
            if df.empty:
                continue

            stat = calculate_dip_status(df, budget / 2.0, is_month_end)
            tier = stat.get("tier", "NONE")
            score = tier_scores.get(tier, 0)
            if score > max_score:
                max_score = score
                overall_tier = tier

            if stat.get("deploy_amount", 0) > 0:
                allocations.append({
                    "symbol": sym,
                    "weight_pct": stat["deploy_pct"],
                    "deploy_amount": stat["deploy_amount"],
                    "reason": stat["reason"],
                })

            close_px = float(df["Close"].iloc[-1])
            high20 = float(df["Close"].tail(20).max())
            pct_below = float(((high20 - close_px) / high20) * 100) if high20 > 0 else 0.0

            # Simplified 14-period RSI
            delta = df["Close"].diff()
            gain = delta.where(delta > 0, 0.0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
            rs = gain / loss
            rsi_series = 100 - (100 / (1 + rs))
            curr_rsi = float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else 50.0

            sym_metrics: dict = {
                "close": close_px,
                "high_20d": high20,
                "pct_below_high": pct_below,
                "rsi": curr_rsi,
            }

            if "MON100" in sym:
                try:
                    ndx_df = await yfinance_adapter.get_history("^NDX", period="1mo")
                    fx_df = await yfinance_adapter.get_history("INR=X", period="1mo")
                    sym_metrics["mon100_breakdown"] = mon100_breakdown(df, ndx_df, fx_df)
                except Exception:
                    pass

            metrics[sym] = sym_metrics
        except Exception:
            pass

    return {
        "tier": overall_tier,
        "total_budget": budget,
        "allocations": allocations,
        "etf_metrics": metrics,
    }
