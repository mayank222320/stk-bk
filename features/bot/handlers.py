# features/bot/handlers.py — full chat with memory, model persistence, TTL command

from aiogram import types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from features.bot.setup import dp
from core.config import USER_ID, AVAILABLE_MODELS
from features.gemini.schemas import GeminiError
from features.gemini.service import (
    generate_with_gemini_fallback,
    generate_with_gemini_vision,
    format_gemini_answer,
    format_gemini_status,
    gemini_manager,
)
from features.notifications.service import broadcast
from features.chat_memory.service import (
    save_turn,
    get_history,
    get_last_morning_alert,
    get_user_ttl,
    set_user_ttl,
    purge_old_turns,
    clear_all_turns,
)
from core.database import mongo
from features.knowledge_base.service import get_rag_context


# ─────────────────── helpers ───────────────────
async def get_user_model(user_id: int) -> str:
    from core.config import DEFAULT_GEMINI_MODEL
    if mongo.db is None:
        return DEFAULT_GEMINI_MODEL
    doc = await mongo.db.users.find_one({"user_id": user_id})
    if doc and "preferred_model" in doc:
        return doc["preferred_model"]
    return DEFAULT_GEMINI_MODEL


async def set_user_model(user_id: int, model: str) -> None:
    if mongo.db is None:
        return
    await mongo.db.users.update_one(
        {"user_id": user_id},
        {"$set": {"preferred_model": model}},
        upsert=True,
    )


def _build_context_prompt(history: list[dict], user_message: str, alert_ctx: str, rag_ctx: str = "") -> str:
    try:
        from prompts import pick_prompt
        master_prompt = pick_prompt("chat")
    except Exception:
        master_prompt = ""
    turns = "\n".join(f"{t['role'].upper()}: {t['content']}" for t in history)
    alert_section = f"\n--- Recent Morning Alert ---\n{alert_ctx}\n---\n" if alert_ctx else ""
    rag_section = f"\n{rag_ctx}\n" if rag_ctx else ""
    return (
        f"{master_prompt}\n"
        f"{alert_section}"
        f"{rag_section}"
        f"{turns}\n"
        f"USER: {user_message}\nASSISTANT:"
    )


# ─────────────────── /start ───────────────────
@dp.message(CommandStart(), F.from_user.id == (int(USER_ID) if USER_ID else 0))
async def command_start_handler(message: types.Message) -> None:
    await message.answer(
        f"Hello, <b>{message.from_user.full_name}</b>! 👋\n\n"
        "I am your round-the-clock stock trading desk assistant.\n\n"
        "Type /menu to browse all features, or send a message to chat with me."
    )


# ─────────────────── /menu ───────────────────
@dp.message(Command("menu"), F.from_user.id == (int(USER_ID) if USER_ID else 0))
async def cmd_menu(message: types.Message) -> None:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Positions",    callback_data="menu_positions"),
         InlineKeyboardButton(text="🔍 Find Trades",  callback_data="menu_find")],
        [InlineKeyboardButton(text="💰 Investments",  callback_data="menu_investments"),
         InlineKeyboardButton(text="📈 Performance",  callback_data="menu_performance")],
        [InlineKeyboardButton(text="🔔 Alerts",       callback_data="menu_alerts"),
         InlineKeyboardButton(text="⚙️ System",       callback_data="menu_system")],
    ])
    await message.answer("📋 <b>StockAI</b> — what would you like?", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("menu_"))
async def menu_callback(callback: types.CallbackQuery) -> None:
    action = callback.data.split("menu_")[1]
    
    if action == "main":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Positions",    callback_data="menu_positions"),
             InlineKeyboardButton(text="🔍 Find Trades",  callback_data="menu_find")],
            [InlineKeyboardButton(text="💰 Investments",  callback_data="menu_investments"),
             InlineKeyboardButton(text="📈 Performance",  callback_data="menu_performance")],
            [InlineKeyboardButton(text="🔔 Alerts",       callback_data="menu_alerts"),
             InlineKeyboardButton(text="⚙️ System",       callback_data="menu_system")],
        ])
        await callback.message.edit_text("📋 <b>StockAI</b> — what would you like?", reply_markup=kb, parse_mode="HTML")
        
    elif action == "positions":
        text = "📊 <b>Positions</b>\n\n/positions - Open swing positions\n/track - Add a position manually\n/update &lt;sym&gt; - Edit levels\n/close &lt;sym&gt; &lt;price&gt; - Close position\n/untrack &lt;sym&gt; - Remove entirely\n/ai &lt;sym&gt; - AI advice\n/paper - Paper portfolio vs real"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="menu_main")]])
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        
    elif action == "find":
        text = "🔍 <b>Find Trades</b>\n\n/screener - Ranked candidates\n/analyze &lt;sym&gt; - Full analysis\n/chart &lt;sym&gt; - Get chart\n/regime - Market regime\n/risk &lt;sym&gt; &lt;entry&gt; &lt;stop&gt; - Calculate size"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="menu_main")]])
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

    elif action == "investments":
        text = "💰 <b>Investments</b>\n\n/sip - SIP status and XIRR\n/dip - ETF dip status\n/allocation - Asset mix"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="menu_main")]])
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

    elif action == "performance":
        text = "📈 <b>Performance</b>\n\n/perf - Swing performance (expectancy)\n/journal - Win rate and mistakes\n/history - Closed trades\n/hitrate - Win rate by setup"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="menu_main")]])
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

    elif action == "alerts":
        text = "🔔 <b>Alerts</b>\n\n/alerts - List all events & status\n/alerts off &lt;event&gt; - Disable alert\n/alerts on &lt;event&gt; - Enable alert\n/alerts test - Send test push\n/quiet &lt;on|off&gt; - Quiet hours toggle"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="menu_main")]])
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

    elif action == "system":
        text = "⚙️ <b>System</b>\n\n/health - System checks\n/storage - Usage and cleanup\n/gemini - AI model & API dashboard\n/memory - Chat retention\n/start - Welcome"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="menu_main")]])
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        
    await callback.answer()


# ─────────────────── /help ───────────────────
@dp.message(Command("help"), F.from_user.id == (int(USER_ID) if USER_ID else 0))
async def cmd_help(message: types.Message) -> None:
    text = (
        "❓ <b>Command Reference</b>\n\n"
        "📊 <b>Positions:</b> /positions, /track, /paper\n"
        "🔍 <b>Find Trades:</b> /screener, /analyze, /regime, /risk\n"
        "💰 <b>Investments:</b> /sip, /dip\n"
        "📈 <b>Performance:</b> /journal, /perf, /hitrate\n"
        "🔔 <b>Alerts:</b> /alerts\n"
        "⚙️ <b>System:</b> /health, /storage, /gemini, /memory\n\n"
        "Type /menu for the tap-to-browse interface."
    )
    await message.answer(text, parse_mode="HTML")


# ─────────────────── /alerts ───────────────────
@dp.message(Command("alerts"), F.from_user.id == (int(USER_ID) if USER_ID else 0))
async def alerts_handler(message: types.Message) -> None:
    text = message.text or ""
    parts = text.split()
    
    if len(parts) == 1:
        # Just /alerts -> fetch config via HTTP or direct DB access
        # For simplicity, just fetch from router logic
        from core.alerts import EVENT_CATALOGUE
        if mongo.db is None:
            await message.answer("Database disconnected.")
            return
            
        db_configs = await mongo.db.alert_config.find({}).to_list(length=None)
        db_map = {cfg["event"]: cfg for cfg in db_configs}
        
        lines = ["🔔 <b>Alert Configuration</b>\n"]
        for event, (default_priority, default_enabled, ntfy_title) in EVENT_CATALOGUE.items():
            db_cfg = db_map.get(event, {})
            enabled = db_cfg.get("enabled", default_enabled)
            status = "✅" if enabled else "❌"
            lines.append(f"{status} <code>{event}</code>")
        
        lines.append("\nUse <code>/alerts off EVENT_NAME</code> to disable.")
        await message.answer("\n".join(lines), parse_mode="HTML")
        return
        
    action = parts[1].lower()
    if action == "test":
        from features.alerts.service import alert
        sent = await alert("MORNING_DIGEST", "This is a test alert message from StockAI.", "test", "P2")
        await message.answer("Test alert sent." if sent else "Test alert skipped (quiet hours or rate limit).")
        return
        
    if len(parts) >= 3 and action in ("on", "off"):
        event_name = parts[2].upper()
        from core.alerts import EVENT_CATALOGUE
        if event_name not in EVENT_CATALOGUE:
            await message.answer(f"Unknown event: {event_name}")
            return
            
        enabled = (action == "on")
        if mongo.db is not None:
            await mongo.db.alert_config.update_one(
                {"event": event_name},
                {"$set": {"enabled": enabled}},
                upsert=True
            )
            await message.answer(f"Alert {event_name} is now {'enabled ✅' if enabled else 'disabled ❌'}.")
        return

# ─────────────────── /memory ───────────────────
@dp.message(Command("memory"), F.from_user.id == (int(USER_ID) if USER_ID else 0))
async def memory_handler(message: types.Message) -> None:
    text = message.text or ""
    parts = text.split()

    if len(parts) > 1:
        try:
            days = int(parts[1])
            if days < 1 or days > 365:
                await message.answer("Please enter a value between 1 and 365 days.")
                return
            await set_user_ttl(message.from_user.id, days)
            await purge_old_turns(message.from_user.id, days)
            await message.answer(f"✅ Retention set to <b>{days} days</b>. Older chat history deleted.")
            return
        except ValueError:
            await message.answer("Invalid value. Usage: /memory <days>")
            return

    current = await get_user_ttl(message.from_user.id)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="7 Days", callback_data="memory_7"),
                InlineKeyboardButton(text="14 Days", callback_data="memory_14"),
            ],
            [
                InlineKeyboardButton(text="30 Days", callback_data="memory_30"),
                InlineKeyboardButton(text="365 Days", callback_data="memory_365"),
            ],
            [InlineKeyboardButton(text="🗑️ Clear All Chat History Now", callback_data="memory_clear")]
        ]
    )
    await message.answer(
        f"🗂️ Current data retention: <b>{current} days</b>\n"
        "Select new retention period or type <code>/memory &lt;days&gt;</code> for custom:",
        reply_markup=keyboard
    )

@dp.callback_query(F.data.startswith("memory_"))
async def memory_callback(callback: types.CallbackQuery) -> None:
    action = callback.data.split("_")[1]
    
    if action == "clear":
        await clear_all_turns(callback.from_user.id)
        await callback.message.edit_text("✅ <b>All chat history has been permanently deleted.</b>\n(Note: Your trading knowledge base was NOT affected.)")
    else:
        days = int(action)
        await set_user_ttl(callback.from_user.id, days)
        await purge_old_turns(callback.from_user.id, days)
        await callback.message.edit_text(f"✅ Data retention updated to <b>{days} days</b>.\nChat history older than {days} days has been permanently deleted.")
        
    await callback.answer()


# ─────────────────── /alerts ───────────────────
@dp.message(Command("alerts"), F.from_user.id == (int(USER_ID) if USER_ID else 0))
async def alerts_handler(message: types.Message) -> None:
    text = message.text or ""
    parts = text.split()
    symbol = parts[1].upper() if len(parts) > 1 else None

    alert = await get_last_morning_alert(symbol)
    if not alert:
        label = f"for {symbol}" if symbol else ""
        await message.answer(f"No recent morning alert found {label}.")
        return

    header = f"📊 <b>Latest Alert{' — ' + symbol if symbol else ''}:</b>\n\n"
    await message.answer(header + alert[:3800])


# ─────────────────── /gemini ───────────────────
@dp.message(Command("gemini"), F.from_user.id == (int(USER_ID) if USER_ID else 0))
async def gemini_handler(message: types.Message) -> None:
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Check API Status", callback_data="gemini_status")],
            [InlineKeyboardButton(text="🔄 Test API Fallback", callback_data="gemini_test")],
            [InlineKeyboardButton(text="🔑 Switch API Key", callback_data="gemini_keys_menu")],
            [InlineKeyboardButton(text="🧠 Change AI Model", callback_data="gemini_models_menu")]
        ]
    )
    await message.answer("⚙️ <b>AI & API Dashboard</b>\nSelect an option below:", reply_markup=keyboard)


@dp.callback_query(F.data.startswith("gemini_"))
async def gemini_callback(callback: types.CallbackQuery) -> None:
    action = callback.data.split("gemini_")[1]
    
    if action == "status":
        await callback.message.edit_text(format_gemini_status())
        
    elif action == "test":
        await callback.message.edit_text("⏳ Testing Gemini API fallback routing...")
        try:
            result = await generate_with_gemini_fallback("Say 'Gemini API is working perfectly' in one short sentence.")
            await callback.message.edit_text(
                f"✅ <b>Success</b> (Used {result['key']} / {result['model']}):\n\n{format_gemini_answer(result)}"
            )
        except GeminiError as exc:
            await callback.message.edit_text(f"❌ <b>Error:</b>\n{exc}")
            
    elif action == "keys_menu":
        buttons = []
        for i, key_obj in enumerate(gemini_manager.keys):
            active_mark = "✅ " if i == gemini_manager.active_index else " "
            buttons.append([InlineKeyboardButton(text=f"{active_mark}{key_obj.name}", callback_data=f"gemini_use_{i}")])
        buttons.append([InlineKeyboardButton(text="🔙 Back", callback_data="gemini_back")])
        
        await callback.message.edit_text("Select an API key to switch to:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        
    elif action.startswith("use_"):
        idx = int(action.split("_")[1])
        try:
            key = gemini_manager.switch(str(idx + 1))
            await callback.message.edit_text(f"✅ Active Gemini API Key manually switched to: <b>{key.name}</b>")
        except GeminiError as exc:
            await callback.message.edit_text(f"❌ {exc}")
            
    elif action == "models_menu":
        user_model = await get_user_model(callback.from_user.id)
        buttons = []
        for model_id, desc in AVAILABLE_MODELS.items():
            active_mark = "✅ " if model_id == user_model else " "
            buttons.append([InlineKeyboardButton(text=f"{active_mark}{desc}", callback_data=f"gemini_setmodel_{model_id}")])
        buttons.append([InlineKeyboardButton(text="🔙 Back", callback_data="gemini_back")])
        await callback.message.edit_text("🧠 <b>Select AI Model:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

    elif action.startswith("setmodel_"):
        model_id = action.split("setmodel_")[1]
        if model_id in AVAILABLE_MODELS:
            await set_user_model(callback.from_user.id, model_id)
            await callback.message.edit_text(f"✅ AI Model changed to: <b>{AVAILABLE_MODELS[model_id]}</b>\n\n(Applies to chat only. Scheduler uses default.)")

    elif action == "back":
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📊 Check API Status", callback_data="gemini_status")],
                [InlineKeyboardButton(text="🔄 Test API Fallback", callback_data="gemini_test")],
                [InlineKeyboardButton(text="🔑 Switch API Key", callback_data="gemini_keys_menu")],
                [InlineKeyboardButton(text="🧠 Change AI Model", callback_data="gemini_models_menu")]
            ]
        )
        await callback.message.edit_text("⚙️ <b>AI & API Dashboard</b>\nSelect an option below:", reply_markup=keyboard)
        
    await callback.answer()

# ─────────────────── /track ───────────────────
@dp.message(Command("track"), F.from_user.id == (int(USER_ID) if USER_ID else 0))
async def track_handler(message: types.Message) -> None:
    text = message.text or ""
    parts = text.split()
    
    if len(parts) == 1:
        # Guided flow
        msg = (
            "➕ <b>Track a position</b>\n\n"
            "Send as one line:\n"
            "<code>/track SYMBOL ENTRY TARGET STOPLOSS [QTY]</code>\n\n"
            "Example: <code>/track RELIANCE 1240 1310 1195 20</code>"
        )
        # Fetch top screener candidates to suggest
        if mongo.db is not None:
            cands = await mongo.db.screener_scores.find({"date": today_ist()}).sort("score", -1).limit(3).to_list(None)
            if cands:
                msg += "\n\nOr use a candidate from today's screener (coming soon):"
                kb = InlineKeyboardMarkup(inline_keyboard=[])
                # We don't have the screener callback logic fully built out yet, so just leave it as text for now
                for c in cands:
                    msg += f"\n- {c['symbol']} (Score: {c['score']})"
        await message.answer(msg, parse_mode="HTML")
        return
        
    if len(parts) < 5:
        await message.answer("⚠️ Not enough arguments.\nUsage: /track SYMBOL ENTRY TARGET STOPLOSS [QTY]")
        return
        
    symbol = parts[1].upper()
    try:
        entry = float(parts[2])
        target = float(parts[3])
        stop = float(parts[4])
        qty = int(parts[5]) if len(parts) > 5 else 0
        
        from features.swing.service import create_manual_position
        pos = await create_manual_position(
            symbol=symbol,
            entry_low=entry,
            entry_high=entry,
            t1=target,
            stop_loss=stop,
            qty=qty
        )
        await message.answer(f"✅ Now tracking <b>{symbol}</b> (Manual Setup).\nStatus: PENDING_ENTRY")
    except ValueError:
        await message.answer("⚠️ Invalid number format.\nUsage: /track SYMBOL 100 120 90")
        

# ─────────────────── /storage ───────────────────
from features.storage.service import storage_stats
from core.retention import cleanup

@dp.message(Command("storage"), F.from_user.id == (int(USER_ID) if USER_ID else 0))
async def storage_handler(message: types.Message) -> None:
    stats = await storage_stats()
    usage = stats.get("usage_percent", 0)
    db_mb = stats.get("db_size", 0) / (1024 * 1024)
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧹 Run Cleanup (Dry Run)", callback_data="storage_cleanup_dry")],
            [InlineKeyboardButton(text="🗑️ Run Cleanup (Confirm)", callback_data="storage_cleanup_confirm")]
        ]
    )
    
    await message.answer(
        f"💾 <b>Storage Manager</b>\n\n"
        f"Usage: {usage:.2f}% of 512MB limit.\n"
        f"DB Size: {db_mb:.2f} MB",
        reply_markup=keyboard
    )

@dp.callback_query(F.data.startswith("storage_"))
async def storage_callback(callback: types.CallbackQuery) -> None:
    action = callback.data.split("storage_")[1]
    
    if action == "cleanup_dry":
        res = await cleanup(dry_run=True, confirm=False)
        counts = res.get('deleted_counts', {})
        text = "\n".join([f"{k}: {v}" for k, v in counts.items()])
        await callback.message.edit_text(f"🧹 <b>Dry Run Cleanup</b>\n\nWould delete:\n{text}")
    elif action == "cleanup_confirm":
        res = await cleanup(dry_run=False, confirm=True)
        counts = res.get('deleted_counts', {})
        text = "\n".join([f"{k}: {v}" for k, v in counts.items()])
        await callback.message.edit_text(f"🗑️ <b>Cleanup Complete</b>\n\nDeleted:\n{text}")
        
    await callback.answer()


# ─────────────────── photo handler (vision) ───────────────────
DEFAULT_VISION_PROMPT = (
    "You are StockAI (QMAF-Advisor), an elite Indian markets analyst.\n"
    "Analyze this image using your full expertise: identify the chart pattern, "
    "key support/resistance levels, technical indicators visible (RSI, MACD, volume, candle patterns), "
    "Wyckoff phase if applicable, and provide a clear actionable recommendation with entry, target, and stop-loss."
)

@dp.message(F.photo, F.from_user.id == (int(USER_ID) if USER_ID else 0))
async def photo_handler(message: types.Message) -> None:
    uid = message.from_user.id
    caption = message.caption or ""
    prompt = caption.strip() if caption.strip() else DEFAULT_VISION_PROMPT

    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

    # Download highest resolution photo from Telegram
    photo = message.photo[-1]  # last = largest
    file = await message.bot.get_file(photo.file_id)
    file_bytes = await message.bot.download_file(file.file_path)
    image_bytes = file_bytes.read() if hasattr(file_bytes, "read") else bytes(file_bytes)

    user_model = await get_user_model(uid)

    try:
        result = await generate_with_gemini_vision(
            image_bytes=image_bytes,
            mime_type="image/jpeg",
            prompt=prompt,
            model=user_model,
        )
        answer = format_gemini_answer(result)
    except Exception as exc:
        answer = f"⚠️ Vision analysis failed: {exc}"

    # Persist both sides to memory
    await save_turn(uid, "user", f"[IMAGE] {caption}" if caption else "[IMAGE sent]")
    await save_turn(uid, "assistant", answer)

    await message.answer(answer)


# ─────────────────── document handler (PDF / file) ──────────────
SUPPORTED_DOC_MIME = {"application/pdf", "image/jpeg", "image/png", "image/webp", "image/gif"}

@dp.message(F.document, F.from_user.id == (int(USER_ID) if USER_ID else 0))
async def document_handler(message: types.Message) -> None:
    uid = message.from_user.id
    doc = message.document
    mime = doc.mime_type or ""
    caption = message.caption or ""

    if mime not in SUPPORTED_DOC_MIME:
        await message.answer(
            f"📎 File type <b>{mime or 'unknown'}</b> is not supported for AI analysis.\n"
            "Supported: PDF, JPEG, PNG, WEBP, GIF."
        )
        return

    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

    file = await message.bot.get_file(doc.file_id)
    file_bytes = await message.bot.download_file(file.file_path)
    raw_bytes = file_bytes.read() if hasattr(file_bytes, "read") else bytes(file_bytes)

    prompt = caption.strip() if caption.strip() else (
        "Analyze this document and extract all relevant financial data, "
        "charts, or trading information. Apply QMAF rules where applicable."
    )

    user_model = await get_user_model(uid)

    try:
        result = await generate_with_gemini_vision(
            image_bytes=raw_bytes,
            mime_type=mime,
            prompt=prompt,
            model=user_model,
        )
        answer = format_gemini_answer(result)
    except Exception as exc:
        answer = f"⚠️ Document analysis failed: {exc}"

    await save_turn(uid, "user", f"[FILE: {doc.file_name}] {caption}")
    await save_turn(uid, "assistant", answer)

    await message.answer(answer)


# ─────────────────── /positions ───────────────────
@dp.message(Command("positions"), F.from_user.id == (int(USER_ID) if USER_ID else 0))
async def positions_handler(message: types.Message) -> None:
    from features.swing.service import get_positions
    pos = await get_positions()
    open_pos = [p for p in pos if p["status"] in ("OPEN", "PENDING_ENTRY")]
    if not open_pos:
        await message.answer("No open swing positions.")
        return
    
    lines = ["📊 <b>Open Swing Positions</b>\n"]
    for p in open_pos:
        st = "🟢" if p["status"] == "OPEN" else "⏳"
        fill = f" Fill: {p['fill_price']}" if p.get('fill_price') else f" Entry: {p['entry_zone_low']}-{p['entry_zone_high']}"
        lines.append(f"{st} <b>{p['symbol']}</b> | {p['status']}{fill}")
        if p["status"] == "OPEN":
            lines.append(f"   T1: {p.get('t1')} | Stop: {p.get('trailing_stop')} | Days: {p.get('days_held',0)}")
    
    await message.answer("\n".join(lines))

# ─────────────────── /perf ───────────────────
@dp.message(Command("perf"), F.from_user.id == (int(USER_ID) if USER_ID else 0))
async def perf_handler(message: types.Message) -> None:
    from features.swing.service import performance
    parts = message.text.split()
    days = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 90
    
    perf = await performance(days)
    if perf.get("trades", 0) == 0:
        await message.answer(f"No closed trades in the last {days} days.")
        return
        
    lines = [
        f"📈 <b>Swing Performance ({days} days)</b>\n",
        f"Trades: <b>{perf['trades']}</b>",
        f"Win Rate: <b>{perf['win_rate_pct']}%</b>",
        f"Avg Win R: <b>{perf['avg_win_r']}</b>",
        f"Avg Loss R: <b>{perf['avg_loss_r']}</b>",
        f"Expectancy R: <b>{perf['expectancy_r']}</b>",
        f"Avg Hold Days: <b>{perf['avg_hold_days']}</b>"
    ]
    await message.answer("\n".join(lines))


# =================== /screener ===================
@dp.message(Command("screener"), F.from_user.id == (int(USER_ID) if USER_ID else 0))
async def screener_handler(message: types.Message) -> None:
    from core.database import mongo
    from core.timeutils import today_ist
    
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    if mongo.db is None:
        await message.answer("Database disconnected.")
        return
        
    cands = await mongo.db.screener_scores.find({"date": today_ist()}).sort("score", -1).limit(10).to_list(None)
    if not cands:
        await message.answer("Screener hasn't run yet today. Use the dashboard to force run it.")
        return
        
    lines = [f"🎯 <b>Top Screener Candidates ({today_ist()})</b>\n"]
    for c in cands:
        setup = c.get('setup_type', 'UNKNOWN').replace("_", " ")
        lines.append(
            f"<b>{c['symbol']}</b> (Score: {c['score']})\n"
            f"└ {setup} | CMP: {c.get('cmp', 0)} | SL: {c.get('suggested_stop', 0)}"
        )
        
    await message.answer("\n\n".join(lines), parse_mode="HTML")

# =================== /paper ===================
@dp.message(Command("paper"), F.from_user.id == (int(USER_ID) if USER_ID else 0))
async def paper_handler(message: types.Message) -> None:
    from features.paper_portfolio.service import get_paper_performance
    parts = message.text.split()
    days = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 90
    
    perf = await get_paper_performance(days)
    if perf.get("trades", 0) == 0:
        await message.answer(f"No paper trades in the last {days} days.")
        return
        
    vs = perf.get("vs_real", {})
    
    lines = [
        f"📝 <b>Paper Portfolio Performance ({days} days)</b>\n",
        f"Paper Trades: <b>{perf['trades']}</b> (vs Real: {vs.get('real_trades', 0)})",
        f"Paper Win Rate: <b>{perf['win_rate_pct']}%</b> (vs Real: {vs.get('real_win_rate', 0)}%)",
        f"Paper Expectancy R: <b>{perf['expectancy_r']}</b> (vs Real: {vs.get('real_expectancy_r', 0)})",
        f"\nAvg Win R: <b>{perf['avg_win_r']}</b>",
        f"Avg Loss R: <b>{perf['avg_loss_r']}</b>",
        f"Avg Hold Days: <b>{perf['avg_hold_days']}</b>"
    ]
    await message.answer("\n".join(lines))


# =================== /regime ===================
@dp.message(Command("regime"), F.from_user.id == (int(USER_ID) if USER_ID else 0))
async def regime_handler(message: types.Message) -> None:
    from features.screener.service import get_regime
    reg = await get_regime()
    text = (
        f"📊 <b>Market Regime</b>\n\n"
        f"State: <b>{reg['state']}</b>\n"
        f"Nifty vs 200 DMA: {'Above' if reg.get('nifty_above_200dma') else 'Below'} ({reg.get('nifty_dma_pct', 0)}%)\n"
        f"Market Breadth: {reg.get('breadth_pct', 0)}% > 50DMA\n"
        f"India VIX Rank: {reg.get('vix_pct', 0)}%\n\n"
        f"Position Sizing: {reg['size_multiplier']}x\n"
        f"Max Positions: {reg['max_positions']}"
    )
    await message.answer(text, parse_mode="HTML")

# =================== /dip ===================
@dp.message(Command("dip"), F.from_user.id == (int(USER_ID) if USER_ID else 0))
async def dip_handler(message: types.Message) -> None:
    from features.investments.service import get_etf_dip_status
    dips = await get_etf_dip_status()
    if not dips or not dips.get("etf_metrics"):
        await message.answer("No ETF data available.")
        return
    lines = [f"📉 <b>ETF Dip Status</b> (Overall: {dips.get('tier', 'NONE')})\n"]
    for sym, metrics in dips.get("etf_metrics", {}).items():
        lines.append(f"<b>{sym}</b>")
        lines.append(f"└ CMP: {metrics['close']:.2f} | 20d High: {metrics['high_20d']:.2f} (-{metrics['pct_below_high']:.2f}%)")
    
    allocs = dips.get("allocations", [])
    if allocs:
        lines.append("\n<b>Allocations:</b>")
        for a in allocs:
            lines.append(f"└ {a['symbol']}: ₹{a['deploy_amount']} ({a['weight_pct']}%)")
            
    await message.answer("\n".join(lines), parse_mode="HTML")

# =================== /sip ===================
@dp.message(Command("sip"), F.from_user.id == (int(USER_ID) if USER_ID else 0))
async def sip_handler(message: types.Message) -> None:
    from features.investments.service import get_sip_xirr
    data = await get_sip_xirr()
    if not data or "overall" not in data:
        await message.answer("No SIP data available.")
        return
    ov = data["overall"]
    lines = [
        "💰 <b>SIP Portfolio</b>\n",
        f"Invested: ₹{ov.get('invested', 0)}",
        f"Current: ₹{ov.get('current_value', 0)}",
        f"XIRR: <b>{ov.get('xirr_pct', 0)}%</b>\n",
        "<b>Funds:</b>"
    ]
    for m in data.get("mutual_funds", []):
        lines.append(f"- {m['name']} ({m['xirr_pct']}%)")
    await message.answer("\n".join(lines), parse_mode="HTML")

# =================== /journal ===================
@dp.message(Command("journal"), F.from_user.id == (int(USER_ID) if USER_ID else 0))
async def journal_handler(message: types.Message) -> None:
    from features.performance.router import get_journal_metrics
    m = await get_journal_metrics()
    if isinstance(m, dict) and "error" in m:
        await message.answer("No journal data available.")
        return
    lines = [
        "📓 <b>Trade Journal</b>\n",
        f"Win Rate: <b>{m.get('win_rate_pct', 0)}%</b> ({m.get('winning_trades', 0)}W / {m.get('losing_trades', 0)}L)",
        f"Avg Win: {m.get('avg_win_r', 0)}R",
        f"Avg Loss: {m.get('avg_loss_r', 0)}R",
        f"Expectancy: <b>{m.get('expectancy_r', 0)}R</b>",
        f"Total Costs: ₹{m.get('total_costs', 0)}"
    ]
    await message.answer("\n".join(lines), parse_mode="HTML")

# =================== /hitrate ===================
@dp.message(Command("hitrate"), F.from_user.id == (int(USER_ID) if USER_ID else 0))
async def hitrate_handler(message: types.Message) -> None:
    from features.performance.service import get_hit_rate
    m = await get_hit_rate(30)
    lines = [
        "🎯 <b>AI Hit Rate (30 Days)</b>\n",
        f"Hit Rate: <b>{m.get('hit_rate_pct', 0)}%</b>",
        f"Passes: {m.get('passes', 0)} | Fails: {m.get('fails', 0)}",
        f"Untriggered: {m.get('untriggered', 0)}",
        f"Total: {m.get('total_recommendations', 0)}"
    ]
    await message.answer("\n".join(lines), parse_mode="HTML")


# =================== Unimplemented Stubs ===================
@dp.message(Command("analyze", "chart", "risk", "update", "close", "untrack", "ai", "health", "allocation", "history"), F.from_user.id == (int(USER_ID) if USER_ID else 0))
async def stub_handler(message: types.Message) -> None:
    cmd = message.text.split()[0]
    await message.answer(f"🚧 Command <b>{cmd}</b> is currently being built and will be available soon.", parse_mode="HTML")

# ─────────────────── main chat handler (text only) ──────────────
@dp.message(F.from_user.id == (int(USER_ID) if USER_ID else 0))
async def ai_chat_handler(message: types.Message) -> None:
    if not message.text:
        await message.answer(
            "📸 Send a <b>photo</b> or <b>PDF</b> and I'll analyse it.\n"
            "Or type your question and I'll answer it."
        )
        return

    uid = message.from_user.id
    user_text = message.text

    if user_text.startswith("/"):
        await message.answer(f"⚠️ Command <b>{user_text.split()[0]}</b> is not recognized or not implemented yet.\nType /menu to see available commands.", parse_mode="HTML")
        return

    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

    # Save user turn to memory
    await save_turn(uid, "user", user_text)

    # Fetch recent history + latest morning alert for context
    history = await get_history(uid, last_n=10)
    alert_ctx = await get_last_morning_alert()

    # Search knowledge base for relevant rules
    rag_ctx = await get_rag_context("chat", top_k=3)

    # Build context-aware prompt
    full_prompt = _build_context_prompt(history[:-1], user_text, alert_ctx, rag_ctx)

    # Use user's saved model preference
    user_model = await get_user_model(uid)

    try:
        result = await generate_with_gemini_fallback(full_prompt, model=user_model)
        answer = format_gemini_answer(result)
    except Exception as exc:
        answer = f"⚠️ Gemini error: {exc}"

    await message.answer(answer)

    # Save assistant turn to memory
    await save_turn(uid, "assistant", answer)
