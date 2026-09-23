import ast
import asyncio
import inspect
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.types import InlineQuery, Update
from aiogram.types import InlineQueryResultArticle, InlineQueryResultPhoto
from fastapi import HTTPException
from PIL import Image

from app import bot
from app import miniapp
from app.admin_api import inline_media_photo
from app.alert_map import AlertMapResult
from app import inline_media
from app.admin_api import app
from app.db import Database
from app.miniapp_ui import MINI_APP_HTML


@pytest.fixture(autouse=True)
def reset_inline_runtime(tmp_path, monkeypatch):
    database = Database(str(tmp_path / "inline.sqlite3"))
    database.init()
    monkeypatch.setattr(bot, "db", database, raising=False)
    monkeypatch.setattr(bot, "load_config", lambda: SimpleNamespace(owner_id=999))
    bot.INLINE_WEATHER_CACHE.clear()
    bot.INLINE_WEATHER_TASKS.clear()
    bot.INLINE_MAP_CACHE.clear()
    bot.INLINE_MAP_TASKS.clear()
    bot.INLINE_USER_LIMITS.clear()
    yield database
    database.close()


def png_bytes(size=(80, 60)) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, (218, 38, 45)).save(output, format="PNG")
    return output.getvalue()


def test_inline_media_is_atomic_jpeg_and_path_is_constrained(tmp_path):
    image = png_bytes()
    with ThreadPoolExecutor(max_workers=4) as executor:
        saved = list(executor.map(lambda _: inline_media.save_inline_photo(image, tmp_path), range(4)))
    assert len({item[0] for item in saved}) == 1
    filename, path = saved[0]
    assert path.read_bytes().startswith(b"\xff\xd8")
    assert path.stat().st_size <= inline_media.INLINE_PHOTO_MAX_BYTES
    assert inline_media.resolve_inline_photo(filename, tmp_path) == path
    assert inline_media.resolve_inline_photo("../secret.jpg", tmp_path) is None


def test_inline_media_rejects_a_photo_that_cannot_fit_limit(monkeypatch):
    monkeypatch.setattr(inline_media, "INLINE_PHOTO_MAX_BYTES", 10)
    with pytest.raises(ValueError, match="5 MB"):
        inline_media.save_inline_photo(png_bytes(), None)


def test_public_inline_endpoint_serves_only_generated_filename(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    filename, path = inline_media.save_inline_photo(png_bytes())
    response = inline_media_photo(filename)
    assert Path(response.path) == path
    assert response.media_type == "image/jpeg"
    assert response.headers["cache-control"] == "public, max-age=86400, immutable"
    with pytest.raises(HTTPException) as error:
        inline_media_photo("..%2F.env")
    assert error.value.status_code == 404


def test_inline_weather_routes_to_forecast(monkeypatch):
    answer = AsyncMock()
    query = SimpleNamespace(query="  погода   Киев завтра ", answer=answer)
    monkeypatch.setattr(bot, "fetch_inline_weather", AsyncMock(return_value="<b>Погода на завтра: Киев</b>"))

    asyncio.run(bot.inline_weather_or_alert_map(query))

    bot.fetch_inline_weather.assert_awaited_once_with("Киев", "tomorrow")
    results = answer.await_args.args[0]
    assert len(results) == 1
    assert isinstance(results[0], InlineQueryResultArticle)
    assert results[0].title == "🌤 Погода выбранного населённого пункта"
    assert "Киев · на завтра" in results[0].description
    assert results[0].input_message_content.message_text.startswith("<b>Погода")
    assert answer.await_args.kwargs["cache_time"] == bot.INLINE_ANSWER_CACHE_SECONDS
    assert answer.await_args.kwargs["is_personal"] is True


def test_inline_weather_reuses_same_query_but_limits_a_new_city(monkeypatch):
    fetch = AsyncMock(return_value="<b>Прогноз</b>")
    monkeypatch.setattr(bot, "fetch_weather", fetch)

    async def run():
        first = AsyncMock()
        repeated = AsyncMock()
        limited = AsyncMock()
        await bot.inline_weather_or_alert_map(SimpleNamespace(
            query="погода Киев", from_user=SimpleNamespace(id=10), answer=first,
        ))
        await bot.inline_weather_or_alert_map(SimpleNamespace(
            query="погода Киев", from_user=SimpleNamespace(id=10), answer=repeated,
        ))
        await bot.inline_weather_or_alert_map(SimpleNamespace(
            query="погода Львов", from_user=SimpleNamespace(id=10), answer=limited,
        ))
        return first, repeated, limited

    _, repeated, limited = asyncio.run(run())

    fetch.assert_awaited_once_with("Киев", "now")
    assert repeated.await_args.args[0][0].title == "🌤 Погода выбранного населённого пункта"
    assert limited.await_args.args[0][0].title.startswith("⏳ Новый запрос через")


def test_inline_owner_is_not_rate_limited(monkeypatch):
    fetch = AsyncMock(side_effect=["<b>Киев</b>", "<b>Львов</b>"])
    monkeypatch.setattr(bot, "fetch_weather", fetch)

    async def run():
        for city in ("Киев", "Львов"):
            await bot.inline_weather_or_alert_map(SimpleNamespace(
                query=f"погода {city}", from_user=SimpleNamespace(id=999), answer=AsyncMock(),
            ))

    asyncio.run(run())
    assert fetch.await_count == 2


def test_inline_alert_map_produces_public_jpeg_result(tmp_path, monkeypatch):
    answer = AsyncMock()
    query = SimpleNamespace(query="карта тревог днепр", answer=answer)
    generated = AlertMapResult(
        image=png_bytes(),
        updated_at=datetime(2026, 9, 17, 12, tzinfo=timezone.utc),
        alert_count=3,
        threat_count=1,
        region_title="Дніпропетровська область",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ADMIN_PUBLIC_URL", "https://app.example.test")
    monkeypatch.setattr(bot, "fetch_alert_map", AsyncMock(return_value=generated))

    asyncio.run(bot.inline_weather_or_alert_map(query))

    bot.fetch_alert_map.assert_awaited_once_with("днепр")
    result = answer.await_args.args[0][0]
    assert isinstance(result, InlineQueryResultPhoto)
    assert result.title == "🗺 Карта тревог выбранного региона"
    assert "Дніпропетровська область" in result.description
    assert (result.photo_width, result.photo_height) == (1200, 900)
    assert result.photo_url.startswith("https://app.example.test/inline-media/")
    assert result.photo_url.endswith(".jpg")
    saved = tmp_path / "media_storage" / "inline_maps" / result.photo_url.rsplit("/", 1)[1]
    assert saved.read_bytes().startswith(b"\xff\xd8")
    assert "Обновлено" in result.caption


def test_inline_usage_statistics_include_periods_and_regions(reset_inline_runtime):
    database = reset_inline_runtime
    now = datetime(2026, 9, 17, 12, tzinfo=timezone.utc)
    database.record_inline_usage(1, "weather", target="Киев", created_at="2026-09-17T11:00:00+00:00")
    database.record_inline_usage(2, "weather", target="Львов", created_at="2026-09-10T11:00:00+00:00")
    database.record_inline_usage(
        1, "alert_map", target="днепр", region="Дніпропетровська область",
        created_at="2026-09-17T11:30:00+00:00",
    )
    database.record_inline_usage(
        2, "alert_map", target="киев", region="Київська область",
        created_at="2026-08-01T10:00:00+00:00",
    )

    stats = database.inline_usage_statistics(now)

    assert stats["weather"] == {"day": 1, "week": 1, "month": 2, "all": 2}
    assert stats["alertMap"] == {"day": 1, "week": 1, "month": 1, "all": 2}
    assert stats["alertMapRegions"][0]["region"] == "Дніпропетровська область"


def test_miniapp_owner_can_view_inline_statistics(reset_inline_runtime, monkeypatch):
    database = reset_inline_runtime
    database.record_inline_usage(1, "weather", target="Киев")
    database.record_inline_usage(1, "alert_map", target="днепр", region="Дніпропетровська область")
    monkeypatch.setattr(miniapp, "_db", lambda: Database(str(database.path)))
    monkeypatch.setattr(miniapp, "_telegram_user", lambda _data: {"id": 999})
    monkeypatch.setattr(miniapp, "load_config", lambda: SimpleNamespace(owner_id=999))

    payload = miniapp.miniapp_profile_inline_statistics(x_telegram_init_data="signed")

    assert payload["weather"]["all"] == 1
    assert payload["alertMap"]["all"] == 1
    assert payload["alertMapRegions"][0]["region"] == "Дніпропетровська область"
    assert 'api("/miniapp/profile/inline-statistics")' in MINI_APP_HTML


@pytest.mark.parametrize("text", ["", "погода", "что-нибудь другое"])
def test_empty_and_invalid_inline_queries_return_usage(text):
    answer = AsyncMock()
    asyncio.run(bot.inline_weather_or_alert_map(SimpleNamespace(query=text, answer=answer)))
    results = answer.await_args.args[0]
    assert [item.title for item in results] == [
        "🌤 Погода выбранного города",
        "🗺 Карта тревог выбранного региона",
        "❓ Помощь",
    ]


@pytest.mark.parametrize("text", ["помощь", "help", "/help"])
def test_inline_help_has_developer_contact_button(text):
    answer = AsyncMock()
    asyncio.run(bot.inline_weather_or_alert_map(SimpleNamespace(query=text, answer=answer)))

    results = answer.await_args.args[0]
    assert len(results) == 1
    result = results[0]
    assert result.title == "❓ Помощь"
    assert "@YourLittleCat" in result.input_message_content.message_text
    button = result.reply_markup.inline_keyboard[0][0]
    assert button.text == "💬 Связаться с разработчиком"
    assert button.url == "https://t.me/YourLittleCat"


def test_production_polling_subscribes_to_inline_queries():
    startup = ast.parse(inspect.getsource(bot.main))
    calls = [
        node for node in ast.walk(startup)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "start_polling"
    ]
    allowed = next(keyword.value for keyword in calls[0].keywords if keyword.arg == "allowed_updates")
    assert "inline_query" in ast.literal_eval(allowed)


def test_inline_query_dispatch_and_http_photo_delivery(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ADMIN_PUBLIC_URL", "https://example.test")
    generated = AlertMapResult(png_bytes(), datetime.now(timezone.utc), 1, 2)
    monkeypatch.setattr(bot, "fetch_alert_map", AsyncMock(return_value=generated))
    answer = AsyncMock()
    monkeypatch.setattr(InlineQuery, "answer", answer)

    async def run():
        client = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
        dispatcher = Dispatcher()
        dispatcher.include_router(bot.router)
        try:
            await dispatcher.feed_update(client, Update.model_validate({
                "update_id": 900,
                "inline_query": {
                    "id": "test-query", "query": "карта тревог", "offset": "",
                    "from": {"id": 42, "is_bot": False, "first_name": "Tester"},
                },
            }))
            result = answer.await_args.args[0][0]
            path = "/inline-media/" + result.photo_url.rsplit("/", 1)[1]
            sent = []

            async def send(message):
                sent.append(message)

            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}

            await app({
                "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                "method": "GET", "scheme": "https", "path": path,
                "raw_path": path.encode(), "query_string": b"", "headers": [],
                "server": ("example.test", 443), "client": ("127.0.0.1", 1234),
            }, receive, send)
            assert sent[0]["status"] == 200
            assert dict(sent[0]["headers"])[b"content-type"] == b"image/jpeg"
            content = b"".join(item.get("body", b"") for item in sent)
            assert content.startswith(b"\xff\xd8")
            with Image.open(BytesIO(content)) as image:
                assert image.format == "JPEG"
        finally:
            dispatcher.sub_routers.remove(bot.router)
            bot.router._parent_router = None
            await dispatcher.storage.close()
            await client.session.close()

    asyncio.run(run())


def test_inline_weather_coalesces_and_releases_completed_tasks(monkeypatch):
    monkeypatch.setattr(bot, "INLINE_WEATHER_CACHE", {})
    monkeypatch.setattr(bot, "INLINE_WEATHER_TASKS", {})
    fetch = AsyncMock(return_value="forecast")
    monkeypatch.setattr(bot, "fetch_weather", fetch)

    async def run():
        assert await asyncio.gather(
            bot.fetch_inline_weather("Киев", "now"),
            bot.fetch_inline_weather("Киев", "now"),
        ) == ["forecast", "forecast"]
        assert await bot.fetch_inline_weather("Киев", "now") == "forecast"
        assert not bot.INLINE_WEATHER_TASKS

    asyncio.run(run())
    fetch.assert_awaited_once()
