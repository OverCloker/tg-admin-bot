import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from aiogram.types import ChatPermissions

from app import bot as bot_module
from app.bot import (
    DICTIONARY_HIT_MUTE_MINUTES,
    DICTIONARY_HIT_PHOTO_PATH,
    MODERATOR_ASSIGN_COMMANDS,
    MINIAPP_ADMIN_PROFILE_LABEL,
    actor_can_manage_moderators,
    format_quiet_duration,
    handle_blacklist,
    is_miniapp_admin_user,
    moderator_can_delete_messages,
    moderator_can_unmute,
    moderator_max_mute_minutes,
    moderator_role_rank,
    parse_dictionary_hit_payload,
    parse_quiet_admin_payload,
    parse_quiet_duration,
    parse_quiet_payload,
    parse_moderator_duration,
    parse_moderator_role_payload,
)
from app.db import Database
from app.staff import STAFF_TOPIC_KEYS


def _db(tmp_path):
    service = Database(str(tmp_path / "bot.sqlite3"))
    service.init()
    service.upsert_chat(-100, "Test chat", "supergroup", None)
    service.upsert_seen_user(-100, 1, "admin", "Admin", False)
    service.upsert_seen_user(-100, 2, "helper", "Helper", False)
    service.upsert_seen_user(-100, 3, "mod", "Moderator", False)
    service.upsert_seen_user(-100, 4, "target", "Target", False)
    return service


def test_moderation_topic_is_known() -> None:
    assert "moderation" in STAFF_TOPIC_KEYS


def test_moderator_role_expires(tmp_path) -> None:
    db = _db(tmp_path)
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(timespec="seconds")
    past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(timespec="seconds")

    db.set_chat_moderator_role(-100, 2, "assistant", 1, future)
    assert db.get_chat_moderator_role(-100, 2)["role"] == "assistant"

    db.set_chat_moderator_role(-100, 2, "assistant", 1, past)
    assert db.get_chat_moderator_role(-100, 2) is None


def test_clear_all_chat_moderator_roles(tmp_path) -> None:
    db = _db(tmp_path)
    db.upsert_chat(-200, "Other chat", "supergroup", None)
    db.set_chat_moderator_role(-100, 2, "assistant", 1)
    db.set_chat_moderator_role(-200, 2, "moderator", 1)

    assert len(db.list_user_moderator_roles(2)) == 2
    assert db.clear_all_chat_moderator_roles(2) == 2
    assert db.list_user_moderator_roles(2) == []


def test_moderator_vote_replaces_previous_choice(tmp_path) -> None:
    db = _db(tmp_path)
    db.set_chat_moderator_role(-100, 2, "assistant", 1)
    db.set_chat_moderator_role(-100, 3, "moderator", 1)

    db.save_moderator_vote(-100, 4, 2, "2026-08-05")
    db.save_moderator_vote(-100, 4, 3, "2026-08-06")

    vote = db.moderator_vote_for_user(-100, 4)
    assert vote["moderator_id"] == 3
    rating = {row["user_id"]: row["votes_count"] for row in db.list_chat_moderators(-100)}
    assert rating[2] == 0
    assert rating[3] == 1


def test_miniapp_admin_profile_role_grants_chat_admin_power(tmp_path, monkeypatch) -> None:
    from app import bot as bot_module

    db = _db(tmp_path)
    db.set_miniapp_profile_role(2, MINIAPP_ADMIN_PROFILE_LABEL, 1)
    monkeypatch.setattr(bot_module, "db", db, raising=False)

    assert is_miniapp_admin_user(2) is True
    assert is_miniapp_admin_user(3) is False


@pytest.mark.anyio
async def test_only_owner_can_manage_moderator_roles(tmp_path, monkeypatch) -> None:
    from app import bot as bot_module

    db = _db(tmp_path)
    db.set_miniapp_profile_role(2, MINIAPP_ADMIN_PROFILE_LABEL, 1)
    monkeypatch.setattr(bot_module, "db", db, raising=False)
    monkeypatch.setattr(bot_module, "is_bot_admin", lambda user_id: user_id == 1)

    assert await actor_can_manage_moderators(None, -100, 1) is True
    assert await actor_can_manage_moderators(None, -100, 2) is False


def test_moderator_mute_count_uses_window(tmp_path) -> None:
    db = _db(tmp_path)
    db.add_moderator_action(-100, 2, 4, "mute", 10, "one")
    db.add_moderator_action(-100, 3, 4, "mute", 20, "two")

    assert db.count_moderator_mutes_for_target(-100, 4) == 2
    assert db.count_moderator_mutes_for_target(-100, 4, "2999-01-01T00:00:00+00:00") == 0


def test_latest_active_mute_tracks_owner_and_unmute(tmp_path) -> None:
    db = _db(tmp_path)
    db.add_moderator_action(-100, 2, 4, "mute", 10, "helper")
    active = db.latest_active_moderator_mute(-100, 4)

    assert active["moderator_id"] == 2
    assert moderator_can_unmute("assistant", 2, active) is True
    assert moderator_can_unmute("moderator", 3, active) is False
    assert moderator_can_unmute("senior", 3, active) is True

    db.add_moderator_action(-100, 3, 4, "unmute", None, "")
    assert db.latest_active_moderator_mute(-100, 4) is None


def test_moderator_payloads_and_limits() -> None:
    role, username, payload = parse_moderator_role_payload("+стМодератор @target неделя", MODERATOR_ASSIGN_COMMANDS)
    name, expires_at = parse_moderator_duration(payload)
    app_role, app_username, app_payload = parse_moderator_role_payload("+админ @target_user", MODERATOR_ASSIGN_COMMANDS)

    assert role == "senior"
    assert username == "target"
    assert name == ""
    assert expires_at is not None
    assert app_role == "app_admin"
    assert app_username == "target_user"
    assert app_payload == ""
    assert moderator_max_mute_minutes("assistant") == 10
    assert moderator_max_mute_minutes("moderator") == 30
    assert moderator_max_mute_minutes("senior") == 60
    assert moderator_can_delete_messages("assistant") is False
    assert moderator_can_delete_messages("moderator") is True
    assert moderator_can_delete_messages("senior") is True
    assert moderator_can_delete_messages("admin") is True
    assert moderator_role_rank("admin") > moderator_role_rank("senior")
    assert moderator_can_unmute("admin", 99, {"moderator_id": 2}) is True


def test_chat_lock_storage_and_expiration(tmp_path) -> None:
    db = _db(tmp_path)
    future = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(timespec="seconds")
    past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(timespec="seconds")

    db.set_chat_lock(-100, True, 1, "cleanup", future)
    assert db.get_chat_lock(-100)["reason"] == "cleanup"

    db.set_chat_lock(-100, True, 1, "expired", past)
    assert db.get_chat_lock(-100) is None

    db.set_chat_lock(-100, True, 1, "manual", None, {"can_send_messages": True})
    lock = db.get_chat_lock(-100)
    assert lock["reason"] == "manual"
    assert '"can_send_messages": true' in lock["permissions_json"]
    db.set_chat_lock(-100, False, 1)
    assert db.get_chat_lock(-100) is None


def test_blacklist_variants_storage_and_delete(tmp_path) -> None:
    db = _db(tmp_path)

    db.replace_blacklist_variants(-100, "Плохое слово", ["плохие слова", "плохое слово", "плохиш"], 1, 45)
    rules = db.list_blacklist_rules(-100)
    assert rules[0].word == "плохое слово"
    assert rules[0].mute_minutes == 45
    assert rules[0].variants == ("плохие слова", "плохиш")
    assert [variant.variant for variant in db.list_blacklist_variants(-100, "плохое слово")] == ["плохие слова", "плохиш"]

    assert db.delete_blacklist_word(-100, "плохое слово") is True
    assert db.list_blacklist_rules(-100) == []
    assert db.list_blacklist_variants(-100, "плохое слово") == []


def test_blacklist_keeps_twenty_variants(tmp_path) -> None:
    db = _db(tmp_path)

    db.replace_blacklist_variants(-100, "слово", [f"вариант {index}" for index in range(25)], 1)

    rules = db.list_blacklist_rules(-100)
    assert len(rules[0].variants) == 20
    assert rules[0].variants[-1] == "вариант 19"


@pytest.mark.anyio
async def test_blacklist_matches_word_variants(tmp_path, monkeypatch) -> None:
    from app import bot as bot_module

    db = _db(tmp_path)
    db.replace_blacklist_variants(-100, "банан", ["бананы", "банановый"], 1)
    monkeypatch.setattr(bot_module, "db", db, raising=False)
    bot_module.BLACKLIST_CACHE.clear()

    class FakeMessage:
        def __init__(self) -> None:
            self.text = "Тут банановый след"
            self.caption = None
            self.chat = type("Chat", (), {"id": -100})()
            self.deleted = False
            self.answers: list[str] = []

        async def delete(self) -> None:
            self.deleted = True

        async def answer(self, text: str) -> None:
            self.answers.append(text)

    message = FakeMessage()
    assert await handle_blacklist(message) is True
    assert message.deleted is True
    assert message.answers == ["Данные выражения запрещены в чате."]


def test_chat_stop_and_start_change_default_text_permission(tmp_path, monkeypatch) -> None:
    db = _db(tmp_path)
    permission_calls = []
    replies = []

    class FakeBot:
        async def get_chat(self, _chat_id):
            return SimpleNamespace(
                permissions=ChatPermissions(
                    can_send_messages=True,
                    can_send_photos=False,
                    can_send_voice_notes=True,
                )
            )

        async def set_chat_permissions(self, **kwargs):
            permission_calls.append(kwargs)

    message = SimpleNamespace(
        text="чат стоп",
        chat=SimpleNamespace(id=-100, type="supergroup", title="Test chat"),
        from_user=SimpleNamespace(id=1, username="admin", full_name="Admin"),
        bot=FakeBot(),
    )

    async def yes_admin(*_args):
        return True

    async def no_op(*_args, **_kwargs):
        return None

    async def reply(_message, text, *_args, **_kwargs):
        replies.append(text)

    monkeypatch.setattr(bot_module, "db", db, raising=False)
    monkeypatch.setattr(bot_module, "is_chat_admin", yes_admin)
    monkeypatch.setattr(bot_module, "remember_sender", no_op)
    monkeypatch.setattr(bot_module, "safe_reply", reply)
    monkeypatch.setattr(bot_module, "notify_staff_moderation", no_op)

    asyncio.run(bot_module.stop_chat_messages(message))
    assert permission_calls[0]["permissions"].can_send_messages is False
    assert permission_calls[0]["permissions"].can_send_photos is False
    assert permission_calls[0]["permissions"].can_send_voice_notes is True
    assert db.get_chat_lock(-100) is not None

    message.text = "чат старт"
    asyncio.run(bot_module.start_chat_messages(message))
    assert permission_calls[1]["permissions"].can_send_messages is True
    assert permission_calls[1]["permissions"].can_send_photos is False
    assert permission_calls[1]["permissions"].can_send_voice_notes is True
    assert db.get_chat_lock(-100) is None
    assert "Чат остановлен" in replies[0]
    assert "Чат снова открыт" in replies[1]
    db.close()


def test_chat_start_does_not_remove_active_alarm_media_limits(tmp_path, monkeypatch) -> None:
    db = _db(tmp_path)
    original = ChatPermissions(
        can_send_messages=True,
        can_send_photos=True,
        can_send_voice_notes=True,
    )
    db.save_alarm_permissions(-100, original.model_dump(exclude_none=True))
    calls = []

    class FakeBot:
        async def get_chat(self, _chat_id):
            return SimpleNamespace(permissions=bot_module.media_locked_permissions())

        async def set_chat_permissions(self, **kwargs):
            calls.append(kwargs["permissions"])

    message = SimpleNamespace(
        text="чат стоп",
        chat=SimpleNamespace(id=-100, type="supergroup", title="Test chat"),
        from_user=SimpleNamespace(id=1, username="admin", full_name="Admin"),
        bot=FakeBot(),
    )

    async def yes_admin(*_args):
        return True

    async def no_op(*_args, **_kwargs):
        return None

    monkeypatch.setattr(bot_module, "db", db, raising=False)
    monkeypatch.setattr(bot_module, "is_chat_admin", yes_admin)
    monkeypatch.setattr(bot_module, "remember_sender", no_op)
    monkeypatch.setattr(bot_module, "safe_reply", no_op)
    monkeypatch.setattr(bot_module, "notify_staff_moderation", no_op)

    asyncio.run(bot_module.stop_chat_messages(message))
    lock = db.get_chat_lock(-100)
    assert bot_module.saved_chat_lock_permissions(lock).can_send_photos is True

    message.text = "чат старт"
    asyncio.run(bot_module.start_chat_messages(message))
    assert calls[-1].can_send_messages is True
    assert calls[-1].can_send_photos is False
    assert bot_module.stored_permissions(db.get_alarm_settings(-100).permissions_json).can_send_photos is True
    db.close()


def test_quiet_payload_defaults_to_one_hour() -> None:
    assert parse_quiet_payload("затихни") == (None, 60, "")
    assert parse_quiet_payload("затихни - флуд") == (None, 60, "флуд")
    assert parse_quiet_payload("@target_user затихни") == ("target_user", 60, "")
    assert parse_quiet_payload("затихни @target_user") == ("target_user", 60, "")


def test_quiet_reply_by_chat_admin_applies_default_one_hour(monkeypatch) -> None:
    restricted = {}
    replies = []

    class FakeBot:
        async def restrict_chat_member(self, **kwargs):
            restricted.update(kwargs)

    class FakeDb:
        def get_quiet_settings(self, _chat_id):
            return SimpleNamespace(reply_text=None, media_type=None, media_file_id=None)

        def add_moderator_action(self, *_args):
            return None

        def count_moderator_mutes_for_target(self, *_args):
            return 0

    message = SimpleNamespace(
        text="Затихни",
        chat=SimpleNamespace(id=-100, type="supergroup"),
        from_user=SimpleNamespace(id=1, username="admin", full_name="Admin"),
        reply_to_message=SimpleNamespace(from_user=SimpleNamespace(id=4, username="target", full_name="Target")),
        bot=FakeBot(),
    )

    async def admin_role(*_args):
        return "admin"

    async def no_op(*_args, **_kwargs):
        return None

    async def target(*_args):
        return 4, "@target", None

    async def not_admin(*_args):
        return False

    async def reply(_message, text, *_args, **_kwargs):
        replies.append(text)

    monkeypatch.setattr(bot_module, "db", FakeDb(), raising=False)
    monkeypatch.setattr(bot_module, "actor_moderation_role", admin_role)
    monkeypatch.setattr(bot_module, "remember_sender", no_op)
    monkeypatch.setattr(bot_module, "resolve_command_target", target)
    monkeypatch.setattr(bot_module, "is_chat_admin", not_admin)
    monkeypatch.setattr(bot_module, "safe_reply", reply)
    monkeypatch.setattr(bot_module, "send_quiet_media", no_op)
    monkeypatch.setattr(bot_module, "notify_staff_moderation", no_op)

    before = datetime.now(timezone.utc)
    asyncio.run(bot_module.quiet_user(message))
    after = datetime.now(timezone.utc)

    assert restricted["chat_id"] == -100
    assert restricted["user_id"] == 4
    assert before + timedelta(minutes=59, seconds=59) <= restricted["until_date"]
    assert restricted["until_date"] <= after + timedelta(minutes=60, seconds=1)
    assert restricted["permissions"].can_send_messages is False
    assert "1 час" in replies[0]


def test_quiet_payload_accepts_minutes_hours_and_days() -> None:
    assert parse_quiet_payload("затихни 30м - флуд") == (None, 30, "флуд")
    assert parse_quiet_payload("затихни @target_user 2 часа") == ("target_user", 120, "")
    assert parse_quiet_payload("@target_user затихни 3д - спам") == ("target_user", 4320, "спам")
    assert parse_quiet_payload("затихни 45") == (None, 45, "")
    assert parse_quiet_duration("2ч") == 120
    assert parse_quiet_duration("3 дня") == 4320
    assert parse_quiet_duration("0м") is None
    assert parse_quiet_payload("затихни завтра") == (None, None, "")


def test_quiet_admin_payload_accepts_default_and_duration_units() -> None:
    assert parse_quiet_admin_payload("затихни админ") == (None, 60, "")
    assert parse_quiet_admin_payload("затихни админ @target_user 2ч - спор") == (
        "target_user",
        120,
        "спор",
    )
    assert parse_quiet_admin_payload("@target_user затихни админ 1 день") == (
        "target_user",
        1440,
        "",
    )


def test_quiet_duration_is_rendered_for_people() -> None:
    assert format_quiet_duration(30) == "30 минут"
    assert format_quiet_duration(60) == "1 час"
    assert format_quiet_duration(120) == "2 часа"
    assert format_quiet_duration(1440) == "1 день"
    assert format_quiet_duration(4320) == "3 дня"


def test_dictionary_hit_payload_and_asset() -> None:
    assert parse_dictionary_hit_payload("ударить словарём") is None
    assert parse_dictionary_hit_payload("ударить словарем") is None
    assert parse_dictionary_hit_payload("@target_user ударить словарём") == "target_user"
    assert parse_dictionary_hit_payload("ударить словарём быстро") == ""
    assert DICTIONARY_HIT_MUTE_MINUTES == 1
    assert DICTIONARY_HIT_PHOTO_PATH.exists()
