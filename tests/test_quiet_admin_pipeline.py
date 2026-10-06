import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message, Update

from app import bot as bot_module
from app.db import Database


@pytest.fixture
def quiet_db(tmp_path, monkeypatch):
    service = Database(str(tmp_path / 'bot.sqlite3'))
    service.init()
    service.set_quiet_admin(
        chat_id=-100, user_id=42, username='quiet_admin', full_name='Admin',
        reason='test', until_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        created_by=1,
    )
    monkeypatch.setattr(bot_module, 'db', service, raising=False)
    yield service
    service.close()


@pytest.mark.parametrize('earlier_handler', [False, True])
def test_quiet_admin_deletes_media_even_without_matching_router(quiet_db, monkeypatch, earlier_handler):
    delete, handler = AsyncMock(), AsyncMock()
    monkeypatch.setattr(Message, 'delete', delete)

    async def run():
        client = Bot('123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi')
        dispatcher = Dispatcher()
        bot_module.install_quiet_admin_middleware(dispatcher)
        if earlier_handler:
            staff = Router()
            async def receive(message):
                await handler(message)
            staff.message.register(receive)
            staff.edited_message.register(receive)
            dispatcher.include_router(staff)
        common_file = {'file_id': 'file', 'file_unique_id': 'unique'}
        contents = [
            {'sticker': {**common_file, 'type': 'regular', 'width': 512, 'height': 512,
                         'is_animated': False, 'is_video': False}},
            {'sticker': {**common_file, 'type': 'regular', 'width': 512, 'height': 512,
                         'is_animated': True, 'is_video': False}},
            {'photo': [{**common_file, 'width': 100, 'height': 100}]},
            {'animation': {**common_file, 'width': 100, 'height': 100, 'duration': 1}},
            {'voice': {**common_file, 'duration': 1}},
            {'document': common_file},
            {'text': 'message'},
        ]
        try:
            for index, content in enumerate(contents):
                payload = {'message_id': index + 1, 'date': datetime.now(timezone.utc),
                           'chat': {'id': -100, 'type': 'supergroup'},
                           'from': {'id': 42, 'is_bot': False, 'first_name': 'Admin'}, **content}
                await dispatcher.feed_update(client, Update.model_validate({
                    'update_id': index, 'message': payload,
                }))
            await dispatcher.feed_update(client, Update.model_validate({
                'update_id': len(contents), 'edited_message': {**payload, 'text': 'edited'},
            }))
            assert delete.await_count == len(contents) + 1
            handler.assert_not_awaited()
        finally:
            await client.session.close()
    asyncio.run(run())


def test_quiet_admin_does_not_delete_after_expiry_or_for_other_users(quiet_db, monkeypatch):
    delete, handler = AsyncMock(), AsyncMock()
    monkeypatch.setattr(Message, 'delete', delete)
    quiet_db.set_quiet_admin(
        chat_id=-100, user_id=43, username='expired_admin', full_name='Expired',
        reason='test', until_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        created_by=1,
    )

    async def run():
        client = Bot('123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi')
        dispatcher = Dispatcher()
        bot_module.install_quiet_admin_middleware(dispatcher)
        async def receive(message):
            await handler(message)
        dispatcher.message.register(receive)
        try:
            for user_id in [43, 44]:
                await dispatcher.feed_update(client, Update.model_validate({
                    'update_id': user_id, 'message': {
                        'message_id': user_id, 'date': datetime.now(timezone.utc),
                        'chat': {'id': -100, 'type': 'supergroup'},
                        'from': {'id': user_id, 'is_bot': False, 'first_name': 'User'},
                        'sticker': {'file_id': 'file', 'file_unique_id': 'unique', 'type': 'regular',
                                    'width': 512, 'height': 512, 'is_animated': False, 'is_video': False},
                    },
                }))
            delete.assert_not_awaited()
            assert handler.await_count == 2
        finally:
            await client.session.close()
    asyncio.run(run())
