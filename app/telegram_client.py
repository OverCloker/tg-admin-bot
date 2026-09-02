from __future__ import annotations

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer

from .config import Config, load_config


DEFAULT_BOT_API_URL = "https://api.telegram.org"


def normalize_bot_api_url(api_url: str | None) -> str:
    value = (api_url or DEFAULT_BOT_API_URL).strip().rstrip("/")
    return value or DEFAULT_BOT_API_URL


def is_default_bot_api_url(api_url: str | None) -> bool:
    return normalize_bot_api_url(api_url).casefold() == DEFAULT_BOT_API_URL


def bot_api_method_url(token: str, method: str, api_url: str | None = None) -> str:
    return f"{normalize_bot_api_url(api_url)}/bot{token}/{method}"


def create_bot(
    config: Config | None = None,
    *,
    default: DefaultBotProperties | None = None,
) -> Bot:
    resolved = config or load_config()
    api_url = normalize_bot_api_url(resolved.bot_api_url)
    if is_default_bot_api_url(api_url):
        return Bot(token=resolved.bot_token, default=default)
    # The Bot API server runs in a separate container. Keep aiogram in multipart
    # upload mode so FSInputFile paths from bot/api containers don't need to be
    # visible inside the telegram-bot-api container.
    server = TelegramAPIServer.from_base(api_url, is_local=False)
    session = AiohttpSession(api=server)
    return Bot(token=resolved.bot_token, session=session, default=default)
