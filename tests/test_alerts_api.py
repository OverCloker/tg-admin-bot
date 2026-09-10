import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.bot as bot_module
from app.bot import (
    ALERTS_POLL_INTERVAL_SECONDS,
    AlertsLocationState,
    AlertsThreat,
    alerts_location_state_signature,
    build_alarm_alert_text,
    format_current_alarm_status,
    format_alerts_location_details,
    format_important_alarm_update,
    is_important_alarm_update,
    parse_alerts_location_state,
)


def test_alerts_api_parses_direct_location_and_threats() -> None:
    state = parse_alerts_location_state(
        {
            "alerts": [
                {
                    "location_uid": "46",
                    "location_title": "Криворізький район",
                    "alert_type": "air_raid",
                    "alert_level": "red",
                    "threats": [
                        {
                            "threat_type": "drones",
                            "level": "yellow",
                            "started_at": "2026-09-07T10:00:00.000Z",
                            "source_message": "Дронова загроза",
                        }
                    ],
                }
            ]
        }
    )

    assert state.status == "A"
    assert state.alert_level == "red"
    assert state.threats == (
        AlertsThreat(
            threat_type="drones",
            level="yellow",
            started_at="2026-09-07T10:00:00.000Z",
            source_message="Дронова загроза",
        ),
    )


def test_alerts_api_oblast_alert_applies_to_location() -> None:
    state = parse_alerts_location_state(
        {
            "alerts": [
                {
                    "location_uid": 9,
                    "location_title": "Дніпропетровська область",
                    "alert_type": "air_raid",
                    "alert_level": "yellow",
                }
            ]
        }
    )

    assert state == AlertsLocationState(status="A", alert_level="yellow")


def test_alerts_api_child_alert_is_partial_for_raion() -> None:
    state = parse_alerts_location_state(
        {
            "alerts": [
                {
                    "location_uid": "999",
                    "location_title": "Тестова громада",
                    "location_raion": "Криворізький район",
                    "alert_type": "air_raid",
                },
                {
                    "location_uid": "46",
                    "location_title": "Криворізький район",
                    "alert_type": "artillery_shelling",
                },
            ]
        }
    )

    assert state.status == "P"


def test_alerts_api_ignores_unrelated_locations() -> None:
    state = parse_alerts_location_state(
        {
            "alerts": [
                {
                    "location_uid": "16",
                    "location_title": "Луганська область",
                    "alert_type": "air_raid",
                    "alert_level": "red",
                }
            ]
        }
    )

    assert state == AlertsLocationState(status="N")


def test_alerts_api_rejects_invalid_payload() -> None:
    with pytest.raises(RuntimeError, match="список alerts"):
        parse_alerts_location_state({"message": "error"})


def test_alerts_api_accepts_updated_schema_and_unknown_future_threat() -> None:
    state = parse_alerts_location_state(
        {
            "alerts": [
                {
                    "location_uid": "46",
                    "location_title": "Криворізький район",
                    "location_title_en": "Kryvyi Rih Raion",
                    "alert_type": "air_raid",
                    "alert_level": "yellow",
                    "threats": [
                        {
                            "threat_type": "future_threat",
                            "level": "yellow",
                            "started_at": "2026-09-10T10:00:00.000Z",
                            "source_message": "Нова категорія загрози",
                        }
                    ],
                }
            ]
        }
    )

    assert state.status == "A"
    assert state.alert_level == "yellow"
    assert state.threats[0].threat_type == "future_threat"
    assert "future threat" in format_alerts_location_details(state)


def test_alerts_api_uses_last_modified_cache(monkeypatch) -> None:
    payload = {
        "alerts": [
            {
                "location_uid": "46",
                "location_title": "Криворізький район",
                "alert_type": "air_raid",
                "alert_level": "red",
            }
        ]
    }

    class FakeResponse:
        def __init__(self, status, *, data=None, headers=None):
            self.status = status
            self.data = data
            self.headers = headers or {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def json(self, content_type=None):
            return self.data

        async def text(self):
            return ""

    class FakeSession:
        responses = [
            FakeResponse(200, data=payload, headers={"Last-Modified": "Thu, 10 Sep 2026 10:00:00 GMT"}),
            FakeResponse(304),
        ]
        request_headers = []

        def __init__(self, *, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        def get(self, url, *, headers):
            self.request_headers.append(dict(headers))
            return self.responses.pop(0)

    monkeypatch.setattr(bot_module.aiohttp, "ClientSession", FakeSession)
    monkeypatch.setattr(bot_module, "ALERTS_API_TOKEN", "test-token")
    monkeypatch.setattr(bot_module, "ALERTS_API_CACHE", bot_module.AlertsApiCache())

    first = asyncio.run(bot_module.fetch_alerts_location_state())
    second = asyncio.run(bot_module.fetch_alerts_location_state())

    assert first == second == AlertsLocationState(status="A", alert_level="red")
    assert "If-Modified-Since" not in FakeSession.request_headers[0]
    assert FakeSession.request_headers[1]["If-Modified-Since"] == "Thu, 10 Sep 2026 10:00:00 GMT"


def test_alerts_details_escape_external_source_text_and_signature_changes() -> None:
    first = AlertsLocationState(
        status="A",
        alert_level="yellow",
        threats=(AlertsThreat("drones", "yellow", None, "<b>не HTML</b>"),),
    )
    second = AlertsLocationState(
        status="A",
        alert_level="red",
        threats=(AlertsThreat("ballistic_missiles", "red", None, None),),
    )

    text = format_alerts_location_details(first)

    assert "ударные БПЛА" in text
    assert "&lt;b&gt;не HTML&lt;/b&gt;" in text
    assert alerts_location_state_signature(first) != alerts_location_state_signature(second)


def test_alerts_signature_ignores_started_at_when_visible_text_is_unchanged() -> None:
    first = AlertsLocationState(
        status="A",
        alert_level="yellow",
        threats=(AlertsThreat("drones", "yellow", "2026-09-07T10:00:00Z", "Дрони"),),
    )
    second = AlertsLocationState(
        status="A",
        alert_level="yellow",
        threats=(AlertsThreat("drones", "yellow", "2026-09-07T10:01:00Z", "Дрони"),),
    )

    assert alerts_location_state_signature(first) == alerts_location_state_signature(second)


def test_initial_alarm_message_explains_automatic_updates() -> None:
    text = build_alarm_alert_text(AlertsLocationState(status="A", alert_level="yellow"))

    assert "объявлена воздушная тревога" in text
    assert "обновляются автоматически каждые 30 секунд" in text


def test_current_alarm_status_has_no_location_and_uses_api_details() -> None:
    state = AlertsLocationState(
        status="A",
        alert_level="red",
        threats=(AlertsThreat("ballistic_missiles", "red", None, "Загроза балістики"),),
    )

    text = format_current_alarm_status(state)

    assert "Красная тревога" in text
    assert "баллистические ракеты" in text
    assert "Загроза балістики" in text
    assert "Кривор" not in text
    assert format_current_alarm_status(AlertsLocationState(status="N")) == "🟢 Тревоги нет."


def test_alarm_status_command_uses_latest_cached_api_state(monkeypatch) -> None:
    class FakeDb:
        def get_alarm_settings(self, chat_id):
            return SimpleNamespace(alarm_thread_id=77)

        def alarm_api_enabled(self, chat_id):
            return True

    state = AlertsLocationState(
        status="P",
        alert_level="yellow",
        threats=(AlertsThreat("drones", "yellow", None, "БпЛА у напрямку району"),),
    )
    monkeypatch.setattr(bot_module, "db", FakeDb(), raising=False)
    monkeypatch.setattr(bot_module, "ALERTS_API_CACHE", bot_module.AlertsApiCache(state=state))

    text = bot_module.alarm_status_text(-100)

    assert "Жёлтая тревога" in text
    assert "ударные БПЛА" in text
    assert "БпЛА у напрямку району" in text
    assert "Кривор" not in text
    assert "тема" not in text


@pytest.mark.anyio
async def test_alarm_status_message_is_pinned_and_previous_one_is_removed(monkeypatch) -> None:
    class FakeDb:
        def __init__(self):
            self.saved = []
            self.cleared = []

        def get_alarm_settings(self, chat_id):
            return SimpleNamespace(alarm_text=None)

        def alarm_restrictions_enabled(self, chat_id):
            return False

        def set_alarm_api_status_message_id(self, chat_id, status, message_id):
            self.saved.append((chat_id, status, message_id))

        def alarm_api_status_message_ids(self, chat_id, status):
            return [101, 102]

        def alarm_api_status_message_id(self, chat_id, status):
            return 101

        def clear_alarm_api_status_message_ids(self, chat_id, status):
            self.cleared.append((chat_id, status))

    fake_db = FakeDb()
    fake_bot = SimpleNamespace(
        pin_chat_message=AsyncMock(),
        unpin_chat_message=AsyncMock(),
        delete_message=AsyncMock(),
    )
    send_notification = AsyncMock(return_value=SimpleNamespace(message_id=501))
    monkeypatch.setattr(bot_module, "db", fake_db, raising=False)
    monkeypatch.setattr(bot_module, "send_alarm_notification", send_notification)

    activated = await bot_module.activate_alarm_from_api(
        fake_bot,
        -100,
        AlertsLocationState(status="A", alert_level="yellow"),
    )

    assert activated is True
    fake_bot.unpin_chat_message.assert_awaited_once_with(chat_id=-100, message_id=101)
    assert fake_bot.delete_message.await_count == 2
    fake_bot.pin_chat_message.assert_awaited_once_with(
        chat_id=-100,
        message_id=501,
        disable_notification=True,
    )
    assert fake_db.saved == [(-100, "A", 501)]
    assert fake_db.cleared == [(-100, "N")]


@pytest.mark.anyio
async def test_alarm_clear_replaces_alert_and_is_pinned(monkeypatch) -> None:
    class FakeDb:
        def __init__(self):
            self.saved = []

        def get_alarm_settings(self, chat_id):
            return SimpleNamespace(permissions_json=None, reactions_json=None, clear_text=None)

        def set_alarm_api_status_message_id(self, chat_id, status, message_id):
            self.saved.append((chat_id, status, message_id))

    fake_db = FakeDb()
    fake_bot = SimpleNamespace(pin_chat_message=AsyncMock())
    delete_previous = AsyncMock()
    restore_restrictions = AsyncMock()
    send_notification = AsyncMock(return_value=SimpleNamespace(message_id=601))
    monkeypatch.setattr(bot_module, "db", fake_db, raising=False)
    monkeypatch.setattr(bot_module, "delete_previous_alarm_status_message", delete_previous)
    monkeypatch.setattr(bot_module, "restore_alarm_restrictions", restore_restrictions)
    monkeypatch.setattr(bot_module, "send_alarm_notification", send_notification)

    cleared = await bot_module.deactivate_alarm_from_api(fake_bot, -100)

    assert cleared is True
    delete_previous.assert_awaited_once_with(fake_bot, -100, "A")
    send_notification.assert_awaited_once_with(fake_bot, -100, "🟢 <b>Отбой воздушной тревоги.</b>")
    fake_bot.pin_chat_message.assert_awaited_once_with(
        chat_id=-100,
        message_id=601,
        disable_notification=True,
    )
    assert fake_db.saved == [(-100, "N", 601)]


def test_only_escalations_create_separate_alarm_notification() -> None:
    yellow_drones = AlertsLocationState(
        status="A",
        alert_level="yellow",
        threats=(AlertsThreat("drones", "yellow", None, None),),
    )
    red_drones = AlertsLocationState(
        status="A",
        alert_level="red",
        threats=(AlertsThreat("drones", "yellow", None, None),),
    )
    yellow_missiles = AlertsLocationState(
        status="A",
        alert_level="yellow",
        threats=(
            AlertsThreat("drones", "yellow", None, None),
            AlertsThreat("ballistic_missiles", "red", None, None),
        ),
    )
    changed_drone_text = AlertsLocationState(
        status="A",
        alert_level="yellow",
        threats=(AlertsThreat("drones", "yellow", None, "Оновлений текст"),),
    )

    assert is_important_alarm_update(yellow_drones, red_drones) is True
    assert is_important_alarm_update(yellow_drones, yellow_missiles) is True
    assert is_important_alarm_update(yellow_drones, changed_drone_text) is False
    assert "баллистические ракеты" in format_important_alarm_update(
        yellow_drones,
        yellow_missiles,
    )


def test_regular_alarm_update_edits_existing_status_message(monkeypatch) -> None:
    class FakeDb:
        def alarm_api_status_message_id(self, chat_id, status):
            assert (chat_id, status) == (-100, "A")
            return 321

    fake_bot = type("FakeBot", (), {"edit_message_text": AsyncMock()})()
    monkeypatch.setattr(bot_module, "db", FakeDb(), raising=False)

    updated = asyncio.run(
        bot_module.edit_alarm_status_message(
            fake_bot,
            -100,
            AlertsLocationState(status="A", alert_level="red"),
        )
    )

    assert updated is True
    fake_bot.edit_message_text.assert_awaited_once()


def test_alerts_api_is_polled_every_30_seconds() -> None:
    assert ALERTS_POLL_INTERVAL_SECONDS == 30
