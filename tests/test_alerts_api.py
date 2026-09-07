import pytest

from app.bot import (
    ALERTS_POLL_INTERVAL_SECONDS,
    AlertsLocationState,
    AlertsThreat,
    alerts_location_state_signature,
    format_alerts_location_details,
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


def test_alerts_api_is_polled_every_30_seconds() -> None:
    assert ALERTS_POLL_INTERVAL_SECONDS == 30
