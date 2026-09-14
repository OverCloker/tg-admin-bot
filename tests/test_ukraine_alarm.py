import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.bot as bot
import app.alert_providers as alert_providers
import app.miniapp as miniapp
from app.alert_providers import (
    DEFAULT_NEPTUN_LOCATION,
    UkraineAlarmProvider,
    parse_ukraine_alarm_alerts,
)
from app.db import Database
from app.miniapp import MiniAppAlarmSettingsSet


def region(name="Криворізький район", alerts=None):
    return {
        "regionId": 46,
        "regionName": name,
        "regionType": "District",
        "lastUpdate": "2026-09-14T10:00:00Z",
        "activeAlerts": alerts or [],
    }


def air(*levels):
    return {
        "regionId": 46,
        "regionName": "Криворізький район",
        "type": "AIR",
        "lastUpdate": "2026-09-14T10:00:00Z",
        "activeAlertLevels": list(levels),
    }


def level(value, reason="", created_at="2026-09-14T10:00:00Z"):
    return {"alertLevel": value, "reason": reason, "createdAt": created_at}


def test_ukraine_alarm_keeps_simultaneous_air_levels_and_reasons():
    state = parse_ukraine_alarm_alerts([
        region(alerts=[air(
            level("Yellow", "Загроза застосування ударних БПЛА"),
            level("Red", "Ракетна небезпека"),
        )]),
    ])
    assert (state.status, state.alert_level, state.official_alert) == ("A", "red", True)
    assert state.source == "ukraine_alarm"
    assert state.location_title == "Кривий Ріг"
    assert {item.level for item in state.threats} == {"yellow", "red"}
    assert {item.threat_type for item in state.threats} == {"drones", "unspecified_missiles"}


def test_ukraine_alarm_provider_uses_raw_auth_and_revision_cache(monkeypatch):
    responses = [
        {"lastActionIndex": 7},
        [region(alerts=[air(level("Yellow", "БПЛА"))])],
        {"lastActionIndex": 7},
    ]
    requests = []
    session_options = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def raise_for_status(self):
            return None

        async def json(self):
            return self.payload

    class Session:
        def __init__(self, **kwargs):
            session_options.append(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def get(self, url):
            requests.append(url)
            return Response(responses.pop(0))

    monkeypatch.setattr(alert_providers.aiohttp, "ClientSession", Session)
    provider = UkraineAlarmProvider("secret-key")
    first = asyncio.run(provider.fetch())
    second = asyncio.run(provider.fetch())
    assert first is second
    assert requests.count("https://api.ukrainealarm.com/api/v3/alerts/status") == 2
    assert requests.count("https://api.ukrainealarm.com/api/v3/alerts") == 1
    assert all(item["headers"]["Authorization"] == "secret-key" for item in session_options)


def test_ukraine_alarm_air_without_known_levels_is_still_active():
    state = parse_ukraine_alarm_alerts([
        region(alerts=[air(level("Green", "unknown"))]),
    ])
    assert state.status == "A"
    assert state.official_alert is True
    assert state.alert_level is None
    assert state.threats == ()


def test_ukraine_alarm_ignores_levels_on_non_air_alerts():
    state = parse_ukraine_alarm_alerts([
        region(alerts=[{
            "type": "ARTILLERY",
            "lastUpdate": "2026-09-14T10:00:00Z",
            "activeAlertLevels": [level("Yellow", "not an air level")],
        }]),
    ])
    assert (state.status, state.alert_level, state.official_alert) == ("A", "red", False)
    assert [item.threat_type for item in state.threats] == ["artillery"]


def test_ukraine_alarm_matches_city_district_or_oblast_but_not_other_area():
    oblast = parse_ukraine_alarm_alerts([
        region("Дніпропетровська область", [air(level("Yellow", "БПЛА"))]),
    ])
    assert oblast.status == "A"
    clear = parse_ukraine_alarm_alerts([
        region("Київська область", [air(level("Red", "Ракетна небезпека"))]),
    ])
    assert clear.status == "N"


@pytest.mark.parametrize("payload", [None, {}, [None], [{"regionName": "Криворізький район"}]])
def test_invalid_ukraine_alarm_snapshot_is_never_treated_as_clear(payload):
    with pytest.raises(ValueError):
        parse_ukraine_alarm_alerts(payload)


def test_admin_can_select_ukraine_alarm_only_when_token_is_configured(tmp_path, monkeypatch):
    database = Database(str(tmp_path / "bot.db"))
    database.init()
    database.upsert_chat(-1, "Group", "supergroup", None)
    monkeypatch.setattr(bot, "db", database, raising=False)
    monkeypatch.setattr(bot, "require_selected_admin", AsyncMock(return_value=object()))
    monkeypatch.setattr(bot, "require_callback_feature", AsyncMock(return_value=True))
    monkeypatch.setattr(bot, "mention_chat", lambda chat: "Group")
    monkeypatch.setattr(bot, "safe_edit", AsyncMock())
    callback = SimpleNamespace(
        data="alarm:source_ukraine_alarm:-1",
        from_user=SimpleNamespace(id=1),
        answer=AsyncMock(),
    )

    monkeypatch.setattr(bot, "UKRAINE_ALARM_API_TOKEN", None)
    asyncio.run(bot.cb_alarm(callback, object()))
    assert database.alarm_api_source(-1) == "alerts_in_ua"
    callback.answer.assert_awaited()

    callback.answer.reset_mock()
    monkeypatch.setattr(bot, "UKRAINE_ALARM_API_TOKEN", "secret")
    asyncio.run(bot.cb_alarm(callback, object()))
    assert database.alarm_api_source(-1) == "ukraine_alarm"
    bot.safe_edit.assert_awaited()
    database.close()


def test_ukraine_alarm_status_is_compact(tmp_path, monkeypatch):
    database = Database(str(tmp_path / "bot.db"))
    database.init()
    database.upsert_chat(-1, "Group", "supergroup", None)
    database.set_alarm_api_source(-1, "ukraine_alarm", 1)
    database.set_alarm_api_enabled(-1, True, 1)
    state = parse_ukraine_alarm_alerts([
        region(alerts=[air(level("Yellow", "Загроза застосування ударних БПЛА"))]),
    ])
    monkeypatch.setattr(bot, "db", database, raising=False)
    monkeypatch.setattr(bot, "PROVIDER_STATES", {("ukraine_alarm", DEFAULT_NEPTUN_LOCATION): state})
    text = bot.alarm_status_text(-1)
    assert "Город: <b>Кривий Ріг</b>" in text
    assert "Воздушная тревога: <b>активна</b>" in text
    assert "ударные БПЛА" in text
    assert "UkraineAlarm" in text
    database.close()


def test_miniapp_requires_token_before_enabling_ukraine_alarm(tmp_path, monkeypatch):
    database = Database(str(tmp_path / "bot.db"))
    database.init()
    database.upsert_chat(-1, "Group", "supergroup", None)
    database.replace_chat_telegram_admins(-1, [{
        "user_id": 1, "username": "admin", "full_name": "Admin",
        "status": "administrator", "is_bot": False,
    }])
    database.close()
    monkeypatch.setattr(miniapp, "_db", lambda: Database(str(tmp_path / "bot.db")))
    monkeypatch.setattr(miniapp, "_telegram_user", lambda _data: {"id": 1})
    payload = MiniAppAlarmSettingsSet(
        chatId=-1,
        automaticEnabled=True,
        source="ukraine_alarm",
        location=DEFAULT_NEPTUN_LOCATION,
    )
    monkeypatch.setattr(miniapp, "load_config", lambda: SimpleNamespace(
        owner_id=42,
        alerts_api_token=None,
        ukraine_alarm_api_token=None,
    ))
    with pytest.raises(Exception) as exc_info:
        miniapp.miniapp_profile_moderation_alarm(payload, x_telegram_init_data="test")
    assert getattr(exc_info.value, "status_code", None) == 400

    monkeypatch.setattr(miniapp, "load_config", lambda: SimpleNamespace(
        owner_id=42,
        alerts_api_token=None,
        ukraine_alarm_api_token="secret",
    ))
    saved = miniapp.miniapp_profile_moderation_alarm(payload, x_telegram_init_data="test")
    assert saved["alarm"]["source"] == "ukraine_alarm"
    assert saved["alarm"]["automaticEnabled"] is True
