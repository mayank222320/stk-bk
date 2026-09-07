from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from core.config import TELEGRAM_TOKEN

try:
    bot = Bot(token=TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
except Exception:
    # Use a dummy token if none provided so the server can still boot
    bot = Bot(token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11", default=DefaultBotProperties(parse_mode=ParseMode.HTML))

dp = Dispatcher()
