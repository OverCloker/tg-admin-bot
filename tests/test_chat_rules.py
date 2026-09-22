import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import bot, miniapp
from app.db import Database
from app.miniapp import MiniAppRulesSave
from app.miniapp_ui import MINI_APP_HTML


def prepared_db(tmp_path):
    path = tmp_path / "rules.sqlite3"
    db = Database(str(path))
    db.init()
    db.upsert_chat(-100, "Чат правил", "supergroup", None)
    db.upsert_seen_user(-100, 9, "reader", "Reader", False)
    return path, db


def test_chat_rules_storage_and_due_timer(tmp_path) -> None:
    _, db = prepared_db(tmp_path)
    try:
        saved = db.set_chat_rules_settings(-100, "1. Уважайте друг друга", True, 60, True, 42)
        assert saved.rules_text == "1. Уважайте друг друга"
        assert saved.enabled == 1
        assert saved.interval_minutes == 60
        assert saved.require_agreement == 1
        assert bot.chat_rules_due(saved, datetime.now(timezone.utc)) is False

        old = (datetime.now(timezone.utc) - timedelta(minutes=61)).isoformat(timespec="seconds")
        db.mark_chat_rules_sent(-100, old)
        assert bot.chat_rules_due(db.get_chat_rules_settings(-100), datetime.now(timezone.utc)) is True
        assert [item.chat_id for item in db.list_enabled_chat_rules()] == [-100]
    finally:
        db.close()


def test_rules_admin_is_scoped_and_public_page_uses_saved_text(tmp_path, monkeypatch) -> None:
    path, db = prepared_db(tmp_path)
    db.replace_chat_telegram_admins(
        -100,
        [{"user_id": 9, "username": "reader", "full_name": "Reader", "status": "administrator", "is_bot": False}],
    )
    db.close()
    monkeypatch.setenv("OWNER_ID", "42")
    monkeypatch.setattr(miniapp, "_db", lambda: Database(str(path)))
    monkeypatch.setattr(miniapp, "_telegram_user", lambda _data: {"id": 9})

    result = miniapp.miniapp_profile_rules_save(
        MiniAppRulesSave(chatId=-100, rulesText="Не оскорблять участников.", automaticEnabled=True, intervalMinutes=60),
        x_telegram_init_data="test",
    )
    assert result["ok"] is True
    admin = miniapp.miniapp_profile_rules(chat_id=-100, x_telegram_init_data="test")
    public = miniapp.miniapp_rules(chat_id=-100, x_telegram_init_data="test")
    assert admin["rules"]["automaticEnabled"] is True
    assert admin["rules"]["requireAgreement"] is True
    assert public["rulesText"] == "Не оскорблять участников."


def test_non_admin_cannot_change_rules(tmp_path, monkeypatch) -> None:
    path, db = prepared_db(tmp_path)
    db.close()
    monkeypatch.setenv("OWNER_ID", "42")
    monkeypatch.setattr(miniapp, "_db", lambda: Database(str(path)))
    monkeypatch.setattr(miniapp, "_telegram_user", lambda _data: {"id": 9})
    with pytest.raises(Exception) as exc_info:
        miniapp.miniapp_profile_rules_save(
            MiniAppRulesSave(chatId=-100, rulesText="Текст", automaticEnabled=False, intervalMinutes=60),
            x_telegram_init_data="test",
        )
    assert getattr(exc_info.value, "status_code", None) == 403


def test_rules_ui_and_chat_keyboard() -> None:
    rules_button = MINI_APP_HTML.index('<strong>Правила</strong>')
    weather_button = MINI_APP_HTML.index('onclick="showWeather()">Погода</button>')
    radio_button = MINI_APP_HTML.index('onclick="showRadio()">Радио</button>')
    assert rules_button < weather_button < radio_button
    assert 'api("/miniapp/profile/rules"' in MINI_APP_HTML
    assert 'normalized.startsWith("rules_")' in MINI_APP_HTML
    keyboard = bot.rules_keyboard(-100)
    assert keyboard.inline_keyboard[0][0].text == "📜 Правила чата"
    assert len(keyboard.inline_keyboard) == 1
    assert "startapp=rules_n100" in keyboard.inline_keyboard[0][0].url


def test_rules_prompt_has_text_and_one_button() -> None:
    telegram_bot = AsyncMock()
    asyncio.run(bot.send_chat_rules_prompt(telegram_bot, -100))
    telegram_bot.send_message.assert_awaited_once()
    args, kwargs = telegram_bot.send_message.await_args
    assert args[:2] == (-100, "<b>Обязательно к прочтению</b>")
    assert len(kwargs["reply_markup"].inline_keyboard) == 1


def test_rules_agreement_storage(tmp_path) -> None:
    _, db = prepared_db(tmp_path)
    try:
        db.begin_chat_rule_agreement(-100, 9, restricted=True)
        pending = db.get_chat_rule_agreement(-100, 9)
        assert pending["restricted"] == 1
        assert pending["agreed_at"] is None
        db.set_chat_rule_prompt_message(-100, 9, 555)
        assert db.get_chat_rule_agreement(-100, 9)["prompt_message_id"] == 555
        assert db.complete_chat_rule_agreement(-100, 9) is True
        assert db.get_chat_rule_agreement(-100, 9)["agreed_at"]
        assert db.complete_chat_rule_agreement(-100, 9) is False
    finally:
        db.close()


def test_agreement_keyboard_is_personal_and_green() -> None:
    keyboard = bot.rules_agreement_keyboard(-100, 9)
    assert keyboard.inline_keyboard[0][0].text == "📜 Правила чата"
    agree = keyboard.inline_keyboard[1][0]
    assert agree.text == "✅ Прочитал и согласен"
    assert agree.callback_data == "rules:agree:-100:9"
    assert agree.style == "success"


def test_new_member_is_restricted_until_rules_are_accepted(tmp_path, monkeypatch) -> None:
    _, database = prepared_db(tmp_path)
    database.set_chat_rules_settings(-100, "Правила", False, 60, True, 42)
    telegram_bot = SimpleNamespace(
        restrict_chat_member=AsyncMock(),
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=777)),
    )
    event = SimpleNamespace(
        chat=SimpleNamespace(id=-100, title="Чат правил", type="supergroup", username=None),
        old_chat_member=SimpleNamespace(status="left", is_member=False),
        new_chat_member=SimpleNamespace(
            status="member",
            user=SimpleNamespace(id=10, username="new_user", full_name="Новый участник", is_bot=False),
        ),
        bot=telegram_bot,
    )
    monkeypatch.setattr(bot, "db", database, raising=False)
    asyncio.run(bot.participant_membership_changed(event))

    telegram_bot.restrict_chat_member.assert_awaited_once()
    permissions = telegram_bot.restrict_chat_member.await_args.kwargs["permissions"]
    assert permissions.can_send_messages is False
    assert permissions.can_send_photos is False
    prompt = telegram_bot.send_message.await_args
    assert "прочитай правила" in prompt.args[1]
    assert prompt.kwargs["reply_markup"].inline_keyboard[1][0].style == "success"
    agreement = database.get_chat_rule_agreement(-100, 10)
    assert agreement["prompt_message_id"] == 777
    assert agreement["agreed_at"] is None
    database.close()


def test_only_target_user_can_accept_and_restore_permissions(tmp_path, monkeypatch) -> None:
    _, database = prepared_db(tmp_path)
    database.set_chat_rules_settings(-100, "Правила", False, 60, True, 42)
    database.begin_chat_rule_agreement(-100, 9, restricted=True, prompt_message_id=777)
    chat_permissions = bot.default_open_permissions()
    telegram_bot = SimpleNamespace(
        get_chat=AsyncMock(return_value=SimpleNamespace(permissions=chat_permissions)),
        restrict_chat_member=AsyncMock(),
    )
    message = SimpleNamespace(edit_text=AsyncMock())
    callback = SimpleNamespace(
        data="rules:agree:-100:9",
        from_user=SimpleNamespace(id=9, full_name="Reader"),
        bot=telegram_bot,
        message=message,
        answer=AsyncMock(),
    )
    monkeypatch.setattr(bot, "db", database, raising=False)
    asyncio.run(bot.accept_rules_callback(callback))

    telegram_bot.restrict_chat_member.assert_awaited_once()
    restored = telegram_bot.restrict_chat_member.await_args.kwargs["permissions"]
    assert restored.can_send_messages is True
    assert database.get_chat_rule_agreement(-100, 9)["agreed_at"]
    acceptance = database.get_chat_rules_acceptance(-100, 9)
    assert acceptance["rules_updated_at"] == database.get_chat_rules_settings(-100).updated_at
    message.edit_text.assert_awaited_once()
    database.close()


def test_other_user_cannot_accept_rules_button(tmp_path, monkeypatch) -> None:
    _, database = prepared_db(tmp_path)
    database.begin_chat_rule_agreement(-100, 9, restricted=True)
    callback = SimpleNamespace(
        data="rules:agree:-100:9",
        from_user=SimpleNamespace(id=10, full_name="Other"),
        answer=AsyncMock(),
    )
    monkeypatch.setattr(bot, "db", database, raising=False)
    asyncio.run(bot.accept_rules_callback(callback))
    assert database.get_chat_rule_agreement(-100, 9)["agreed_at"] is None
    assert callback.answer.await_args.kwargs["show_alert"] is True
    database.close()
