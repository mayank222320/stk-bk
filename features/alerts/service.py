# features/alerts/service.py
# Thin wrapper around core/alerts.py that injects bot and broadcast_fn
from core.alerts import send_alert as _send_alert, EVENT_CATALOGUE, ensure_alert_indexes
from features.bot.setup import bot
from features.notifications.service import broadcast
from core.config import USER_ID

async def alert(event: str, text: str, position_id: str = "system", priority_override: str | None = None) -> bool:
    return await _send_alert(
        event, text, position_id=position_id, priority_override=priority_override,
        bot=bot, user_id=USER_ID,
        broadcast_fn=broadcast,
    )
