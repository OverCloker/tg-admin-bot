from datetime import datetime, timedelta, timezone

from app.bot import (
    DICTIONARY_HIT_MUTE_MINUTES,
    DICTIONARY_HIT_PHOTO_PATH,
    MODERATOR_ASSIGN_COMMANDS,
    MINIAPP_ADMIN_PROFILE_LABEL,
    is_miniapp_admin_user,
    moderator_can_delete_messages,
    moderator_can_stop_chat,
    moderator_can_unmute,
    moderator_max_mute_minutes,
    moderator_role_rank,
    parse_chat_stop_payload,
    parse_dictionary_hit_payload,
    parse_duration_seconds_token,
    parse_moderator_duration,
    parse_moderator_role_payload,
    parse_slow_mode_payload,
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
    assert moderator_can_stop_chat("assistant", 60) is False
    assert moderator_can_stop_chat("moderator", 600) is True
    assert moderator_can_stop_chat("moderator", 601) is False
    assert moderator_can_stop_chat("moderator", None) is False
    assert moderator_can_stop_chat("senior", 1800) is True
    assert moderator_can_stop_chat("senior", 1801) is False
    assert moderator_can_stop_chat("admin", None) is True
    assert moderator_can_stop_chat("admin", 24 * 60 * 60) is True
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

    db.set_chat_lock(-100, True, 1, "manual", None)
    assert db.get_chat_lock(-100)["reason"] == "manual"
    db.set_chat_lock(-100, False, 1)
    assert db.get_chat_lock(-100) is None


def test_chat_control_payloads() -> None:
    assert parse_duration_seconds_token("30с") == 30
    assert parse_duration_seconds_token("5м") == 300
    assert parse_duration_seconds_token("1ч") == 3600
    assert parse_chat_stop_payload("чат стоп 5м зачистка") == (300, "зачистка")
    assert parse_chat_stop_payload("чат стоп без флуда") == (None, "без флуда")
    assert parse_slow_mode_payload("медленно 30с") == 30
    assert parse_slow_mode_payload("медленно 5м") == 300
    assert parse_slow_mode_payload("медленно выкл") == 0


def test_dictionary_hit_payload_and_asset() -> None:
    assert parse_dictionary_hit_payload("ударить словарём") is None
    assert parse_dictionary_hit_payload("ударить словарем") is None
    assert parse_dictionary_hit_payload("@target_user ударить словарём") == "target_user"
    assert parse_dictionary_hit_payload("ударить словарём быстро") == ""
    assert DICTIONARY_HIT_MUTE_MINUTES == 1
    assert DICTIONARY_HIT_PHOTO_PATH.exists()
