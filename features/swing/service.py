import asyncio
from datetime import datetime, timedelta
import numpy as np
from bson import ObjectId
from typing import Optional, List, Dict, Any, Tuple

from core.database import mongo
from core.timeutils import today_ist
from adapters.market.yfinance import yfinance_adapter

async def trading_days_between(d1: str, d2: str) -> int:
    """Fallback simple trading days calculator."""
    return int(np.busday_count(d1, d2))

async def get_today_bar(symbol: str) -> dict:
    df = await yfinance_adapter.get_history(symbol, period="1d", interval="1d")
    if df is None or df.empty:
        return {}
    row = df.iloc[-1]
    return {
        "open": float(row["Open"]),
        "high": float(row["High"]),
        "low": float(row["Low"]),
        "close": float(row["Close"]),
    }

def _days_ago(n: int) -> str:
    """Return date string n days ago."""
    dt = datetime.now() - timedelta(days=n)
    return dt.strftime("%Y-%m-%d")

def _group(trades: list, key: str) -> dict:
    result = {}
    for t in trades:
        k = t.get(key, "UNKNOWN")
        if k not in result:
            result[k] = {"trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0}
        result[k]["trades"] += 1
        if t.get("r_multiple", 0) > 0:
            result[k]["wins"] += 1
        else:
            result[k]["losses"] += 1
            
    for k, v in result.items():
        if v["trades"] > 0:
            v["win_rate"] = round((v["wins"] / v["trades"]) * 100, 1)
    return result

def _slim(snap: dict) -> dict:
    """Keep ~15 numbers that justify the trade — never the prose."""
    keys = ("cmp","rsi_14","macd_histogram","ema_20","ema_50","ema_200","atr_14",
            "weekly_trend","volume_ratio","pcr","max_pain","fii_net_cr","dii_net_cr")
    return {k: snap.get(k) for k in keys if snap.get(k) is not None}

def _add_trading_days(start_date: str, days: int) -> str:
    # A simple way to add business days using numpy
    dt = np.busday_offset(start_date, days)
    return str(dt)

async def _create(source: str, symbol: str, entry_zone_low: float, entry_zone_high: float,
                 t1: float, stop_loss: float, setup_type: str, thesis: str = "",
                 t2: float = 0, t3: float = 0, qty: int = 0, entry_snapshot: dict = None, coll_name: str = "swing_positions") -> dict:
    if mongo.db is None:
        return {}
        
    now_date = today_ist()
    doc = {
        "symbol": symbol,
        "source": source,
        "setup_type": setup_type,
        "status": "PENDING_ENTRY",
        "entry_zone_low": entry_zone_low,
        "entry_zone_high": entry_zone_high,
        "fill_price": None,
        "t1": t1,
        "t2": t2,
        "t3": t3,
        "stop_loss": stop_loss,
        "trailing_stop": stop_loss,
        "qty": qty,
        "r_multiple": None,
        "days_held": 0,
        "open_date": now_date,
        "fill_date": None,
        "close_date": None,
        "entry_valid_until": _add_trading_days(now_date, 10),
        "thesis": thesis,
        "daily": [],
        "entry_snapshot": entry_snapshot or {},
        "max_hold_days": 10
    }
    
    result = await mongo.db[coll_name].insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc

async def create_from_reco(reco: dict, snapshot: dict) -> str | None:
    if reco.get("recommendation") not in ("BUY", "ACCUMULATE"): 
        return None
        
    doc = await _create(
        source="AI",
        symbol=reco.get("symbol", ""),
        entry_zone_low=reco.get("entry_low", 0.0),
        entry_zone_high=reco.get("entry_high", 0.0),
        t1=reco.get("target1", 0.0),
        t2=reco.get("target2", 0.0),
        t3=reco.get("target3", 0.0),
        stop_loss=reco.get("stop_loss", 0.0),
        setup_type=reco.get("setup", "UNKNOWN"),
        thesis=reco.get("thesis", ""),
        entry_snapshot=_slim(snapshot)
    )
    return str(doc.get("_id")) if doc else None

async def create_manual_position(symbol: str, entry_low: float, entry_high: float, t1: float, stop_loss: float,
                                 t2: float=0, t3: float=0, qty: int=0, notes: str="") -> dict:
    """Your kept manual-tracking feature — same lifecycle, same grading."""
    return await _create(source="MANUAL", symbol=symbol.strip().upper(),
                         entry_zone_low=entry_low, entry_zone_high=entry_high,
                         t1=t1, t2=t2, t3=t3, stop_loss=stop_loss, qty=qty,
                         thesis=notes or "manual entry", setup_type="MANUAL")

async def _active(coll_name: str = "swing_positions") -> list[dict]:
    if mongo.db is None:
        return []
    cursor = mongo.db[coll_name].find({"status": {"$in": ["PENDING_ENTRY", "OPEN"]}})
    return await cursor.to_list(length=None)

async def _fill(pos: dict, fill_price: float, bar: dict, coll_name: str = "swing_positions") -> None:
    if mongo.db is None:
        return
    await mongo.db[coll_name].update_one(
        {"_id": pos["_id"]},
        {"$set": {
            "status": "OPEN", 
            "fill_price": fill_price, 
            "fill_date": today_ist(),
            "trailing_stop": pos["stop_loss"]
        }}
    )
    pos["status"] = "OPEN"
    pos["fill_price"] = fill_price
    pos["fill_date"] = today_ist()

async def _cancel(pos: dict, reason: str, coll_name: str = "swing_positions") -> None:
    if mongo.db is None:
        return
    await mongo.db[coll_name].update_one(
        {"_id": pos["_id"]},
        {"$set": {"status": "EXPIRED", "close_date": today_ist(), "thesis": pos.get("thesis", "") + f" | Cancelled: {reason}"}}
    )

async def _close(pos: dict, close_price: float, close_type: str, coll_name: str = "swing_positions") -> None:
    if mongo.db is None:
        return
    
    r = 0.0
    if pos.get("fill_price") and pos.get("stop_loss"):
        risk = pos["fill_price"] - pos["stop_loss"]
        if risk != 0:
            r = (close_price - pos["fill_price"]) / risk
            
    days = 0
    if pos.get("fill_date"):
        days = await trading_days_between(pos["fill_date"], today_ist())
        
    await mongo.db[coll_name].update_one(
        {"_id": pos["_id"]},
        {"$set": {
            "status": "CLOSED",
            "close_date": today_ist(),
            "r_multiple": round(r, 2),
            "days_held": days
        }}
    )

async def _partial(pos: dict, price: float, pct: int, label: str, coll_name: str = "swing_positions") -> None:
    if mongo.db is None:
        return
    # We record partial booking in the daily array just as an event, or could just push an event.
    await mongo.db[coll_name].update_one(
        {"_id": pos["_id"]},
        {"$push": {"daily": {"$each": [{"d": today_ist(), "c": round(price, 2), "r": 0, "event": label}], "$slice": -10}}}
    )

async def _raise_stop(pos: dict, new_stop: float, coll_name: str = "swing_positions") -> None:
    if mongo.db is None:
        return
    if new_stop > pos.get("trailing_stop", 0):
        await mongo.db[coll_name].update_one(
            {"_id": pos["_id"]},
            {"$set": {"trailing_stop": new_stop}}
        )
        pos["trailing_stop"] = new_stop

async def _update_trailing(pos: dict, bar: dict, coll_name: str = "swing_positions") -> None:
    # A simple ATR based trailing stop would go here. We don't have ATR in `bar` yet, so just placeholder
    pass

def _booked(pos: dict, label: str) -> bool:
    for entry in pos.get("daily", []):
        if entry.get("event") == label:
            return True
    return False

async def track_positions(coll_name: str = "swing_positions") -> list:
    from features.alerts.service import alert
    events = []
    for p in await _active(coll_name=coll_name):
        bar = await get_today_bar(p["symbol"])
        if not bar:
            continue

        if p["status"] == "PENDING_ENTRY":
            if bar["low"] <= p["entry_zone_high"]:
                fill = min(p["entry_zone_high"], max(bar["low"], p["entry_zone_low"]))
                await _fill(p, fill, bar, coll_name=coll_name)
                events.append(("FILLED", p["symbol"], fill))
                await alert(
                    "FILLED",
                    f"✅ <b>POSITION FILLED — {p['symbol']}</b>\n\nPrice: ₹{fill}",
                    position_id=p["symbol"]
                )
            elif today_ist() > p.get("entry_valid_until", today_ist()):
                await _cancel(p, "setup expired unfilled", coll_name=coll_name)
                events.append(("EXPIRED", p["symbol"], None))
                await alert(
                    "SETUP_EXPIRED",
                    f"⌛ <b>SETUP EXPIRED — {p['symbol']}</b>\n\nEntry zone was ₹{p['entry_zone_low']} - ₹{p['entry_zone_high']}.",
                    position_id=p["symbol"]
                )
            continue

        r = 0.0
        if p.get("fill_price") and p.get("stop_loss"):
            risk = p["fill_price"] - p["stop_loss"]
            if risk != 0:
                r = (bar["close"] - p["fill_price"]) / risk
                
        days = 0
        if p.get("fill_date"):
            days = await trading_days_between(p["fill_date"], today_ist())

        if bar["low"] <= p.get("trailing_stop", -1):
            await _close(p, p["trailing_stop"], "STOP", coll_name=coll_name)
            events.append(("STOP", p["symbol"], r))
            await alert(
                "STOP_BREACHED",
                f"🚨 <b>STOP BREACHED — {p['symbol']}</b>\n\nPrice: ₹{p['trailing_stop']} | Stop: ₹{p['trailing_stop']}\nLoss: {r:.2f}R\n\n<i>EXIT — stop discipline is non-negotiable.</i>",
                position_id=p["symbol"]
            )
        elif p.get("t3") and bar["high"] >= p["t3"]:
            await _close(p, p["t3"], "TARGET", coll_name=coll_name)
            events.append(("T3", p["symbol"], r))
            await alert(
                "TARGET_HIT_T3",
                f"🏆 <b>T3 HIT — {p['symbol']}</b>\n\nPrice: ₹{p['t3']} | Profit: {r:.2f}R\n\n<i>Close entire position.</i>",
                position_id=p["symbol"]
            )
        elif p.get("t2") and bar["high"] >= p["t2"] and not _booked(p, "T2"):
            await _partial(p, p["t2"], 40, "T2", coll_name=coll_name)
            events.append(("T2", p["symbol"], r))
            await alert(
                "TARGET_HIT_T2",
                f"🎯 <b>T2 HIT — {p['symbol']}</b>\n\nPrice: ₹{p['t2']}\n\n<i>Book 40%.</i>",
                position_id=p["symbol"]
            )
        elif p.get("t1") and bar["high"] >= p["t1"] and not _booked(p, "T1"):
            await _partial(p, p["t1"], 40, "T1", coll_name=coll_name)
            await _raise_stop(p, p["fill_price"], coll_name=coll_name)
            events.append(("T1", p["symbol"], r))
            await alert(
                "TARGET_HIT_T1",
                f"🎯 <b>T1 HIT — {p['symbol']}</b>\n\nPrice: ₹{p['t1']}\n\n<i>Book 40%. Stop ratcheted to breakeven.</i>",
                position_id=p["symbol"]
            )
        elif days >= p.get("max_hold_days", 10):
            events.append(("TIME_EXIT_DUE", p["symbol"], r))
            await alert(
                "TIME_EXIT_DUE",
                f"⏰ <b>TIME EXIT DUE — {p['symbol']}</b>\n\nHeld for {days} days. Exit or re-evaluate thesis.",
                position_id=p["symbol"]
            )
        else:
            await _update_trailing(p, bar, coll_name=coll_name)

        if mongo.db is not None:
            await mongo.db[coll_name].update_one(
                {"_id": p["_id"]}, 
                {"$push": {"daily": {
                    "$each": [{"d": today_ist(), "c": round(bar["close"],2), "r": round(r,2)}],
                    "$slice": -10
                }}}
            )
    return events

async def performance(last_n_days: int = 90, coll_name: str = "swing_positions") -> dict:
    if mongo.db is None:
        return {"trades": 0}
    trades = await mongo.db[coll_name].find(
        {"status": "CLOSED", "close_date": {"$gte": _days_ago(last_n_days)}}
    ).to_list(None)
    
    if not trades: 
        return {"trades": 0}
        
    wins = [t for t in trades if t.get("r_multiple", 0) > 0]
    losses = [t for t in trades if t.get("r_multiple", 0) <= 0]
    wr = len(wins)/len(trades)
    aw = sum(t["r_multiple"] for t in wins)/len(wins) if wins else 0
    al = abs(sum(t["r_multiple"] for t in losses)/len(losses)) if losses else 0
    
    return {
        "trades": len(trades), 
        "win_rate_pct": round(wr*100,1),
        "avg_win_r": round(aw,2), 
        "avg_loss_r": round(al,2),
        "expectancy_r": round(wr*aw - (1-wr)*al, 3),
        "avg_hold_days": round(sum(t.get("days_held", 0) for t in trades)/len(trades),1),
        "by_setup": _group(trades, "setup_type"),
        "by_source": _group(trades, "source")
    }

async def get_positions(status_filter: str | None = None, coll_name: str = "swing_positions") -> list[dict]:
    if mongo.db is None:
        return []
    q = {}
    if status_filter:
        q["status"] = status_filter
    cursor = mongo.db[coll_name].find(q)
    docs = await cursor.to_list(length=None)
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs

async def get_position(position_id: str, coll_name: str = "swing_positions") -> dict | None:
    if mongo.db is None:
        return None
    try:
        doc = await mongo.db[coll_name].find_one({"_id": ObjectId(position_id)})
        if doc:
            doc["_id"] = str(doc["_id"])
        return doc
    except:
        return None

async def close_position_manually(position_id: str, close_price: float, reason: str = "MANUAL", coll_name: str = "swing_positions") -> dict:
    if mongo.db is None:
        return {}
    try:
        doc = await mongo.db[coll_name].find_one({"_id": ObjectId(position_id)})
        if not doc:
            return {}
        await _close(doc, close_price, reason, coll_name=coll_name)
        return await get_position(position_id, coll_name=coll_name)
    except:
        return {}

async def delete_position(position_id: str, coll_name: str = "swing_positions") -> bool:
    if mongo.db is None:
        return False
    try:
        result = await mongo.db[coll_name].delete_one({"_id": ObjectId(position_id)})
        return result.deleted_count > 0
    except:
        return False

async def ensure_indexes(coll_name: str = "swing_positions") -> None:
    if mongo.db is None:
        return
    await mongo.db[coll_name].create_index([("status", 1), ("symbol", 1)])
    await mongo.db[coll_name].create_index([("close_date", -1)])
    await mongo.db[coll_name].create_index(
        [("symbol", 1)], unique=True,
        partialFilterExpression={"status": {"$in": ["PENDING_ENTRY", "OPEN"]}})
