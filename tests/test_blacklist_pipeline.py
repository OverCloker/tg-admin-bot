import asyncio
import ast
import inspect
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher, Router
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import DeleteMessage, SendMessage
from aiogram.types import Message, Update

from app import bot as app_bot
from app.db import Database


def test_production_polling_requests_edited_messages_from_telegram():
    # Feeding an Update into a test dispatcher bypasses getUpdates. Validate
    # the real startup call too, so an omitted subscription cannot hide edits.
    startup = ast.parse(inspect.getsource(app_bot.main))
    calls = [node for node in ast.walk(startup) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and node.func.attr == 'start_polling']
    assert len(calls) == 1
    allowed = next(keyword.value for keyword in calls[0].keywords if keyword.arg == 'allowed_updates')
    assert {'message', 'edited_message', 'channel_post', 'edited_channel_post', 'callback_query', 'message_reaction',
            'pre_checkout_query', 'my_chat_member'} <= set(ast.literal_eval(allowed))


@pytest.fixture
def rules(tmp_path, monkeypatch):
    path = tmp_path / 'blacklist.sqlite3'
    db = Database(str(path))
    db.init()
    db.upsert_chat(-100, 'Test', 'supergroup', None)
    db.replace_blacklist_variants(-100, 'банан', ['бананы', 'банановый', 'плохая фраза', 'ёлка'], 1)
    monkeypatch.setattr(app_bot, 'db', db, raising=False)
    monkeypatch.setattr(app_bot, 'BLACKLIST_CACHE', {})
    monkeypatch.setattr(app_bot, 'BLACKLIST_NOTICE_AT', {})
    yield db, path
    db.close()


@pytest.mark.parametrize('content', ['банан', 'БАНАНЫ!', 'это банановый сок', 'плохая\n  фраза', 'ЕЛКА', 'ба\u200bнан', 'плохая\u00a0фраза'])
def test_every_variant_and_normalized_spelling_matches(rules, content):
    msg = SimpleNamespace(text=content, caption=None, chat=SimpleNamespace(id=-100), delete=AsyncMock(), answer=AsyncMock())
    assert asyncio.run(app_bot.handle_blacklist(msg))
    msg.delete.assert_awaited_once()


def test_word_boundaries_are_preserved(rules):
    msg = SimpleNamespace(text='банановая', caption=None, chat=SimpleNamespace(id=-100), delete=AsyncMock(), answer=AsyncMock())
    assert not asyncio.run(app_bot.handle_blacklist(msg))
    msg.delete.assert_not_awaited()


def test_cache_observes_api_process_changes_immediately(rules):
    db, path = rules
    app_bot.cached_blacklist_words(-100)
    writer = Database(str(path))
    try:
        writer.replace_blacklist_variants(-100, 'новое', ['вариант'], 1)
        current = app_bot.cached_blacklist_words(-100)
        assert any(rule.word == 'новое' and 'вариант' in rule.variants for rule in current)
        writer.delete_blacklist_word(-100, 'новое')
        assert not any(rule.word == 'новое' for rule in app_bot.cached_blacklist_words(-100))
        db.add_blacklist_word(-100, 'локальное', 1)
        assert any(rule.word == 'локальное' for rule in app_bot.cached_blacklist_words(-100))
    finally:
        writer.close()


def test_all_messages_and_edits_are_checked_before_any_router(rules, monkeypatch):
    delete, answer, handler = AsyncMock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr(Message, 'delete', delete)
    monkeypatch.setattr(Message, 'answer', answer)
    async def run():
        client = Bot('123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi')
        dispatcher = Dispatcher()
        app_bot.install_blacklist_middleware(dispatcher)
        first = Router()
        async def receive(message):
            await handler(message)
        first.message.register(receive)
        first.edited_message.register(receive)
        dispatcher.include_router(first)
        try:
            for index in range(12):
                payload = {'message_id': index + 1, 'date': datetime.now(timezone.utc), 'chat': {'id': -100, 'type': 'supergroup'}, 'from': {'id': 1, 'is_bot': False, 'first_name': 'User'}}
                payload['text' if index % 2 else 'caption'] = 'бананы!'
                kind = 'edited_message' if index % 3 == 0 else 'message'
                await dispatcher.feed_update(client, Update.model_validate({'update_id': index, kind: payload}))
            assert delete.await_count == 12
            assert answer.await_count == 1
            handler.assert_not_awaited()
        finally:
            await client.session.close()
    asyncio.run(run())


def test_channel_posts_use_linked_group_blacklist(rules, monkeypatch):
    delete, answer, handler = AsyncMock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr(Message, 'delete', delete)
    monkeypatch.setattr(Message, 'answer', answer)
    monkeypatch.setattr(app_bot, 'BLACKLIST_LINKED_CHAT_CACHE', {})
    async def run():
        client = Bot('123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi')
        client.get_chat = AsyncMock(return_value=SimpleNamespace(linked_chat_id=-100))
        dispatcher = Dispatcher()
        app_bot.install_blacklist_middleware(dispatcher)
        first = Router()
        async def receive(message):
            await handler(message)
        first.channel_post.register(receive)
        first.edited_channel_post.register(receive)
        dispatcher.include_router(first)
        try:
            for index, kind in enumerate(('channel_post', 'edited_channel_post')):
                payload = {
                    'message_id': index + 1,
                    'date': datetime.now(timezone.utc),
                    'chat': {'id': -200, 'type': 'channel', 'title': 'Channel'},
                    'text': 'Вась и бананы',
                }
                await dispatcher.feed_update(client, Update.model_validate({'update_id': index, kind: payload}))
            assert delete.await_count == 2
            assert answer.await_count == 1
            handler.assert_not_awaited()
            client.get_chat.assert_awaited_once()
        finally:
            await client.session.close()
    asyncio.run(run())


def test_deletion_failure_is_logged_not_claimed_as_success(rules, caplog):
    msg = SimpleNamespace(text='банан', caption=None, chat=SimpleNamespace(id=-100), delete=AsyncMock(side_effect=TelegramForbiddenError(method=DeleteMessage(chat_id=-100, message_id=1), message='not enough rights')), answer=AsyncMock())
    assert asyncio.run(app_bot.handle_blacklist(msg))
    assert 'Blacklist deletion failed' in caplog.text
    msg.answer.assert_not_awaited()


def test_flood_limit_retries_deletion_and_notice_failure_does_not_escape(rules, monkeypatch):
    monkeypatch.setattr(app_bot.asyncio, 'sleep', AsyncMock())
    msg = SimpleNamespace(text='банан', caption=None, chat=SimpleNamespace(id=-100), delete=AsyncMock(side_effect=[TelegramRetryAfter(method=DeleteMessage(chat_id=-100, message_id=1), message='wait', retry_after=1), True]), answer=AsyncMock(side_effect=TelegramRetryAfter(method=SendMessage(chat_id=-100, text='notice'), message='wait', retry_after=1)))
    assert asyncio.run(app_bot.handle_blacklist(msg))
    assert msg.delete.await_count == 2
