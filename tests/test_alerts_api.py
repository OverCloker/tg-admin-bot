import asyncio
from unittest.mock import AsyncMock

import pytest

import app.bot as bot_module
from app.bot import (
    ALERTS_POLL_INTERVAL_SECONDS,
    AlertsLocationState,
    AlertsThreat,
    alerts_location_state_signature,
    build_alarm_alert_text,
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
