from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import Config
from app.telegram_client import bot_api_method_url, create_bot, normalize_bot_api_url


def _config(api_url: str) -> Config:
    return Config(
        bot_token="123456:test",
        bot_api_url=api_url,
        db_path=":memory:",
        bot_admin_ids=set(),
        owner_id=None,
        alerts_api_token=None,
    )


def test_normalize_bot_api_url_defaults_to_cloud() -> None:
    assert normalize_bot_api_url("") == "https://api.telegram.org"
    assert normalize_bot_api_url("http://127.0.0.1:8081/") == "http://127.0.0.1:8081"


def test_bot_api_method_url_uses_configured_base() -> None:
    assert bot_api_method_url("token", "getMe", "http://127.0.0.1:8081/") == "http://127.0.0.1:8081/bottoken/getMe"


def test_create_bot_uses_local_api_session_for_custom_endpoint() -> None:
    bot = create_bot(_config("http://127.0.0.1:8081"), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        assert bot.session.api.is_local is False
        assert bot.session.api.api_url("123456:test", "getMe") == "http://127.0.0.1:8081/bot123456:test/getMe"
    finally:
        # No HTTP session is opened until the bot makes a request.
        pass
