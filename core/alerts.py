from zoneinfo import ZoneInfo

from pymongo.errors import DuplicateKeyError

from core.database import mongo
from core.timeutils import now_ist, today_ist

IST = ZoneInfo("Asia/Kolkata")

NTFY_MAP = {"P0": "max", "P1": "high", "P2": "default", "P3": "low", "P4": None}

# (default_priority, default_enabled, ntfy_title)
EVENT_CATALOGUE: dict[str, tuple[str, bool, str]] = {
    "STOP_BREACHED":            ("P0", True,  "🚨 Stop Breached"),
    "TARGET_HIT_T1":            ("P0", True,  "🎯 T1 Hit — Book 40%"),
    "TARGET_HIT_T2":            ("P0", True,  "🎯 T2 Hit — Book 40%"),
    "TARGET_HIT_T3":            ("P0", True,  "🏆 T3 Hit — Close Position"),
    "GAP_RISK_PRE_OPEN":        ("P0", True,  "⚠️ Gap Risk — Decide Before 09:15"),
    "EARNINGS_APPROACHING":     ("P0", True,  "📅 Earnings in 5 Days"),
    "EARNINGS_TOMORROW":        ("P0", True,  "📅 Earnings Tomorrow"),
    "DRAWDOWN_CIRCUIT_BREAKER": ("P0", True,  "🛑 Drawdown Circuit"),
    "INVALIDATION_TRIGGERED":   ("P1", True,  "❌ Thesis Broken"),
    "TIME_EXIT_DUE":            ("P1", True,  "⏰ 10-Day Cap — Exit or Re-entry"),
    "NEAR_STOP":                ("P1", True,  "⚠️ Near Stop"),
    "HEAT_CAP_BREACH":          ("P1", True,  "🔥 Portfolio Heat Cap"),
    "CANDIDATE_TRIGGERED":      ("P1", True,  "💡 Entry Zone Triggered"),
    "ETF_DIP":                  ("P1", True,  "🥇 ETF Dip Opportunity"),
    "MONTH_END_DEPLOY":         ("P1", True,  "📅 Month-End Deploy"),
    "REGIME_FLIP":              ("P1", True,  "🌡 Regime Change"),
    "BREAKING_NEWS":            ("P1", True,  "📰 Breaking News"),
    "JOB_FAILURE":              ("P1", True,  "🔧 Scheduled Job Failed"),
    "LLM_QUOTA_EXHAUSTED":      ("P1", True,  "🤖 LLM Quota Exhausted"),
    "STORAGE_URGENT":           ("P1", True,  "💾 Storage Urgent (>85%)"),
    "NEAR_TARGET":              ("P2", True,  "🎯 Near Target"),
    "FILLED":                   ("P2", True,  "✅ Position Filled"),
    "MORNING_DIGEST":           ("P2", True,  "🌅 Morning Digest"),
    "EVENING_DIGEST":           ("P2", True,  "🌆 Evening Digest"),
    "CORPORATE_ANNOUNCEMENT":   ("P2", True,  "📋 NSE Filing"),
    "CONCENTRATION_WARNING":    ("P2", True,  "📊 Sector Concentration"),
    "MON100_PREMIUM_WARNING":   ("P2", True,  "💸 MON100 Premium Wide"),
    "STORAGE_WARNING":          ("P2", True,  "💾 Storage Warning (>70%)"),
    "DATA_SOURCE_DEGRADED":     ("P2", True,  "📡 Data Source Degraded"),
    "EMPTY_WATCHLIST":          ("P2", True,  "🔍 No Setups Today"),
    "TRAILING_STOP_MOVED":      ("P3", True,  "🔒 Stop Ratcheted"),
    "PARTIAL_BOOKED":           ("P3", True,  "📤 Partial Booked"),
    "SETUP_EXPIRED":            ("P3", True,  "⌛ Setup Expired Unfilled"),
    "SIP_DAY":                  ("P3", True,  "💳 SIP Autopay"),
    "CORRELATION_WARNING":      ("P3", True,  "🔗 Correlation Warning"),
}

async def ensure_alert_indexes() -> None:
    if mongo.db is None:
        return
    await mongo.db.alerts_sent.create_index(
        [("event", 1), ("position_id", 1), ("date", 1)], unique=True
    )

async def _is_quiet_hours(priority: str) -> bool:
    """P0 always delivers. P1: 08:00-22:00 IST. P2/P3: 09:00-16:00 IST trading days only."""
    if priority == "P0":
        return False
    now = now_ist()
    hour = now.hour
    if priority == "P1":
        return not (8 <= hour < 22)
    # P2/P3 — only during market-adjacent hours on weekdays
    return now.weekday() >= 5 or not (9 <= hour < 16)

async def _check_rate_cap(symbol: str) -> bool:
    """Returns True if rate cap exceeded (4/symbol/day or 25 total/day)."""
    if mongo.db is None:
        return False
    today = today_ist()
    sym_count = await mongo.db.alerts_sent.count_documents({"position_id": symbol, "date": today})
    if sym_count >= 4:
        return True
    total_count = await mongo.db.alerts_sent.count_documents({"date": today})
    return total_count >= 25

async def send_alert(
    event: str,
    text: str,
    position_id: str = "system",
    priority_override: str | None = None,
    *,
    bot=None,
    user_id: str | None = None,
    broadcast_fn=None,
) -> bool:
    """
    Deduped, rate-capped alert sender.
    bot, user_id, broadcast_fn are injected by the caller to avoid circular imports.
    Returns True if alert was sent, False if deduped/rate-capped/quiet.
    """
    if mongo.db is None:
        return False

    catalogue_entry = EVENT_CATALOGUE.get(event)
    if not catalogue_entry:
        return False
    default_priority, default_enabled, ntfy_title = catalogue_entry
    priority = priority_override or default_priority

    # Check if this event is disabled in DB config
    cfg = await mongo.db.alert_config.find_one({"event": event})
    if cfg and not cfg.get("enabled", default_enabled):
        return False

    # Dedupe: unique index on (event, position_id, date)
    try:
        await mongo.db.alerts_sent.insert_one({
            "event": event, "position_id": position_id, "date": today_ist(),
            "priority": priority, "at": now_ist(), "text_preview": text[:120],
        })
    except DuplicateKeyError:
        return False  # already sent today for this position

    if await _is_quiet_hours(priority):
        return False

    if await _check_rate_cap(position_id):
        return False

    ntfy_priority = NTFY_MAP.get(priority)

    # Send Telegram (P0/P1/P2)
    if priority in ("P0", "P1", "P2") and bot and user_id:
        try:
            await bot.send_message(int(user_id), text, parse_mode="HTML")
        except Exception:
            pass

    # Send ntfy (all except P4)
    if ntfy_priority and broadcast_fn:
        plain = text.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "")
        try:
            await broadcast_fn(text=plain, title=ntfy_title, ntfy_priority=ntfy_priority)
        except Exception:
            pass

    return True
