from datetime import datetime, timedelta, timezone

from app import miniapp
from app.admin_api import should_skip_api_audit
from app.db import Database
from app.miniapp import PersonalReminderCreate, PersonalReminderDelete, PersonalWeatherSave
from app.miniapp_ui import MINI_APP_HTML


def test_personal_reminder_claim_is_idempotent(tmp_path) -> None:
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()
    due = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec="seconds")
    reminder = db.create_personal_reminder(42, "Проверить чайник", due)

    first = db.claim_due_personal_reminders(datetime.now(timezone.utc).isoformat(timespec="seconds"))
    second = db.claim_due_personal_reminders(datetime.now(timezone.utc).isoformat(timespec="seconds"))

    assert [item.id for item in first] == [reminder.id]
    assert second == []
    db.finish_personal_reminder(reminder.id)
    assert db.list_personal_reminders(42) == []
    db.close()


def test_personal_weather_settings_persist(tmp_path) -> None:
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()
    db.set_personal_weather_settings(42, "Кривой Рог", -180, True, 8, 15, True, 21, 5)

    settings = db.get_personal_weather_settings(42)
    assert settings.city == "Кривой Рог"
    assert (settings.daily_hour, settings.daily_minute) == (8, 15)
    assert (settings.tomorrow_hour, settings.tomorrow_minute) == (21, 5)
    assert len(db.list_enabled_personal_weather()) == 1

    db.disable_personal_weather(42)
    assert db.list_enabled_personal_weather() == []
    db.close()


def test_miniapp_reminder_create_and_delete(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "bot.sqlite3"
    db = Database(str(db_path))
    db.init()
    db.close()
    monkeypatch.setattr(miniapp, "_telegram_user", lambda _data: {"id": 42})
    monkeypatch.setattr(miniapp, "_db", lambda: Database(str(db_path)))
    local_future = (datetime.now() + timedelta(hours=2)).replace(second=0, microsecond=0)

    created = miniapp.miniapp_reminder_create(
        PersonalReminderCreate(
            text="Купить корм",
            remindAt=local_future.isoformat(timespec="minutes"),
            timezoneOffsetMinutes=0,
        ),
        x_telegram_init_data="test",
    )
    assert created["reminders"][0]["text"] == "Купить корм"

    deleted = miniapp.miniapp_reminder_delete(
        PersonalReminderDelete(reminderId=created["reminders"][0]["id"]),
        x_telegram_init_data="test",
    )
    assert deleted["reminders"] == []


def test_miniapp_personal_weather_endpoint(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "bot.sqlite3"
    db = Database(str(db_path))
    db.init()
    db.close()
    monkeypatch.setattr(miniapp, "_telegram_user", lambda _data: {"id": 42})
    monkeypatch.setattr(miniapp, "_db", lambda: Database(str(db_path)))

    result = miniapp.miniapp_personal_weather_save(
        PersonalWeatherSave(
            city="Кривой Рог",
            timezoneOffsetMinutes=-180,
            dailyEnabled=True,
            dailyTime="08:30",
            tomorrowEnabled=True,
            tomorrowTime="21:00",
        ),
        x_telegram_init_data="test",
    )
    assert result["weather"]["dailyTime"] == "08:30"
    assert result["weather"]["tomorrowEnabled"] is True


def test_reminder_screen_and_private_actions_are_not_audited() -> None:
    assert "Личный планировщик" in MINI_APP_HTML
    assert 'api("/miniapp/reminders/create"' in MINI_APP_HTML
    assert 'api("/miniapp/reminders/weather"' in MINI_APP_HTML
    assert 'normalized.startsWith("reminders_")' in MINI_APP_HTML
    assert should_skip_api_audit("/miniapp/reminders/create")
    assert should_skip_api_audit("/miniapp/reminders/delete")
    assert should_skip_api_audit("/miniapp/reminders/weather")
