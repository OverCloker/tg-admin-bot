import asyncio
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import app.bot as bot
from app.alert_providers import (
    DEFAULT_NEPTUN_LOCATION,
    NEPTUN_LOCATIONS,
    AlertsLocationState,
    NeptunProvider,
    parse_neptun_alerts,
)
from app.db import Database


@pytest.fixture
def database(tmp_path):
    db = Database(str(tmp_path / "bot.db"))
    db.init()
    for chat in (-1, -2):
        db.upsert_chat(chat, str(chat), "supergroup", None)
        db.set_alarm_api_enabled(chat, True, 1)
    yield db
    db.close()


def test_neptun_district_oblast_and_clear():
    district = {"key": "криворізький", "name": "Криворізький район", "oblast": "Дніпропетровська область"}
    assert parse_neptun_alerts({"raions": [district], "oblasts": []}).status == "A"
    district["oblast"] = "Інша область"
    assert parse_neptun_alerts({"raions": [district], "oblasts": []}).status == "N"
    assert parse_neptun_alerts({"raions": [], "oblasts": [
        {"key": "дніпропетровська", "name": "Дніпропетровська область"}
    ]}).status == "A"
    state = parse_neptun_alerts({"raions": [], "oblasts": [], "threats": [{"type": "missile"}]})
    assert state.status == "N"
    assert state.source == "neptun"
    assert state.location_title == "Кривий Ріг"
    assert state.official_area == "Криворізький район, Дніпропетровська область"


def test_neptun_city_mapping_and_kyiv_special_area():
    dnipro = {"key": "дніпровський", "name": "Дніпровський район", "oblast": "Дніпропетровська область", "level": "yellow"}
    state = parse_neptun_alerts({"raions": [dnipro], "oblasts": []}, "dnipro")
    assert (state.status, state.alert_level, state.location_title) == ("A", "yellow", "Дніпро")
    kyiv = parse_neptun_alerts(
        {"raions": [], "oblasts": [{"key": "м. київ", "name": "м. Київ", "level": "red"}]},
        "kyiv-city",
    )
    assert (kyiv.status, kyiv.alert_level, kyiv.official_area) == ("A", "red", "м. Київ")


def test_neptun_accepts_geojson_apostrophe_variant():
    state = parse_neptun_alerts(
        {
            "raions": [{
                "key": "кам'янський",
                "name": "Кам'янський район",
                "oblast": "Дніпропетровська область",
            }],
            "oblasts": [],
        },
        "kamianske",
    )
    assert state.status == "A"


def neptun_snapshot(status):
    districts = []
    if status == "A":
        districts.append({
            "key": "криворізький",
            "name": "Криворізький район",
            "oblast": "Дніпропетровська область",
        })
    return {"raions": districts, "oblasts": []}


@pytest.mark.parametrize("payload", [None, {}, {"raions": [], "oblasts": None},
    {"raions": [None], "oblasts": []}, {"raions": [{"key": "x", "name": "x"}], "oblasts": []}])
def test_invalid_snapshot_is_never_clear(payload):
    with pytest.raises(ValueError):
        parse_neptun_alerts(payload)


def test_migration_from_existing_schema(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("create table alarm_api_settings (chat_id integer primary key, enabled integer, last_status text, updated_by integer, updated_at text)")
    conn.execute("insert into alarm_api_settings values (-1, 1, 'A', 1, 'old')")
    conn.commit()
    conn.close()
    db = Database(str(path))
    db.init()
    db.init()
    assert db.alarm_api_source(-1) == "alerts_in_ua"
    assert db.alarm_api_location(-1) == DEFAULT_NEPTUN_LOCATION
    assert db.alarm_api_last_status(-1) == "A"
    db.close()


def test_source_persistence_and_group_isolation(database):
    db = database
    db.set_alarm_api_last_status(-1, "A")
    db.set_alarm_api_last_notified_status(-1, "A")
    db.set_alarm_api_status_message_id(-1, "A", 123)
    db.set_alarm_api_source(-1, "neptun", 1)
    db.set_alarm_api_location(-1, "dnipro", 1)
    db.init()
    assert db.alarm_api_source(-1) == "neptun"
    assert db.alarm_api_source(-2) == "alerts_in_ua"
    assert db.alarm_api_location(-1) == "dnipro"
    assert db.alarm_api_location(-2) == DEFAULT_NEPTUN_LOCATION
    assert db.alarm_api_last_status(-1) == "A"
    assert db.alarm_api_last_notified_status(-1) == "A"
    assert db.alarm_api_status_message_id(-1, "A") == 123
    db.set_alarm_api_enabled(-1, False, 1)
    db.set_alarm_api_enabled(-1, True, 1)
    assert db.alarm_api_source(-1) == "neptun"
    with pytest.raises(ValueError):
        db.set_alarm_api_source(-1, "invalid", 1)
    with pytest.raises(ValueError):
        db.set_alarm_api_location(-1, "invalid", 1)
    assert db.alarm_api_source(-1) == "neptun"


def run_cycles(monkeypatch, count, after_cycle=None):
    calls = 0
    async def sleep(seconds):
        nonlocal calls
        calls += 1
        if after_cycle:
            after_cycle(calls)
        if calls >= count:
            raise asyncio.CancelledError
    monkeypatch.setattr(bot.asyncio, "sleep", sleep)


def test_monitor_routes_groups_and_survives_provider_failure(database, monkeypatch):
    database.set_alarm_api_source(-1, "neptun", 1)
    monkeypatch.setattr(bot, "db", database, raising=False)
    monkeypatch.setattr(bot, "ALERTS_API_TOKEN", None)
    neptun = AsyncMock(side_effect=[
        neptun_snapshot("A"), RuntimeError("network"), neptun_snapshot("N")
    ])
    legacy = AsyncMock(side_effect=[AlertsLocationState("N"), AlertsLocationState("A"), AlertsLocationState("A")])
    monkeypatch.setattr(NeptunProvider, "fetch", neptun)
    monkeypatch.setattr(bot, "fetch_alerts_location_state", legacy)
    activate = AsyncMock(return_value=True)
    clear = AsyncMock(return_value=True)
    monkeypatch.setattr(bot, "activate_alarm_from_api", activate)
    monkeypatch.setattr(bot, "deactivate_alarm_from_api", clear)
    def check(cycle):
        if cycle == 2:
            assert database.alarm_api_last_status(-1) == "A"
            clear.assert_not_awaited()
    run_cycles(monkeypatch, 3, check)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(bot.alerts_monitor_loop(object()))
    assert activate.await_args.args[1] == -2
    assert clear.await_args.args[1:] == (-1, "neptun")
    assert neptun.await_count == legacy.await_count == 3


@pytest.mark.parametrize("target_status", ["A", "N"])
def test_switch_reconciles_existing_alarm(database, monkeypatch, target_status):
    monkeypatch.setattr(bot, "db", database, raising=False)
    monkeypatch.setattr(bot, "fetch_alerts_location_state", AsyncMock(return_value=AlertsLocationState("A")))
    monkeypatch.setattr(NeptunProvider, "fetch", AsyncMock(return_value=neptun_snapshot(target_status)))
    edit = AsyncMock(return_value=True)
    clear = AsyncMock(return_value=True)
    monkeypatch.setattr(bot, "edit_alarm_status_message", edit)
    monkeypatch.setattr(bot, "deactivate_alarm_from_api", clear)
    run_cycles(monkeypatch, 2, lambda cycle: database.set_alarm_api_source(-1, "neptun", 1) if cycle == 1 else None)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(bot.alerts_monitor_loop(object()))
    if target_status == "A":
        clear.assert_not_awaited()
        assert edit.await_args.args[1] == -1
        assert edit.await_args.args[2].source == "neptun"
    else:
        assert clear.await_args.args[1:] == (-1, "neptun")


def test_source_callback_requires_admin(database, monkeypatch):
    monkeypatch.setattr(bot, "db", database, raising=False)
    monkeypatch.setattr(bot, "require_selected_admin", AsyncMock(return_value=None))
    callback = SimpleNamespace(data="alarm:source_neptun:-1")
    asyncio.run(bot.cb_alarm(callback, object()))
    assert database.alarm_api_source(-1) == "alerts_in_ua"


def test_admin_can_select_neptun_without_token(database, monkeypatch):
    monkeypatch.setattr(bot, "db", database, raising=False)
    monkeypatch.setattr(bot, "ALERTS_API_TOKEN", None)
    monkeypatch.setattr(bot, "require_selected_admin", AsyncMock(return_value=object()))
    monkeypatch.setattr(bot, "require_callback_feature", AsyncMock(return_value=True))
    monkeypatch.setattr(bot, "mention_chat", lambda chat: "Group")
    monkeypatch.setattr(bot, "safe_edit", AsyncMock())
    callback = SimpleNamespace(data="alarm:source_neptun:-1", from_user=SimpleNamespace(id=1), answer=AsyncMock())
    asyncio.run(bot.cb_alarm(callback, object()))
    assert database.alarm_api_source(-1) == "neptun"
    assert database.alarm_api_source(-2) == "alerts_in_ua"
    assert "NEPTUN" in bot.safe_edit.await_args.args[1]


def test_admin_can_select_city_per_group(database, monkeypatch):
    monkeypatch.setattr(bot, "db", database, raising=False)
    monkeypatch.setattr(bot, "require_selected_admin", AsyncMock(return_value=object()))
    monkeypatch.setattr(bot, "require_callback_feature", AsyncMock(return_value=True))
    monkeypatch.setattr(bot, "mention_chat", lambda chat: "Group")
    monkeypatch.setattr(bot, "safe_edit", AsyncMock())
    callback = SimpleNamespace(
        data="alarm:location_dnipro:-1",
        from_user=SimpleNamespace(id=1),
        answer=AsyncMock(),
    )
    asyncio.run(bot.cb_alarm(callback, object()))
    assert database.alarm_api_location(-1) == "dnipro"
    assert database.alarm_api_location(-2) == DEFAULT_NEPTUN_LOCATION
    assert "Дніпровський район" in bot.safe_edit.await_args.args[1]
    assert len(NEPTUN_LOCATIONS) == 41


def test_city_menu_paginates_with_valid_callback_lengths():
    seen = set()
    for page in range(5):
        menu = bot.neptun_location_menu(-1001234567890, "kryvyi-rih", page)
        for row in menu.inline_keyboard:
            for button in row:
                assert len(button.callback_data.encode("utf-8")) <= 64
                if button.callback_data.startswith("alarm:location_"):
                    seen.add(button.callback_data.split(":", 2)[1].removeprefix("location_"))
    assert seen == set(NEPTUN_LOCATIONS)


def test_attribution_and_status_do_not_use_other_source(database, monkeypatch):
    monkeypatch.setattr(bot, "db", database, raising=False)
    database.set_alarm_api_source(-1, "neptun", 1)
    monkeypatch.setattr(bot, "PROVIDER_STATES", {})
    monkeypatch.setattr(bot, "ALERTS_API_CACHE", bot.AlertsApiCache(state=AlertsLocationState("N")))
    assert "ещё не получен" in bot.alarm_status_text(-1)
    assert "https://neptun.in.ua/" in bot.build_alarm_alert_text(AlertsLocationState("A", source="neptun"))
