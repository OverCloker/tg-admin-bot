import asyncio
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers

from app import bot, miniapp
from app.db import Database
from app.macros import parse_macro_action, validate_macro_phrase
from app.miniapp import MiniAppMacroDelete, MiniAppMacroSave
from app.miniapp_ui import MINI_APP_HTML


def test_macro_action_language() -> None:
    quiet = parse_macro_action("затихни 313842282 30м - флуд")
    assert (quiet.kind, quiet.target, quiet.duration, quiet.reason) == ("quiet", "313842282", "30м", "флуд")
    assert parse_macro_action("сообщение: Привет").text == "Привет"
    assert parse_macro_action("", has_media=True).kind == "media"
    batch = parse_macro_action("затихни 10 - флуд\n@user_one\n313842282\n@user_three")
    assert (batch.kind, batch.targets, batch.duration, batch.reason) == (
        "quiet", ("@user_one", "313842282", "@user_three"), "10", "флуд",
    )
    assert parse_macro_action("затихни\n@user_one").duration == "1ч"
    assert validate_macro_phrase("  Вика  тихо ") == "вика тихо"
    with pytest.raises(ValueError):
        parse_macro_action("затихни @bad 30м")
    with pytest.raises(ValueError):
        parse_macro_action("затихни 9223372036854775808 30м")
    with pytest.raises(ValueError):
        parse_macro_action("/shell rm -rf /tmp")
    with pytest.raises(ValueError):
        parse_macro_action("затихни 10 - флуд\n" + "\n".join(f"@user_{i:02d}" for i in range(11)))
    with pytest.raises(ValueError):
        parse_macro_action("затихни 10\n@user_one\n@USER_ONE")
    with pytest.raises(ValueError):
        parse_macro_action("затихни 10\n@bad")
    with pytest.raises(ValueError):
        parse_macro_action("затихни 10\n9223372036854775808")


def test_macro_editor_uses_full_group_picker_and_styled_switch() -> None:
    assert 'class="rules-chat-picker" for="macroChatSelect"' in MINI_APP_HTML
    assert 'class="macro-selected-chat"' in MINI_APP_HTML
    assert 'class="switch" aria-label="Включить макрос"' in MINI_APP_HTML
    assert '<span class="slider round"></span>' in MINI_APP_HTML
    assert 'id="macroTargetId"' in MINI_APP_HTML
    assert 'onclick="insertMacroTargetId()"' in MINI_APP_HTML
    assert 'затихни 123456789 30м - причина' in MINI_APP_HTML
    assert 'затихни 10 - причина&#10;@username1' in MINI_APP_HTML
    assert 'от 1 до 10 @ников' in MINI_APP_HTML


def test_macro_save_list_rename_and_delete(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OWNER_ID", "42")
    path = tmp_path / "bot.sqlite3"
    db = Database(str(path))
    db.init()
    db.upsert_chat(-100, "Группа", "supergroup", None)
    db.close()
    monkeypatch.setattr(miniapp, "_telegram_user", lambda _: {"id": 42})
    monkeypatch.setattr(miniapp, "_db", lambda: Database(str(path)))

    saved = miniapp.miniapp_profile_macro_save(
        MiniAppMacroSave(chatId=-100, phrase="Вика тихо", action="затихни 313842282 30м", mediaType="photo", mediaFileId="telegram-file"),
        x_telegram_init_data="test",
    )
    assert saved["macro"]["phrase"] == "вика тихо"
    assert miniapp.miniapp_profile_macros(chat_id=-100, x_telegram_init_data="test")["macros"][0]["mediaType"] == "photo"
    miniapp.miniapp_profile_macro_save(
        MiniAppMacroSave(chatId=-100, phrase="Вика спать", originalPhrase="Вика тихо", action="сообщение: пора спать", enabled=False),
        x_telegram_init_data="test",
    )
    items = miniapp.miniapp_profile_macros(chat_id=-100, x_telegram_init_data="test")["macros"]
    assert [(item["phrase"], item["enabled"]) for item in items] == [("вика спать", False)]
    with pytest.raises(HTTPException) as exc:
        miniapp.miniapp_profile_macro_save(MiniAppMacroSave(chatId=-200, phrase="другая", action="сообщение: нет"), x_telegram_init_data="test")
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        miniapp.miniapp_profile_macro_save(
            MiniAppMacroSave(chatId=-100, phrase="слишком много", action="затихни 10\n" + "\n".join(f"@user_{i:02d}" for i in range(11))),
            x_telegram_init_data="test",
        )
    assert exc.value.status_code == 400
    assert miniapp.miniapp_profile_macro_delete(MiniAppMacroDelete(chatId=-100, phrase="вика спать"), x_telegram_init_data="test")["deleted"]


def test_macro_quiet_rechecks_roles_and_sends_media(tmp_path, monkeypatch) -> None:
    path = tmp_path / "bot.sqlite3"
    db = Database(str(path))
    db.init()
    db.upsert_chat(-100, "Группа", "supergroup", None)
    db.save_chat_macro(-100, "вика тихо", "затихни 7 30м", 42, "animation", "file-id")
    monkeypatch.setattr(bot, "db", db, raising=False)
    calls = []

    class FakeBot:
        async def restrict_chat_member(self, **kwargs):
            calls.append(("mute", kwargs))

    async def role(*_args):
        return "admin"

    async def target(*_args):
        return 7, "Вика", None

    async def not_admin(*_args):
        return False

    async def record_reply(_message, value, **_kwargs):
        calls.append(("reply", value))

    async def record_media(_message, item):
        calls.append(("media", item.media_file_id))

    async def notify(*_args):
        return None

    monkeypatch.setattr(bot, "actor_moderation_role", role)
    monkeypatch.setattr(bot, "resolve_quiet_panel_target", target)
    monkeypatch.setattr(bot, "is_chat_admin", not_admin)
    monkeypatch.setattr(bot, "safe_reply", record_reply)
    monkeypatch.setattr(bot, "send_auto_reply_item", record_media)
    monkeypatch.setattr(bot, "notify_staff_moderation", notify)
    message = SimpleNamespace(text="Вика тихо", chat=SimpleNamespace(id=-100), from_user=SimpleNamespace(id=42, username=None, full_name="Админ"), bot=FakeBot())
    try:
        assert asyncio.run(bot.handle_chat_macro(message)) is True
        assert [name for name, *_ in calls] == ["mute", "reply", "media"]
        assert calls[0][1]["user_id"] == 7
        assert db.count_moderator_mutes_for_target(-100, 7, "2000-01-01T00:00:00+00:00") == 1
    finally:
        db.close()


def test_macro_does_not_execute_after_role_is_revoked(tmp_path, monkeypatch) -> None:
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()
    db.upsert_chat(-100, "Группа", "supergroup", None)
    db.save_chat_macro(-100, "тихо", "затихни 7 30м", 42)
    monkeypatch.setattr(bot, "db", db, raising=False)

    async def no_role(*_args):
        return None

    class FakeBot:
        async def restrict_chat_member(self, **_kwargs):
            raise AssertionError("The revoked user must not execute the macro")

    monkeypatch.setattr(bot, "actor_moderation_role", no_role)
    message = SimpleNamespace(text="тихо", chat=SimpleNamespace(id=-100), from_user=SimpleNamespace(id=9), bot=FakeBot())
    try:
        assert asyncio.run(bot.handle_chat_macro(message)) is True
    finally:
        db.close()


def test_batch_macro_mutes_multiple_targets_with_one_result(tmp_path, monkeypatch) -> None:
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()
    db.upsert_chat(-100, "Группа", "supergroup", None)
    db.save_chat_macro(-100, "всем тихо", "затихни 10 - флуд\n@user_one\n22\n@user_admin\n@user_missing", 42)
    monkeypatch.setattr(bot, "db", db, raising=False)
    calls = []

    class FakeBot:
        async def restrict_chat_member(self, **kwargs):
            calls.append(("mute", kwargs))

    async def role(*_args):
        return "admin"

    async def target(_bot, _chat_id, value):
        data = {
            "@user_one": (11, "@user_one", None),
            "22": (22, "Участник без ника", None),
            "@user_admin": (33, "@user_admin", None),
            "@user_missing": (None, None, "Не найден"),
        }
        return data[value]

    async def is_admin(_bot, _chat_id, user_id):
        return user_id == 33

    async def record_reply(_message, value, **_kwargs):
        calls.append(("reply", value))

    async def notify(*_args):
        return None

    monkeypatch.setattr(bot, "actor_moderation_role", role)
    monkeypatch.setattr(bot, "resolve_quiet_panel_target", target)
    monkeypatch.setattr(bot, "is_chat_admin", is_admin)
    monkeypatch.setattr(bot, "safe_reply", record_reply)
    monkeypatch.setattr(bot, "notify_staff_moderation", notify)
    message = SimpleNamespace(text="всем тихо", chat=SimpleNamespace(id=-100), from_user=SimpleNamespace(id=42, username=None, full_name="Админ"), bot=FakeBot())
    try:
        assert asyncio.run(bot.handle_chat_macro(message)) is True
        assert [name for name, *_ in calls] == ["mute", "mute", "reply"]
        assert [call[1]["user_id"] for call in calls[:2]] == [11, 22]
        reply = calls[-1][1]
        assert "@user_one" in reply and "Участник без ника" in reply
        assert "@user_admin — администратор" in reply and "@user_missing — не найден" in reply
        assert "Причина: флуд" in reply
        assert db.count_moderator_mutes_for_target(-100, 11, "2000-01-01T00:00:00+00:00") == 1
        assert db.count_moderator_mutes_for_target(-100, 22, "2000-01-01T00:00:00+00:00") == 1
    finally:
        db.close()


def test_batch_macro_with_media_sends_one_captioned_message(tmp_path, monkeypatch) -> None:
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()
    db.upsert_chat(-100, "Группа", "supergroup", None)
    db.save_chat_macro(-100, "всем тихо", "затихни 10 - флуд\n@user_one\n@user_two", 42, "animation", "file-id")
    monkeypatch.setattr(bot, "db", db, raising=False)
    calls = []

    class FakeBot:
        async def restrict_chat_member(self, **kwargs):
            calls.append(("mute", kwargs["user_id"]))

    async def role(*_args):
        return "admin"

    async def target(_bot, _chat_id, value):
        return (11 if value == "@user_one" else 22), value, None

    async def not_admin(*_args):
        return False

    async def media(_message, item):
        calls.append(("media", item.text, item.media_file_id))

    async def unexpected_reply(*_args, **_kwargs):
        raise AssertionError("A batch macro with media should send one captioned message")

    async def notify(*_args):
        return None

    monkeypatch.setattr(bot, "actor_moderation_role", role)
    monkeypatch.setattr(bot, "resolve_quiet_panel_target", target)
    monkeypatch.setattr(bot, "is_chat_admin", not_admin)
    monkeypatch.setattr(bot, "safe_reply", unexpected_reply)
    monkeypatch.setattr(bot, "send_auto_reply_item", media)
    monkeypatch.setattr(bot, "notify_staff_moderation", notify)
    message = SimpleNamespace(text="всем тихо", chat=SimpleNamespace(id=-100), from_user=SimpleNamespace(id=42, username=None, full_name="Админ"), bot=FakeBot())
    try:
        assert asyncio.run(bot.handle_chat_macro(message)) is True
        assert [name for name, *_ in calls] == ["mute", "mute", "media"]
        assert "@user_one" in calls[-1][1] and "@user_two" in calls[-1][1]
        assert calls[-1][2] == "file-id"
    finally:
        db.close()


def test_macro_media_upload_skips_short_trigger_limit(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OWNER_ID", "42")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "bot.sqlite3"))
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()
    db.close()
    monkeypatch.setattr(miniapp, "_telegram_user", lambda _: {"id": 42})
    monkeypatch.setattr(miniapp, "_db", lambda: Database(str(tmp_path / "bot.sqlite3")))

    async def impossible_duration(_path):
        raise AssertionError("Macro audio must not use the 30-second trigger limit")

    async def saved(_user, _kind, _path, _filename=None):
        return "audio", "telegram-file-id"

    monkeypatch.setattr(miniapp, "_media_duration_seconds", impossible_duration)
    monkeypatch.setattr(miniapp, "_store_trigger_media_in_telegram", saved)
    file = miniapp.UploadFile(BytesIO(b"audio"), filename="song.mp3", headers=Headers({"content-type": "audio/mpeg"}))
    result = asyncio.run(miniapp.miniapp_profile_macro_media_upload("audio", file, "test"))
    assert result["mediaFileId"] == "telegram-file-id"
