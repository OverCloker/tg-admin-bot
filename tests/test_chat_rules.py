from datetime import datetime, timedelta, timezone

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
        saved = db.set_chat_rules_settings(-100, "1. Уважайте друг друга", True, 60, 42)
        assert saved.rules_text == "1. Уважайте друг друга"
        assert saved.enabled == 1
        assert saved.interval_minutes == 60
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
    assert keyboard.inline_keyboard[1][0].text == "Обязательно к прочтению"
    assert "startapp=rules_n100" in keyboard.inline_keyboard[0][0].url
