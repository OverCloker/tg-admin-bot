import asyncio
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from PIL import Image

import app.bot as bot
import app.alert_map as alert_map
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
