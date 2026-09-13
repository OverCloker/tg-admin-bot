import asyncio
import sqlite3
from types import SimpleNamespace

import pytest

from app import bot as game
from app.db import Database


def _message(**values):
    defaults = {
        "chat": SimpleNamespace(id=-100, type="supergroup"),
        "is_automatic_forward": False,
        "sender_chat": None,
        "text": "триггер",
        "caption": None,
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)


def test_triggers_ignore_linked_channel_posts() -> None:
    assert game.is_trigger_chat_message(_message()) is True
    assert game.is_trigger_chat_message(_message(is_automatic_forward=True)) is False
    assert game.is_trigger_chat_message(
        _message(sender_chat=SimpleNamespace(type="channel"))
    ) is False
    assert game.is_trigger_chat_message(
        _message(sender_chat=SimpleNamespace(type="supergroup"))
    ) is False


def test_old_quotes_table_is_migrated_without_losing_text(tmp_path) -> None:
    path = tmp_path / "quotes.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute(
        "create table quotes (id integer primary key autoincrement, chat_id integer not null, "
        "text text not null, author_name text, added_by integer, created_at text not null)"
    )
    connection.execute(
        "insert into quotes(chat_id, text, author_name, added_by, created_at) values(-100, 'Старая', 'Автор', 1, 'now')"
    )
    connection.commit()
    connection.close()

    db = Database(str(path))
    try:
        db.init()
        quote = db.list_quotes(-100)[0]
        assert quote.text == "Старая"
        assert quote.media_type is None
        assert quote.media_file_id is None
    finally:
        db.close()


@pytest.mark.parametrize(
    ("media_type", "field"),
    [
        ("photo", "photo"),
        ("animation", "animation"),
        ("voice", "voice"),
        ("audio", "audio"),
        ("video", "video"),
    ],
)
def test_quote_media_file_id_is_extracted(media_type, field) -> None:
    values = {field: [SimpleNamespace(file_id="file-id")] if field == "photo" else SimpleNamespace(file_id="file-id")}
    assert game.quote_media_from_message(_message(**values)) == (media_type, "file-id")


@pytest.mark.parametrize("media_type", ["photo", "animation", "voice", "audio", "video"])
def test_saved_media_quote_is_sent_using_original_telegram_type(media_type) -> None:
    calls = []

    class FakeBot:
        def __getattr__(self, name):
            async def send(**kwargs):
                calls.append((name, kwargs))

            return send

    message = SimpleNamespace(
        chat=SimpleNamespace(id=-100),
        message_id=55,
        bot=FakeBot(),
        reply=lambda *_args, **_kwargs: None,
    )
    quote = SimpleNamespace(
        id=7,
        text="Подпись",
        media_type=media_type,
        media_file_id="telegram-file-id",
        author_name="Автор",
    )

    asyncio.run(game.send_quote(message, quote, "#7"))

    assert calls[0][0] == f"send_{media_type}"
    assert calls[0][1][media_type] == "telegram-file-id"
    assert "Подпись" in calls[0][1]["caption"]


def test_database_stores_media_quote_with_optional_caption(tmp_path) -> None:
    db = Database(str(tmp_path / "quotes.sqlite3"))
    try:
        db.init()
        db.add_quote(-100, "Подпись", "Автор", 1, "voice", "voice-file-id")
        quote = db.random_quote(-100)
        assert quote is not None
        assert quote.text == "Подпись"
        assert quote.media_type == "voice"
        assert quote.media_file_id == "voice-file-id"
    finally:
        db.close()
