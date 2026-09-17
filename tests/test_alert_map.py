import asyncio
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import pytest
from aiogram import Bot, Dispatcher
from aiogram.types import Message, Update
from PIL import Image

import app.alert_map as alert_map
import app.bot as bot
from app.alert_map import AlertMapResult, render_alert_map


def feature(key, coordinates, *, name="region"):
    return {
        "type": "Feature",
        "properties": {"key": key, "region": name, "rayon": name},
        "geometry": {"type": "Polygon", "coordinates": [coordinates]},
    }


def test_alert_map_renderer_builds_png_with_alerts_and_threats():
    oblasts = {
        "type": "FeatureCollection",
        "features": [feature("oblast", [[22, 44], [40, 44], [40, 52], [22, 52], [22, 44]])],
    }
    raions = {
        "type": "FeatureCollection",
        "features": [feature("raion", [[28, 46], [34, 46], [34, 50], [28, 50], [28, 46]])],
    }
    alerts = {
        "raions": [{"key": "raion", "name": "Район"}],
        "oblasts": [{"key": "oblast", "name": "Область"}],
    }
    threats = {
        "serverTime": "2026-09-16T10:00:00Z",
        "threats": [
            {"id": "1", "type": "uav", "lat": 48.0, "lon": 31.0, "status": "active"},
            {"id": "2", "type": "missile", "lat": 49.0, "lon": 32.0, "status": "resolved"},
        ],
    }

    result = render_alert_map(
        raions, oblasts, alerts, threats, datetime(2026, 9, 16, 10, tzinfo=timezone.utc)
    )

    assert result.startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(BytesIO(result)) as image:
        assert image.size == (1200, 900)
        assert image.mode == "RGB"


def test_alert_map_command_sends_generated_photo(monkeypatch):
    generated = AlertMapResult(
        image=b"\x89PNG\r\n\x1a\nmock",
        updated_at=datetime(2026, 9, 16, 10, tzinfo=timezone.utc),
        alert_count=7,
        threat_count=3,
    )
    monkeypatch.setattr(bot, "fetch_alert_map", AsyncMock(return_value=generated))
    message = SimpleNamespace(
        text="карта тревог",
        chat=SimpleNamespace(id=42, type="private"),
        bot=SimpleNamespace(send_chat_action=AsyncMock()),
        message_thread_id=None,
        answer_photo=AsyncMock(),
    )

    asyncio.run(bot.alert_map_command(message))

    message.answer_photo.assert_awaited_once()
    call = message.answer_photo.await_args
    assert call.args[0].filename == "alert-map.png"
    assert "Актуальная карта тревог Украины" in call.kwargs["caption"]
    assert "Активных территорий: <b>7</b>" in call.kwargs["caption"]
    assert "угроз на карте: <b>3</b>" in call.kwargs["caption"]
    assert "https://neptun.in.ua/" in call.kwargs["caption"]


def test_alert_map_command_and_help_aliases_are_registered():
    for text in (
        "карта тревог", "Карта тривог!", "/карта_тревог",
        "/alertmap", "/alarm_map", "/alertmap@ypominanieBot",
    ):
        assert bot.ALERT_MAP_RE.fullmatch(text)
    assert "карта тревог" in bot.chat_help_text()


def test_map_download_stops_when_stream_exceeds_limit(monkeypatch):
    monkeypatch.setattr(alert_map, "MAX_RESPONSE_BYTES", 5)
    consumed = []

    class Response:
        content_length = None
        content = None

        def raise_for_status(self):
            pass

        async def iter_chunked(self, size):
            for chunk in (b"123", b"456", b"789"):
                consumed.append(chunk)
                yield chunk

        async def __aenter__(self):
            self.content = self
            return self

        async def __aexit__(self, *args):
            pass

    session = SimpleNamespace(get=lambda url: Response())
    with pytest.raises(ValueError, match="too large"):
        asyncio.run(alert_map._fetch_json(session, "/test"))
    assert consumed == [b"123", b"456"]


def test_regional_map_filters_neighboring_alerts_and_threats():
    selected = feature("дніпропетровська", [[30, 46], [34, 46], [34, 50], [30, 50], [30, 46]])
    selected["properties"]["region"] = "Дніпропетровська область"
    neighbor = feature("інша", [[35, 46], [38, 46], [38, 50], [35, 50], [35, 46]])
    inside = feature("local", [[31, 47], [32, 47], [32, 48], [31, 48], [31, 47]])
    outside = feature("outside", [[36, 47], [37, 47], [37, 48], [36, 48], [36, 47]])
    geometry = {"type": "FeatureCollection", "features": [selected, neighbor]}
    raions = {"type": "FeatureCollection", "features": [inside, outside]}
    for alias in ("днепр", "Дніпро", "Дніпропетровська область", "Кривой Рог"):
        assert alert_map.resolve_map_region(alias, geometry) == selected
    alerts = {"raions": [{"key": "local"}, {"key": "outside"}], "oblasts": [{"key": "інша"}]}
    threats = {"threats": [{"lon": 31.5, "lat": 47.5}, {"lon": 36.5, "lat": 47.5}]}
    r, o, a, t, title = alert_map.regional_payloads(raions, geometry, alerts, threats, "днепр")
    assert r["features"] == [inside]
    assert a == {"raions": [{"key": "local"}], "oblasts": []}
    assert len(t["threats"]) == 1
    assert render_alert_map(r, o, a, t, region_title=title).startswith(b"\x89PNG")
    with pytest.raises(alert_map.UnknownMapRegion):
        alert_map.resolve_map_region("несуществующая", geometry)


def test_regional_command_argument():
    for command in ("карта тревог днепр", "/alertmap@ypominanieBot Дніпро!"):
        assert bot.ALERT_MAP_RE.fullmatch(command).group("region").casefold() in {"днепр", "дніпро"}
    assert bot.ALERT_MAP_RE.fullmatch("карта тревог").group("region") is None


def test_private_weather_and_alert_map_reach_registered_handlers(monkeypatch):
    forecast = "<b>PRIVATE WEATHER</b>"
    generated = AlertMapResult(
        image=b"\x89PNG\r\n\x1a\nmock",
        updated_at=datetime(2026, 9, 16, 10, tzinfo=timezone.utc),
        alert_count=2,
        threat_count=1,
    )
    replies = AsyncMock()
    photos = AsyncMock()
    monkeypatch.setattr(bot, "fetch_weather", AsyncMock(return_value=forecast))
    monkeypatch.setattr(bot, "fetch_alert_map", AsyncMock(return_value=generated))
    monkeypatch.setattr(Message, "reply", replies)
    monkeypatch.setattr(Message, "answer_photo", photos)
    monkeypatch.setattr(Bot, "send_chat_action", AsyncMock())

    async def run() -> None:
        client = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
        dispatcher = Dispatcher()
        dispatcher.include_router(bot.router)
        try:
            texts = (
                "погода Кривой Рог",
                "погода Кривой Рог завтра",
                "погода Кривой Рог неделя",
                "карта тревог",
                "карта тревог днепр",
            )
            for update_id, text in enumerate(texts, start=1):
                await dispatcher.feed_update(
                    client,
                    Update.model_validate(
                        {
                            "update_id": update_id,
                            "message": {
                                "message_id": update_id,
                                "date": datetime.now(timezone.utc),
                                "chat": {"id": 42, "type": "private", "first_name": "User"},
                                "from": {"id": 42, "is_bot": False, "first_name": "User"},
                                "text": text,
                            },
                        }
                    ),
                )
        finally:
            await client.session.close()
            dispatcher.sub_routers.remove(bot.router)
            bot.router._parent_router = None

    asyncio.run(run())

    assert bot.fetch_weather.await_args_list == [
        call("Кривой Рог", "now"),
        call("Кривой Рог", "tomorrow"),
        call("Кривой Рог", "week"),
    ]
    assert sum(item.args and item.args[0] == forecast for item in replies.await_args_list) == 3
    assert bot.fetch_alert_map.await_args_list == [call(), call("днепр")]
    assert photos.await_count == 2
    assert all(item.args[0].filename == "alert-map.png" for item in photos.await_args_list)
