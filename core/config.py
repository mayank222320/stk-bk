"""
Central configuration for StockAI backend.
Uses Pydantic Settings for typed, validated environment variables.
"""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with strong validation."""

    # ── Telegram ──────────────────────────────────────────────────
    telegram_token: str = Field(default="")
    userid: int = Field(default=0, alias="Userid")
    bot_name: str = Field(default="stockskabot")

    # ── API Auth ──────────────────────────────────────────────────
    api_token: str = Field(default="", alias="API_TOKEN")

    # ── MongoDB ───────────────────────────────────────────────────
    connection_string: str = Field(default="")
    mongo_database_name: str = Field(default="stock", alias="MONGO_DATABASE_NAME")

    # ── Gemini ────────────────────────────────────────────────────
    gemini_model: str = Field(default="gemini-3.5-flash", alias="GEMINI_MODEL")
    gemini_fallback_models: str = Field(
        default="gemini-3.5-flash,gemini-flash-latest,gemini-2.5-flash,gemini-2.5-flash-lite,gemini-2.0-flash",
        alias="GEMINI_FALLBACK_MODELS",
    )

    # ── Trading & Risk Rules ──────────────────────────────────────
    trading_capital: float = Field(default=200_000.0)
    risk_pct_per_trade: float = Field(default=1.0, ge=0.1, le=2.0)
    max_hold_days: int = Field(default=10, ge=2, le=10)
    min_rr_to_t1: float = Field(default=2.0, ge=1.0)
    max_portfolio_heat_pct: float = Field(default=5.0, ge=1.0, le=20.0)

    # ── Notifications ─────────────────────────────────────────────
    ntfy_topic: str | None = Field(default=None, alias="NTFY_TOPIC")
    emailjs_service_id: str | None = Field(default=None, alias="EMAILJS_SERVICE_ID")
    emailjs_template_id: str | None = Field(default=None, alias="EMAILJS_TEMPLATE_ID")
    emailjs_user_id: str | None = Field(default=None, alias="EMAILJS_USER_ID")
    emailjs_private_key: str | None = Field(default=None, alias="EMAILJS_PRIVATE_KEY")

    # ── Scheduler ─────────────────────────────────────────────────
    max_watchlist_stocks: int = Field(default=5, alias="MAX_WATCHLIST_STOCKS")
    scheduler_morning_time: str = Field(default="09:20", alias="SCHEDULER_MORNING_TIME")
    scheduler_evening_time: str = Field(default="15:35", alias="SCHEDULER_EVENING_TIME")
    scheduler_timezone: str = Field(default="Asia/Kolkata", alias="SCHEDULER_TIMEZONE")

    # ── Data Retention / TTL ──────────────────────────────────────
    chat_history_ttl_days: int = Field(default=25, alias="CHAT_HISTORY_TTL_DAYS")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache(maxsize=1)
def settings() -> Settings:
    """Return cached singleton instance of application settings."""
    return Settings()


# ── Backward Compatibility Exports ───────────────────────────
# Legacy code still imports these module-level variables directly
_s = settings()
TELEGRAM_TOKEN = _s.telegram_token
USER_ID = str(_s.userid) if _s.userid else None
MONGO_CONNECTION_STRING = _s.connection_string
MONGO_DATABASE_NAME = _s.mongo_database_name
DEFAULT_GEMINI_MODEL = _s.gemini_model
DEFAULT_GEMINI_FALLBACK_MODELS = [m.strip() for m in _s.gemini_fallback_models.split(",") if m.strip()]
AVAILABLE_MODELS = {
    "gemini-3.5-flash": "Gemini 3.5 Flash (Recommended - Fast & Smart)",
    "gemini-3.1-flash": "Gemini 3.1 Flash (Standard Option)",
    "gemini-3.1-flash-lite": "Gemini 3.1 Flash-Lite (Super Fast & Light)",
    "gemini-2.5-flash": "Gemini 2.5 Flash (Stable Workhorse)",
}
NTFY_TOPIC = _s.ntfy_topic
EMAILJS_SERVICE_ID = _s.emailjs_service_id
EMAILJS_TEMPLATE_ID = _s.emailjs_template_id
EMAILJS_USER_ID = _s.emailjs_user_id
EMAILJS_PRIVATE_KEY = _s.emailjs_private_key
MAX_WATCHLIST_STOCKS = _s.max_watchlist_stocks
SCHEDULER_MORNING_TIME = _s.scheduler_morning_time
SCHEDULER_EVENING_TIME = _s.scheduler_evening_time
SCHEDULER_TIMEZONE = _s.scheduler_timezone
CHAT_HISTORY_TTL_DAYS = _s.chat_history_ttl_days
