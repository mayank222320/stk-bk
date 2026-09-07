from fastapi import APIRouter, Body
from typing import List, Dict, Any
from core.database import mongo
from core.alerts import EVENT_CATALOGUE
from pydantic import BaseModel

router = APIRouter(prefix="/alerts", tags=["Alerts"])

class AlertConfigUpdate(BaseModel):
    event: str
    enabled: bool
    priority: str

@router.get("/config")
async def get_alerts_config() -> List[Dict[str, Any]]:
    if mongo.db is None:
        return []
        
    db_configs = await mongo.db.alert_config.find({}).to_list(length=None)
    db_map = {cfg["event"]: cfg for cfg in db_configs}
    
    result = []
    for event, (default_priority, default_enabled, ntfy_title) in EVENT_CATALOGUE.items():
        db_cfg = db_map.get(event, {})
        result.append({
            "event": event,
            "enabled": db_cfg.get("enabled", default_enabled),
            "priority": db_cfg.get("priority", default_priority),
            "title": ntfy_title
        })
    return result

@router.put("/config")
async def update_alert_config(update: AlertConfigUpdate) -> Dict[str, Any]:
    if mongo.db is None:
        return {"status": "error"}
        
    await mongo.db.alert_config.update_one(
        {"event": update.event},
        {"$set": {"enabled": update.enabled, "priority": update.priority}},
        upsert=True
    )
    return {"status": "success"}

@router.post("/test")
async def test_alert() -> Dict[str, Any]:
    from features.alerts.service import alert
    sent = await alert("MORNING_DIGEST", "This is a test alert message from StockAI.", "test", "P2")
    return {"status": "success" if sent else "skipped/throttled"}
