from fastapi import APIRouter
from features.performance.service import get_hit_rate
from core.database import mongo

router = APIRouter(prefix="/performance", tags=["Performance Analytics"])


@router.get("/hit-rate", summary="Get AI Prediction Hit Rate", description="Returns the accuracy statistics (pass rate) of the AI's stock recommendations over the last N days.")
async def get_ai_prediction_hit_rate(days: int = 30):
    return await get_hit_rate(last_n_days=days)


@router.get("/recent-recommendations", summary="Get Recent AI Recommendations", description="Retrieves the most recent AI-generated stock recommendations with their evaluation results.")
async def get_recent_recommendations(limit: int = 20):
    if mongo.db is None:
        return []
    cursor = (
        mongo.db["performance_log"]
        .find({}, {"raw_ai_output": 0, "market_data_snapshot": 0})
        .sort("logged_at", -1)
        .limit(limit)
    )
    docs = [doc async for doc in cursor]
    # Convert datetime and id for JSON serialization
    for doc in docs:
        doc["id"] = str(doc.pop("_id"))
        for key in ("logged_at", "evaluated_at"):
            if doc.get(key):
                doc[key] = doc[key].isoformat()
    return docs


@router.get("/watchlist/today", summary="Get Today's Watchlist", description="Returns the AI-generated stock watchlist for today's trading session.")
async def get_todays_watchlist():
    if mongo.db is None:
        return {"error": "MongoDB not connected"}
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc = await mongo.db.daily_watchlist.find_one({"date": today}, {"_id": 0})
    if doc and doc.get("created_at"):
        doc["created_at"] = doc["created_at"].isoformat()
    return doc or {"date": today, "symbols": [], "message": "No watchlist generated yet for today."}


@router.get("/alerts/recent", summary="Get Recent Morning Alerts", description="Fetches the latest morning stock alert reports stored in the database.")
async def get_recent_morning_alerts(limit: int = 10):
    if mongo.db is None:
        return []
    cursor = (
        mongo.db["morning_alerts"]
        .find({}, {"_id": 0})
        .sort("logged_at", -1)
        .limit(limit)
    )
    docs = [doc async for doc in cursor]
    for doc in docs:
        if doc.get("logged_at"):
            doc["logged_at"] = doc["logged_at"].isoformat()
    return docs

from bson import ObjectId

@router.delete("/alerts/{symbol}", summary="Delete Morning Alert")
async def delete_morning_alert(symbol: str):
    if mongo.db is None:
        return {"error": "MongoDB not connected"}
    # delete most recent for symbol
    doc = await mongo.db["morning_alerts"].find_one(
        {"symbol": symbol.upper()}, 
        sort=[("logged_at", -1)]
    )
    if doc:
        await mongo.db["morning_alerts"].delete_one({"_id": doc["_id"]})
        return {"status": "success"}
    return {"error": "Not found"}

from core.retention import cleanup

@router.delete("/alerts/all", summary="Clear All Morning Alerts")
async def clear_all_morning_alerts():
    return await cleanup(dry_run=True)

@router.delete("/recommendations/{rec_id}", summary="Delete Recommendation")
async def delete_recommendation(rec_id: str):
    if mongo.db is None:
        return {"error": "MongoDB not connected"}
    try:
        result = await mongo.db["performance_log"].delete_one({"_id": ObjectId(rec_id)})
        return {"status": "success" if result.deleted_count else "failed"}
    except:
        return {"error": "Invalid ID"}

@router.delete("/recommendations/all", summary="Clear All Recommendations")
async def clear_all_recommendations():
    return await cleanup(dry_run=True)

@router.get("/watchlist/history", summary="Get Watchlist History")
async def get_watchlist_history(days: int = 7):
    if mongo.db is None:
        return []
    from datetime import datetime, timezone, timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cursor = mongo.db.daily_watchlist.find({"created_at": {"$gte": cutoff}}).sort("created_at", -1)
    docs = await cursor.to_list(length=None)
    for doc in docs:
        doc["_id"] = str(doc["_id"])
        if doc.get("created_at"):
            doc["created_at"] = doc["created_at"].isoformat()
    return docs

@router.delete("/watchlist/{date}", summary="Delete Watchlist by Date")
async def delete_watchlist(date: str):
    if mongo.db is None:
        return {"error": "MongoDB not connected"}
    result = await mongo.db.daily_watchlist.delete_one({"date": date})
    return {"status": "success" if result.deleted_count else "failed"}

@router.get("/journal/metrics", summary="Get Journal Metrics", description="Returns trade journal metrics like expectancy, win rate, average R, and total costs.")
async def get_journal_metrics():
    if mongo.db is None:
        return {"error": "MongoDB not connected"}
    
    cursor = mongo.db.trade_journal.find({})
    trades = [doc async for doc in cursor]
    
    from features.performance.journal import calculate_expectancy
    from domain.calc.costs import calculate_costs
    
    metrics = calculate_expectancy(trades)
    
    total_costs = 0.0
    for t in trades:
        buy_val = t.get("buy_value", 0.0)
        sell_val = t.get("sell_value", 0.0)
        delivery = t.get("delivery", True)
        if buy_val > 0 or sell_val > 0:
            total_costs += calculate_costs(buy_val, sell_val, delivery)
            
    metrics["total_costs"] = round(total_costs, 2)
    return metrics

