import asyncio
from types import SimpleNamespace

from app import bot as bot_module
from app.db import Database


def test_chat_user_blacklist_is_separate_per_chat_and_upserts_reason(tmp_path) -> None:
    path = tmp_path / "bot.sqlite3"
    service = Database(str(path))
    service.init()
    service.upsert_chat(-100, "First", "supergroup", None)
    service.upsert_chat(-200, "Second", "supergroup", None)
    service.add_blacklist_word(-100, "spam", 1)
    service.save_chat_blacklisted_user(-100, 9, "Vika", "Вика", "первое нарушение", 1)
    service.save_chat_blacklisted_user(-200, 9, "Vika", "Вика", "другая группа", 2)
    service.save_chat_blacklisted_user(-100, 9, "new_vika", "Вика", "повторное нарушение", 3)

    first = service.list_chat_blacklisted_users(-100)
    assert len(first) == 1
    assert (first[0].user_id, first[0].username, first[0].reason) == (9, "new_vika", "повторное нарушение")
    assert service.get_chat_blacklisted_user_by_username(-100, "@NEW_VIKA") == first[0]
    assert service.get_chat_blacklisted_user_by_username(-100, "@Vika") is None
    assert service.delete_chat_blacklisted_user(-100, 9) is True
    assert service.delete_chat_blacklisted_user(-100, 9) is False
    assert len(service.list_chat_blacklisted_users(-200)) == 1
    assert [word.word for word in service.list_blacklist_words(-100)] == ["spam"]
    service.close()

    reopened = Database(str(path))
    reopened.init()
    assert len(reopened.list_chat_blacklisted_users(-200)) == 1
    reopened.close()


def test_chat_user_blacklist_parses_reply_and_username_forms() -> None:
    parse = bot_module.parse_chat_blacklist_action
    assert parse("добавить в черный список\nСпам и оскорбления") == ("add", None, "Спам и оскорбления")
    assert parse("@vika123 в чс\nзаметка о пользователе") == ("add", "@vika123", "заметка о пользователе")
    assert parse("добавить в чс @vika123 - причина") == ("add", "@vika123", "причина")
    assert parse("удалить из чс") == ("remove", None, "")
    assert parse("@vika123 из чс") == ("remove", "@vika123", "")
    assert parse("удалить из черного списка @vika123") == ("remove", "@vika123", "")
    assert parse("удалить из чс\nнеожиданный текст") is None
    assert parse("") is None


def test_chat_user_blacklist_handlers_check_role_and_escape_reason(tmp_path, monkeypatch) -> None:
    service = Database(str(tmp_path / "bot.sqlite3"))
    service.init()
    service.upsert_chat(-100, "Chat", "supergroup", None)
    service.upsert_seen_user(-100, 9, "vika123", "Вика", False)
    replies: list[str] = []

    async def allowed(*_args):
        return "moderator"

    async def denied(*_args):
        return None

    async def remember(*_args):
        return None

    async def reply(_message, text, **_kwargs):
        replies.append(text)

    async def reply_chunks(_message, lines, **_kwargs):
        replies.append("\n".join(lines))

    monkeypatch.setattr(bot_module, "db", service, raising=False)
    monkeypatch.setattr(bot_module, "actor_moderation_role", allowed)
    monkeypatch.setattr(bot_module, "remember_sender", remember)
    monkeypatch.setattr(bot_module, "safe_reply", reply)
    monkeypatch.setattr(bot_module, "safe_reply_chunks", reply_chunks)
    message = SimpleNamespace(
        text="@vika123 в чс\nСпам <script>",
        chat=SimpleNamespace(id=-100, type="supergroup"),
        from_user=SimpleNamespace(id=7),
        reply_to_message=None,
        bot=SimpleNamespace(),
    )

    asyncio.run(bot_module.manage_chat_blacklisted_user(message))
    assert service.list_chat_blacklisted_users(-100)[0].reason == "Спам <script>"
    assert "&lt;script&gt;" in replies[-1]
    asyncio.run(bot_module.list_chat_blacklisted_users(message))
    assert "1. @vika123 — Спам &lt;script&gt;" in replies[-1]

    monkeypatch.setattr(bot_module, "actor_moderation_role", denied)
    message.text = "@vika123 из чс"
    asyncio.run(bot_module.manage_chat_blacklisted_user(message))
    assert len(service.list_chat_blacklisted_users(-100)) == 1
    assert "могут админы и модераторы" in replies[-1]

    monkeypatch.setattr(bot_module, "actor_moderation_role", allowed)
    asyncio.run(bot_module.manage_chat_blacklisted_user(message))
    assert service.list_chat_blacklisted_users(-100) == []

    message.text = "добавить в черный список\nОтветом: повторный спам"
    message.reply_to_message = SimpleNamespace(from_user=SimpleNamespace(
        id=11, username="other_user", full_name="Другой", is_bot=False,
    ))
    asyncio.run(bot_module.manage_chat_blacklisted_user(message))
    assert service.list_chat_blacklisted_users(-100)[0].reason == "Ответом: повторный спам"
    message.text = "удалить из чс"
    asyncio.run(bot_module.manage_chat_blacklisted_user(message))
    assert service.list_chat_blacklisted_users(-100) == []
    service.close()
