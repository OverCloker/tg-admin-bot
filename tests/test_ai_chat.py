import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app import bot
from app.ai_chat import ChatError, GeminiChat


def test_disabled_and_allowlist():
    chat = GeminiChat("secret", {-100})
    assert chat.allowed(-100)
    assert not chat.allowed(-101)
    assert not GeminiChat().allowed(-100)
    with pytest.raises(ChatError):
        asyncio.run(chat.ask((-101, 0, 9), "hello"))


def test_context_isolation_clear_and_limits(monkeypatch):
    chat = GeminiChat("secret", {-100, -101}, daily_limit=3)
    chat.generate = AsyncMock(return_value="Ответ")
    clock = [100.0]
    monkeypatch.setattr("app.ai_chat.time.monotonic", lambda: clock[0])
    scope = (-100, 0, 9)
    asyncio.run(chat.ask(scope, "Первый"))
    with pytest.raises(ChatError, match="10 секунд"):
        asyncio.run(chat.ask(scope, "Второй"))
    clock[0] += 11
    asyncio.run(chat.ask(scope, "Второй"))
    assert len(chat.generate.await_args.args[0]) == 3
    asyncio.run(chat.ask((-101, 0, 9), "Другой чат"))
    assert len(chat.generate.await_args.args[0]) == 1
    clock[0] += 11
    with pytest.raises(ChatError, match="Дневной"):
        asyncio.run(chat.ask((-100, 1, 10), "hi"))
    chat.clear(scope)
    assert scope not in chat.history


def test_provider_request_has_no_tools_or_key_in_url(monkeypatch):
    chat = GeminiChat("secret", {-100})
    response = MagicMock(status=200)
    response.json = AsyncMock(return_value={"candidates": [{"content": {"parts": [
        {"text": "internal", "thought": True}, {"text": "Привет"},
    ]}}]})
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=response)
    context.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.post.return_value = context
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("app.ai_chat.aiohttp.ClientSession", lambda **kwargs: session_context)
    assert asyncio.run(chat.generate([])) == "Привет"
    args, kwargs = session.post.call_args
    assert "secret" not in args[0]
    assert kwargs["headers"]["x-goog-api-key"] == "secret"
    assert "tools" not in kwargs["json"]
    response.status = 429
    with pytest.raises(ChatError, match="Лимит"):
        asyncio.run(chat.generate([]))


def test_failed_generation_does_not_save_history_or_hold_busy():
    chat = GeminiChat("secret", {-100})
    chat.generate = AsyncMock(side_effect=ChatError("temporary"))
    with pytest.raises(ChatError):
        asyncio.run(chat.ask((-100, 0, 9), "hello"))
    assert not chat.history and not chat.busy
    assert chat.requests == 1


def test_bot_requires_address_and_sends_plain_text(monkeypatch):
    chat = GeminiChat("secret", {-100})
    chat.ask = AsyncMock(return_value="<b>Не HTML</b>")
    monkeypatch.setattr(bot, "ai_chat", chat)
    message = SimpleNamespace(
        text="обычное сообщение", from_user=SimpleNamespace(id=9, is_bot=False),
        chat=SimpleNamespace(id=-100, type="supergroup"), message_thread_id=3,
        reply_to_message=None, reply=AsyncMock(),
        bot=SimpleNamespace(id=123, _ai_username="test_bot"),
    )
    assert not asyncio.run(bot.handle_ai_chat(message))
    chat.ask.assert_not_awaited()
    message.text = "@test_bot Привет"
    assert asyncio.run(bot.handle_ai_chat(message))
    chat.ask.assert_awaited_once_with((-100, 3, 9), "Привет")
    assert message.reply.await_args.kwargs["parse_mode"] is None
    assert "осталось 200 из 200" in message.reply.await_args.args[0]
    message.text = "/ai Вопрос"
    asyncio.run(bot.handle_ai_chat(message, explicit=True))
    assert chat.ask.await_args.args[1] == "Вопрос"


def test_persistent_setting_and_daily_limit(tmp_path):
    from app.db import Database
    from datetime import datetime, timezone, timedelta
    path = str(tmp_path / "ai.sqlite3")
    storage = Database(path)
    storage.init()
    chat = GeminiChat("secret", {-100}, daily_limit=2)
    chat.storage = storage
    chat.generate = AsyncMock(return_value="hello")
    storage.set_ai_chat_enabled(-100, False, 9)
    assert not chat.allowed(-100)
    storage.set_ai_chat_enabled(-101, True, 9)
    assert chat.allowed(-101)
    asyncio.run(chat.ask((-101, 0, 9), "hello"))
    assert chat.remaining() == 1
    storage.close()
    storage = Database(path)
    storage.init()
    chat = GeminiChat("secret", daily_limit=2)
    chat.storage = storage
    chat.generate = AsyncMock(return_value="hello")
    assert chat.allowed(-101) and not chat.allowed(-100)
    assert chat.remaining() == 1
    asyncio.run(chat.ask((-101, 0, 10), "hello"))
    assert chat.remaining() == 0
    with pytest.raises(ChatError, match="Дневной"):
        asyncio.run(chat.ask((-101, 0, 11), "hello"))
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
    assert storage.reserve_ai_request(tomorrow, 2)
    assert storage.ai_requests_used(tomorrow) == 1
    storage.close()


@pytest.mark.parametrize("admin,action", [(False, "включить"), (True, "включить"), (True, "выключить")])
def test_group_admin_can_toggle_ai(tmp_path, monkeypatch, admin, action):
    from app.db import Database
    storage = Database(str(tmp_path / "ai.sqlite3"))
    storage.init()
    chat = GeminiChat("secret", {-100})
    chat.storage = storage
    monkeypatch.setattr(bot, "ai_chat", chat)
    monkeypatch.setattr(bot, "db", storage, raising=False)
    monkeypatch.setattr(bot, "is_chat_admin", AsyncMock(return_value=admin))
    message = SimpleNamespace(
        text=f"ии {action}", chat=SimpleNamespace(id=-100, type="supergroup"),
        from_user=SimpleNamespace(id=9, is_bot=False), bot=SimpleNamespace(), reply=AsyncMock(),
    )
    asyncio.run(bot.ai_chat_settings_command(message))
    assert storage.get_ai_chat_enabled(-100) == (action == "включить" if admin else None)
    if admin:
        assert chat.allowed(-100) == (action == "включить")
    storage.close()


def test_disable_in_flight_drops_answer_and_memory(tmp_path):
    from app.db import Database
    storage = Database(str(tmp_path / "ai.sqlite3"))
    storage.init()
    chat = GeminiChat("secret", {-100})
    chat.storage = storage
    async def generate(_contents):
        storage.set_ai_chat_enabled(-100, False, 9)
        return "late answer"
    chat.generate = generate
    with pytest.raises(ChatError, match="выключено"):
        asyncio.run(chat.ask((-100, 0, 9), "hello"))
    assert not chat.history and not chat.busy
    storage.close()
