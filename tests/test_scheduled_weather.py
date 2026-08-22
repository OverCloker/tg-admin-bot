from datetime import datetime, timedelta, timezone

from app.bot import auto_weather_slot, chat_help_text, parse_auto_weather_command
from app.db import Database


def test_parse_auto_weather_command() -> None:
    assert parse_auto_weather_command("автопогода") == ("status", None)
    assert parse_auto_weather_command("автопогода выкл") == ("off", None)
    assert parse_auto_weather_command("автопогода   Кривой   Рог ") == ("on", "Кривой Рог")


def test_chat_help_mentions_scheduled_weather() -> None:
    text = chat_help_text()

    assert "автопогода Кривой Рог" in text
    assert "08/12/15/18" in text
    assert "автопогода выкл" in text


def test_auto_weather_slot_uses_daily_schedule() -> None:
    tz = timezone(timedelta(hours=3))

    assert auto_weather_slot(datetime(2026, 8, 22, 7, 59, tzinfo=tz)) is None
    assert auto_weather_slot(datetime(2026, 8, 22, 8, 0, tzinfo=tz)) == (
        "2026-08-22:08:now",
        "now",
        "Плановая погода",
    )
    assert auto_weather_slot(datetime(2026, 8, 22, 21, 0, tzinfo=tz)) == (
        "2026-08-22:21:tomorrow",
        "tomorrow",
        "Плановая погода на завтра",
    )


def test_scheduled_weather_settings_are_persisted(tmp_path) -> None:
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()
    db.upsert_chat(-100, "Test chat", "supergroup", None)

    db.set_scheduled_weather_settings(-100, True, "Кривой Рог", 1, 777)
    settings = db.get_scheduled_weather_settings(-100)

    assert settings.enabled == 1
    assert settings.city == "Кривой Рог"
    assert settings.topic_thread_id == 777
    assert len(db.list_enabled_scheduled_weather()) == 1

    db.mark_scheduled_weather_sent(-100, "2026-08-22:08:now")
    assert db.get_scheduled_weather_settings(-100).last_sent_key == "2026-08-22:08:now"

    db.set_scheduled_weather_settings(-100, False, "Кривой Рог", 1, 777)
    assert db.list_enabled_scheduled_weather() == []
    db.close()
