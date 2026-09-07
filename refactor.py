import os
import shutil
from pathlib import Path

# Paths
BASE_DIR = Path("f:/Stock/stockserver")

# Code snippets
code_core_database = """from typing import Any
try:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
except ImportError:
    AsyncIOMotorClient = None
    AsyncIOMotorDatabase = None

from core.config import MONGO_CONNECTION_STRING, MONGO_DATABASE_NAME

class MongoConnection:
    def __init__(self, uri: str | None, database_name: str):
        self.uri = uri
        self.database_name = database_name
        self.client: AsyncIOMotorClient | None = None
        self.db: AsyncIOMotorDatabase | None = None
        self.error: str | None = None

    async def connect(self) -> None:
        if AsyncIOMotorClient is None:
            self.error = "MongoDB driver missing. Run: pip install -r requirements.txt"
            return

        if not self.uri:
            self.error = "MongoDB connection string not found in .env"
            return

        try:
            self.client = AsyncIOMotorClient(self.uri, serverSelectionTimeoutMS=5000)
            self.db = self.client[self.database_name]
            await self.client.admin.command("ping")
            self.error = None
        except Exception as exc:
            self.error = str(exc)

    async def close(self) -> None:
        if self.client:
            self.client.close()
            self.client = None
            self.db = None

    async def status(self) -> dict[str, Any]:
        if not self.client:
            return {"connected": False, "database": self.database_name, "error": self.error}
        try:
            await self.client.admin.command("ping")
            return {"connected": True, "database": self.database_name, "error": None}
        except Exception as exc:
            self.error = str(exc)
            return {"connected": False, "database": self.database_name, "error": self.error}

mongo = MongoConnection(MONGO_CONNECTION_STRING, MONGO_DATABASE_NAME)
"""

code_features_gemini_schemas = """from pydantic import BaseModel, Field
from dataclasses import dataclass

class GeminiRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    model: str | None = None
    use_search: bool = True

class GeminiSwitchRequest(BaseModel):
    key: str | int

@dataclass
class GeminiKey:
    name: str
    value: str

class GeminiError(Exception):
    pass
"""

code_features_gemini_service = (BASE_DIR / "services/gemini.py").read_text(encoding="utf-8")
code_features_gemini_service = code_features_gemini_service.replace("schemas.models", "features.gemini.schemas")

code_features_gemini_router = """from fastapi import APIRouter, HTTPException
from features.gemini.schemas import GeminiRequest, GeminiSwitchRequest, GeminiError
from features.gemini.service import generate_with_gemini_fallback, gemini_manager

router = APIRouter(prefix="/gemini", tags=["Gemini"])

@router.get("/status")
def gemini_status():
    return gemini_manager.status()

@router.post("/switch")
def switch_gemini_key(request: GeminiSwitchRequest):
    try:
        key = gemini_manager.switch(request.key)
        return {"status": "success", "active": key.name}
    except GeminiError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.post("/generate")
async def generate_gemini(request: GeminiRequest):
    try:
        return await generate_with_gemini_fallback(request.prompt, request.model, request.use_search)
    except GeminiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
"""

code_features_notifications_service = """import aiohttp
from core.config import NTFY_TOPIC

async def send_ntfy_notification(text: str):
    if not NTFY_TOPIC:
        return
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://ntfy.sh/{NTFY_TOPIC}"
            safe_text = text[:4000] if len(text) > 4000 else text
            await session.post(url, data=safe_text.encode("utf-8"))
    except Exception as e:
        print(f"Failed to send ntfy notification: {e}")
"""

code_features_notifications_router = """from fastapi import APIRouter
import aiohttp
from features.bot.setup import bot
from core.config import USER_ID, NTFY_TOPIC

router = APIRouter(tags=["Notifications"])

@router.post("/notify")
async def send_notification(text: str):
    results = {}

    if USER_ID:
        try:
            await bot.send_message(chat_id=USER_ID, text=f"🔔 <b>Notification:</b>\\n{text}")
            results["telegram"] = {"status": "success"}
        except Exception as e:
            results["telegram"] = {"status": "error", "message": str(e)}
    else:
        results["telegram"] = {"status": "skipped", "message": "Userid not found in .env"}

    if NTFY_TOPIC:
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://ntfy.sh/{NTFY_TOPIC}"
                async with session.post(url, data=text.encode("utf-8")) as resp:
                    if resp.status >= 400:
                        error_text = await resp.text()
                        results["ntfy"] = {"status": "error", "message": error_text}
                    else:
                        results["ntfy"] = {"status": "success"}
        except Exception as e:
            results["ntfy"] = {"status": "error", "message": str(e)}
    else:
        results["ntfy"] = {"status": "skipped", "message": "NTFY_TOPIC not found in .env"}

    return {"status": "processed", "results": results}
"""

code_features_bot_setup = (BASE_DIR / "bot/setup.py").read_text(encoding="utf-8")

code_features_bot_handlers = """from aiogram import types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from features.bot.setup import dp
from core.config import USER_ID, AVAILABLE_MODELS
from features.gemini.schemas import GeminiError
from features.gemini.service import (
    generate_with_gemini_fallback,
    format_gemini_answer,
    format_gemini_status,
    gemini_manager
)
from features.notifications.service import send_ntfy_notification

USER_PREFERRED_MODEL = "gemini-3.5-flash"

@dp.message(CommandStart(), F.from_user.id == int(USER_ID))
async def command_start_handler(message: types.Message) -> None:
    await message.answer(f"Hello, {message.from_user.full_name}! The Stock Server bot is up and running.\\nSend /model to choose your AI model.")

@dp.message(Command("model"), F.from_user.id == int(USER_ID))
async def command_model_handler(message: types.Message) -> None:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=desc, callback_data=f"model_{model_id}")]
        for model_id, desc in AVAILABLE_MODELS.items()
    ])
    await message.answer(f"Current model: <b>{USER_PREFERRED_MODEL}</b>\\nSelect a model:", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("model_"))
async def model_callback_handler(callback: types.CallbackQuery) -> None:
    global USER_PREFERRED_MODEL
    model_id = callback.data.split("model_")[1]
    if model_id in AVAILABLE_MODELS:
        USER_PREFERRED_MODEL = model_id
        await callback.message.edit_text(f"✅ Model changed to: <b>{AVAILABLE_MODELS[model_id]}</b>")
    await callback.answer()

@dp.message(Command("gemini"), F.from_user.id == int(USER_ID))
async def gemini_handler(message: types.Message) -> None:
    text = message.text or ""
    parts = text.split(maxsplit=2)
    action = parts[1].lower() if len(parts) > 1 else "status"

    if action in {"help", "start"}:
        await message.answer(
            "Commands:\\n"
            "/gemini status\\n"
            "/gemini use <number-or-env-name>\\n"
            "/gemini test [prompt]\\n"
            "/gemini ask <prompt>"
        )
        return

    if action in {"status", "list"}:
        await message.answer(format_gemini_status())
        return

    if action in {"use", "set", "switch", "change"}:
        if len(parts) < 3:
            await message.answer("Send: /gemini use <number-or-env-name>")
            return
        try:
            key = gemini_manager.switch(parts[2])
            await message.answer(f"Active Gemini key changed to {key.name}.")
        except GeminiError as exc:
            await message.answer(str(exc))
        return

    if action == "test":
        prompt = parts[2] if len(parts) > 2 else "Say Gemini fallback is working in one short sentence."
        try:
            result = await generate_with_gemini_fallback(prompt)
            answer = format_gemini_answer(result)
            await message.answer(f"Using {result['key']} / {result['model']}:\\n{answer}")
        except GeminiError as exc:
            await message.answer(str(exc))
        return

    if action == "ask":
        if len(parts) < 3:
            await message.answer("Send: /gemini ask <prompt>")
            return
        try:
            result = await generate_with_gemini_fallback(parts[2])
            answer = format_gemini_answer(result)
            await message.answer(answer)
            await send_ntfy_notification(f"Bot Response:\\n{answer}")
        except GeminiError as exc:
            await message.answer(str(exc))
        return

    await message.answer("Unknown command. Send /gemini help")

@dp.message(F.from_user.id == int(USER_ID))
async def ai_chat_handler(message: types.Message) -> None:
    if not message.text:
        await message.answer("Please send a text message for Gemini.")
        return

    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    try:
        result = await generate_with_gemini_fallback(message.text, model=USER_PREFERRED_MODEL)
        answer = format_gemini_answer(result)
        await message.answer(answer)
        await send_ntfy_notification(f"Bot Response:\\n{answer}")
    except GeminiError as exc:
        await message.answer(f"Gemini error: {exc}")
"""

code_features_system_router = """from fastapi import APIRouter
from core.database import mongo

router = APIRouter(tags=["System"])

@router.get("/")
def read_root():
    return {"message": "Welcome to Stock Server Backend. FastAPI is integrated with Telegram Bot."}

@router.get("/mongo/status")
async def mongo_status():
    return await mongo.status()
"""

code_main = """import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI

from core.database import mongo
from features.bot.setup import bot, dp
import features.bot.handlers

from features.gemini.router import router as gemini_router
from features.notifications.router import router as notifications_router
from features.system.router import router as system_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    await mongo.connect()
    polling_task = asyncio.create_task(dp.start_polling(bot))
    print("Telegram bot started polling...")
    yield
    print("Shutting down telegram bot...")
    polling_task.cancel()
    await bot.session.close()
    await mongo.close()

app = FastAPI(lifespan=lifespan)

app.include_router(system_router)
app.include_router(gemini_router)
app.include_router(notifications_router)
"""

# Create directories
for d in [
    "core",
    "features/gemini",
    "features/notifications",
    "features/bot",
    "features/system"
]:
    (BASE_DIR / d).mkdir(parents=True, exist_ok=True)

# Write files
(BASE_DIR / "core/database.py").write_text(code_core_database, encoding="utf-8")
(BASE_DIR / "features/gemini/schemas.py").write_text(code_features_gemini_schemas, encoding="utf-8")
(BASE_DIR / "features/gemini/service.py").write_text(code_features_gemini_service, encoding="utf-8")
(BASE_DIR / "features/gemini/router.py").write_text(code_features_gemini_router, encoding="utf-8")
(BASE_DIR / "features/notifications/service.py").write_text(code_features_notifications_service, encoding="utf-8")
(BASE_DIR / "features/notifications/router.py").write_text(code_features_notifications_router, encoding="utf-8")
(BASE_DIR / "features/bot/setup.py").write_text(code_features_bot_setup, encoding="utf-8")
(BASE_DIR / "features/bot/handlers.py").write_text(code_features_bot_handlers, encoding="utf-8")
(BASE_DIR / "features/system/router.py").write_text(code_features_system_router, encoding="utf-8")
(BASE_DIR / "main.py").write_text(code_main, encoding="utf-8")

# Clean up old directories
for d in ["db", "schemas", "services", "api", "bot"]:
    p = BASE_DIR / d
    if p.exists() and p.is_dir():
        shutil.rmtree(p)

print("Refactoring completed successfully.")
