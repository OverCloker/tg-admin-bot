import asyncio
import sqlite3
from types import SimpleNamespace

from app import bot as bot_module
from app.db import Database


def test_personal_blacklist_listing_is_only_triggered_by_notepad_command() -> None:
    assert bot_module.CHAT_USER_NOTE_COMMAND_RE.fullmatch("блокнот")
    assert bot_module.CHAT_USER_NOTE_COMMAND_RE.fullmatch("/блокнот")
    assert bot_module.CHAT_USER_NOTE_COMMAND_RE.fullmatch("Блокнот!")
    assert not bot_module.CHAT_USER_NOTE_COMMAND_RE.fullmatch("черный список")
    assert not bot_module.CHAT_USER_NOTE_COMMAND_RE.fullmatch("чёрный список")


def test_chat_user_blacklist_is_separate_per_chat_and_owner(tmp_path) -> None:
    path = tmp_path / "bot.sqlite3"
    service = Database(str(path))
    service.init()
    service.upsert_chat(-100, "First", "supergroup", None)
    service.upsert_chat(-200, "Second", "supergroup", None)
    service.add_blacklist_word(-100, "spam", 1)
    service.save_chat_blacklisted_user(-100, 1, 9, "Vika", "Вика", "первое нарушение")
    service.save_chat_blacklisted_user(-200, 1, 9, "Vika", "Вика", "другая группа")
    service.save_chat_blacklisted_user(-100, 2, 9, "Vika", "Вика", "личная заметка")
    service.save_chat_blacklisted_user(-100, 1, 9, "new_vika", "Вика", "повторное нарушение")

    first = service.list_chat_blacklisted_users(-100, 1)
    assert len(first) == 1
    assert (first[0].user_id, first[0].username, first[0].reason) == (9, "new_vika", "повторное нарушение")
    assert service.get_chat_blacklisted_user_by_username(-100, 1, "@NEW_VIKA") == first[0]
    assert service.get_chat_blacklisted_user(-100, 1, 9) == first[0]
    assert service.get_chat_blacklisted_user(-100, 1, 99) is None
    assert service.get_chat_blacklisted_user_by_username(-100, 1, "@Vika") is None
    assert service.delete_chat_blacklisted_user(-100, 1, 9) is True
    assert service.delete_chat_blacklisted_user(-100, 1, 9) is False
    assert service.get_chat_blacklisted_user(-100, 2, 9).reason == "личная заметка"
    assert len(service.list_chat_blacklisted_users(-200, 1)) == 1
    assert [word.word for word in service.list_blacklist_words(-100)] == ["spam"]
    service.close()

    reopened = Database(str(path))
    reopened.init()
    assert len(reopened.list_chat_blacklisted_users(-200, 1)) == 1
    reopened.close()


def test_existing_group_blacklist_migrates_to_editor_personal_list(tmp_path) -> None:
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "create table chats (chat_id integer primary key, title text not null, "
            "type text not null, username text, updated_at text not null)"
        )
        connection.execute("insert into chats values (-100, 'Chat', 'supergroup', null, 'old')")
        connection.execute(
            """create table chat_blacklisted_users (
                chat_id integer not null, user_id integer not null, username text,
                full_name text not null, reason text not null default '', added_by integer,
                created_at text not null, updated_at text not null,
                primary key (chat_id, user_id),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            )"""
        )
        connection.execute(
            "insert into chat_blacklisted_users values (-100, 9, null, 'Вика', 'спам', 7, 'old', 'old')"
        )
        connection.execute(
            "create index idx_chat_blacklisted_users_chat_time "
            "on chat_blacklisted_users(chat_id, created_at, user_id)"
        )
    service = Database(str(path))
    service.init()
    assert service.get_chat_blacklisted_user(-100, 7, 9).reason == "спам"
    assert service.list_chat_blacklisted_users(-100, 8) == []
    assert service._conn.execute("pragma foreign_key_check").fetchall() == []
    service.init()
    assert len(service.list_chat_blacklisted_users(-100, 7)) == 1
    service.close()


def test_chat_user_blacklist_parses_reply_and_username_forms() -> None:
    parse = bot_module.parse_chat_blacklist_action
    assert parse("добавить в черный список\nСпам и оскорбления") == ("add", None, "Спам и оскорбления")
    assert parse("@vika123 в чс\nзаметка о пользователе") == ("add", "@vika123", "заметка о пользователе")
    assert parse("добавить в чс @vika123 - причина") == ("add", "@vika123", "причина")
    assert parse("удалить из чс") == ("remove", None, "")
    assert parse("@vika123 из чс") == ("remove", "@vika123", "")
    assert parse("удалить из черного списка @vika123") == ("remove", "@vika123", "")
    assert parse("123456789 в чс\nзаметка") == ("add", "123456789", "заметка")
    assert parse("добавить в чс 123456789\nзаметка") == ("add", "123456789", "заметка")
    assert parse("123456789 из чс") == ("remove", "123456789", "")
    assert parse("удалить из чс 123456789") == ("remove", "123456789", "")
    assert parse("удалить из чс\nнеожиданный текст") is None
    assert parse("") is None


def test_chat_user_blacklist_handlers_are_personal_and_escape_reason(tmp_path, monkeypatch) -> None:
    service = Database(str(tmp_path / "bot.sqlite3"))
    service.init()
    service.upsert_chat(-100, "Chat", "supergroup", None)
    service.upsert_seen_user(-100, 9, "vika123", "Вика", False)
    replies: list[str] = []

    async def remember(*_args):
        return None

    async def reply(_message, text, **_kwargs):
        replies.append(text)

    async def reply_chunks(_message, lines, **_kwargs):
        replies.append("\n".join(lines))

    monkeypatch.setattr(bot_module, "db", service, raising=False)
    monkeypatch.setattr(bot_module, "remember_sender", remember)
    monkeypatch.setattr(bot_module, "safe_reply", reply)
    monkeypatch.setattr(bot_module, "safe_reply_chunks", reply_chunks)
    message = SimpleNamespace(
        text="@vika123 в чс\nСпам <script>",
        chat=SimpleNamespace(id=-100, type="supergroup"),
        from_user=SimpleNamespace(id=7, username="editor7", full_name="Редактор"),
        reply_to_message=None,
        bot=SimpleNamespace(),
    )

    asyncio.run(bot_module.manage_chat_blacklisted_user(message))
    assert service.list_chat_blacklisted_users(-100, 7)[0].reason == "Спам <script>"
    assert "&lt;script&gt;" in replies[-1]
    message.text = "блокнот"
    asyncio.run(bot_module.list_chat_blacklisted_users(message))
    assert "Блокнот @editor7" in replies[-1]
    assert "1. @vika123 — Спам &lt;script&gt;" in replies[-1]

    message.from_user = SimpleNamespace(id=8, username=None, full_name="Сосед")
    asyncio.run(bot_module.list_chat_blacklisted_users(message))
    assert "Блокнот Сосед в этой группе пуст" in replies[-1]
    message.text = "@vika123 из чс"
    asyncio.run(bot_module.manage_chat_blacklisted_user(message))
    assert len(service.list_chat_blacklisted_users(-100, 7)) == 1
    assert "в чёрном списке нет" in replies[-1]
    message.text = "@vika123 в чс\nсвоя причина"
    asyncio.run(bot_module.manage_chat_blacklisted_user(message))
    assert service.get_chat_blacklisted_user(-100, 8, 9).reason == "своя причина"
    assert service.get_chat_blacklisted_user(-100, 7, 9).reason == "Спам <script>"

    message.from_user = SimpleNamespace(id=7, username="editor7", full_name="Редактор")
    message.text = "@vika123 из чс"
    asyncio.run(bot_module.manage_chat_blacklisted_user(message))
    assert service.list_chat_blacklisted_users(-100, 7) == []

    message.text = "добавить в черный список\nОтветом: повторный спам"
    message.reply_to_message = SimpleNamespace(from_user=SimpleNamespace(
        id=11, username="other_user", full_name="Другой", is_bot=False,
    ))
    asyncio.run(bot_module.manage_chat_blacklisted_user(message))
    assert service.list_chat_blacklisted_users(-100, 7)[0].reason == "Ответом: повторный спам"
    message.text = "удалить из чс"
    asyncio.run(bot_module.manage_chat_blacklisted_user(message))
    assert service.list_chat_blacklisted_users(-100, 7) == []
    service.close()


def test_chat_user_blacklist_numeric_id_without_username(tmp_path, monkeypatch) -> None:
    service = Database(str(tmp_path / "bot.sqlite3"))
    service.init()
    service.upsert_chat(-100, "Chat", "supergroup", None)
    replies: list[str] = []

    async def remember(*_args):
        return None

    async def reply(_message, text, **_kwargs):
        replies.append(text)

    async def reply_chunks(_message, lines, **_kwargs):
        replies.append("\n".join(lines))

    class FakeBot:
        async def get_chat_member(self, _chat_id, user_id):
            assert user_id == 123456789
            return SimpleNamespace(user=SimpleNamespace(
                id=user_id, username=None, full_name="Вика", is_bot=False,
            ))

    monkeypatch.setattr(bot_module, "db", service, raising=False)
    monkeypatch.setattr(bot_module, "remember_sender", remember)
    monkeypatch.setattr(bot_module, "safe_reply", reply)
    monkeypatch.setattr(bot_module, "safe_reply_chunks", reply_chunks)
    message = SimpleNamespace(
        text="123456789 в чс\nспам", chat=SimpleNamespace(id=-100, type="supergroup"),
        from_user=SimpleNamespace(id=7, username=None, full_name="Участник"),
        reply_to_message=None, bot=FakeBot(),
    )
    asyncio.run(bot_module.manage_chat_blacklisted_user(message))
    assert service.get_chat_blacklisted_user(-100, 7, 123456789).full_name == "Вика"
    message.text = "блокнот"
    asyncio.run(bot_module.list_chat_blacklisted_users(message))
    assert "Вика (ID 123456789) — спам" in replies[-1]
    message.text = "123456789 из чс"
    asyncio.run(bot_module.manage_chat_blacklisted_user(message))
    assert service.get_chat_blacklisted_user(-100, 7, 123456789) is None
    assert "Вика удалён" in replies[-1]
    service.close()
