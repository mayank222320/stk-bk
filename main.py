import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone, UTC
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from core.auth import require_token

from core.database import mongo
from features.bot.setup import bot, dp
from aiogram.types import BotCommand
import features.bot.handlers  # registers all handlers

from features.gemini.router import router as gemini_router
from features.notifications.router import router as notifications_router
from features.system.router import router as system_router
from features.scheduler.service import start_scheduler, stop_scheduler
from features.chat_memory.service import ensure_ttl_index
from features.performance.router import router as performance_router
from features.chat.router import router as chat_router
from features.market_data.router import router as market_router
from features.grok.router import router as grok_router
from features.portfolio.router import router as portfolio_router
from features.news_scanner.router import router as news_scanner_router
from features.storage.router import router as storage_router
from features.swing.router import router as swing_router
from features.swing.service import ensure_indexes as ensure_swing_indexes
from features.paper_portfolio.router import router as paper_router
from features.paper_portfolio.service import ensure_indexes as ensure_paper_indexes
from features.alerts.router import router as alerts_router
from core.alerts import ensure_alert_indexes
from features.screener.router import router as screener_router
from features.risk.router import router as risk_router
from features.investments.router import router as investments_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────
    await mongo.connect()
    await ensure_ttl_index()          # MongoDB TTL index for chat history
    # Ensure fast deduplication lookups for the news scanner
    if mongo.db is not None:
        await mongo.db.processed_news.create_index(
            [("url", 1), ("processed_at", -1)], background=True
        )
        await mongo.db.news_alerts.create_index([("alerted_at", -1)], background=True)
        # ── RAG Startup Assertion ──────────────────────────────
        count = await mongo.db.knowledge_chunks.count_documents({})
        if count == 0:
            print("[WARNING] knowledge_chunks is empty. Did you run the indexer?")
        else:
            sample = await mongo.db.knowledge_chunks.find_one({"tags": "swing"})
            if sample:
                print(f"[RAG] Startup verified. {count} chunks loaded. Sample loaded from source: {sample.get('source')}")
        await ensure_swing_indexes()
        await ensure_paper_indexes()
        await ensure_alert_indexes()
    start_scheduler()                 # Morning & evening cron jobs
    
    # Set up Telegram Bot Menu Commands (skip gracefully if token is invalid/missing)
    _bot_enabled = False
    try:
        commands = [
            BotCommand(command="menu",      description="📋 All features — tap to browse"),
            BotCommand(command="positions", description="📊 Open swing positions"),
            BotCommand(command="track",     description="➕ Track a new position"),
            BotCommand(command="screener",  description="🔍 Today's ranked candidates"),
            BotCommand(command="analyze",   description="🔬 Full swing analysis"),
            BotCommand(command="risk",      description="🧮 Position size calculator"),
            BotCommand(command="regime",    description="🌡 Market regime today"),
            BotCommand(command="sip",       description="💰 SIP status and XIRR"),
            BotCommand(command="dip",       description="🥇 GOLDBEES/MON100 dip status"),
            BotCommand(command="journal",   description="📈 Expectancy and win rate"),
            BotCommand(command="alerts",    description="🔔 Configure alert events"),
            BotCommand(command="storage",   description="💾 Storage usage and cleanup"),
            BotCommand(command="health",    description="🩺 System health check"),
            BotCommand(command="help",      description="❓ Command reference"),
        ]
        await bot.set_my_commands(commands)
        await bot.delete_webhook(drop_pending_updates=True)
        _bot_enabled = True
        print("[Bot] Telegram bot configured successfully.")
    except Exception as e:
        print(f"[Bot] Telegram unavailable (token not configured?): {e}. Server continues without bot.")

    # Start polling only if bot is properly configured
    async def start_bot_delayed():
        if not _bot_enabled:
            return
        await asyncio.sleep(5)
        print("Telegram bot starting polling safely...")
        try:
            await dp.start_polling(bot)
        except Exception as e:
            print(f"Bot polling encountered an error: {e}")

    polling_task = asyncio.create_task(start_bot_delayed())

    yield
    # ── Shutdown ─────────────────────────────────────────────
    print("Shutting down...")
    stop_scheduler()
    polling_task.cancel()
    try:
        await polling_task
    except asyncio.CancelledError:
        pass
    try:
        await bot.session.close()
    except Exception:
        pass
    await mongo.close()


app = FastAPI(
    title="Stock Server",
    description="Intelligent trading desk assistant — Gemini AI + Telegram + MongoDB",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://stock-ai-henna.vercel.app",
        "https://stock-ai-henna.vercel.app/",
        "https://stock-axjlbvrsc-kalparatnas-projects.vercel.app",
        "https://stock-axjlbvrsc-kalparatnas-projects.vercel.app/"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@system_router.get("/ping")
async def ping():
    return {"status": "awake", "time": datetime.now(UTC).isoformat()}

app.include_router(system_router)
for r in (gemini_router, notifications_router, performance_router, chat_router,
          market_router, grok_router, portfolio_router, news_scanner_router,
          storage_router, swing_router, paper_router, alerts_router, screener_router, risk_router, investments_router):
    app.include_router(r, dependencies=[Depends(require_token)])