import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import User

from app import bot
from app.db import Database


@pytest.fixture
def social(tmp_path, monkeypatch):
    db = Database(str(tmp_path / 'social.sqlite3'))
    db.init()
    db.upsert_chat(-100, 'Chat', 'supergroup', None)
    for uid in (1, 2, 3):
        db.upsert_seen_user(-100, uid, f'user{uid}', f'User {uid}', False)
    monkeypatch.setattr(bot, 'db', db, raising=False)
    monkeypatch.setattr(bot, 'remember_sender', AsyncMock())
    monkeypatch.setattr(bot, 'active_social_user', AsyncMock(side_effect=lambda _bot, _chat, uid: User(id=uid, first_name=f'User {uid}', is_bot=False)))
    monkeypatch.setattr(bot, 'safe_edit', AsyncMock())
    yield db
    db.close()


def message(text, uid=1, reply=None):
    return SimpleNamespace(text=text, from_user=User(id=uid, first_name=f'User {uid}', is_bot=False), chat=SimpleNamespace(id=-100, type='supergroup'), reply_to_message=reply, bot=object(), answer=AsyncMock())


def callback(action, uid):
    return SimpleNamespace(data=f'soc:{action}:-100:1:2', from_user=SimpleNamespace(id=uid), message=message(''), bot=object(), answer=AsyncMock())


@pytest.mark.parametrize('text,reply', [('пара @user2', None), ('/pair 2', None), ('пара', SimpleNamespace(from_user=User(id=2, first_name='Second', is_bot=False)))])
def test_proposal_commands_require_consent(social, text, reply):
    msg = message(text, reply=reply)
    asyncio.run(bot.relationship_command(msg))
    assert social.couple_state(-100, 1, 2) == 'outgoing'
    assert social.get_chat_couple(-100, 1) is None
    buttons = msg.answer.call_args.kwargs['reply_markup'].inline_keyboard
    assert any(button.callback_data.startswith('soc:pa:') for row in buttons for button in row)


def test_only_recipient_can_accept_and_double_click_is_safe(social):
    social.create_couple_request(-100, 1, 2)
    asyncio.run(bot.cb_social_action(callback('pa', 3)))
    assert social.get_chat_couple(-100, 1) is None
    asyncio.run(bot.cb_social_action(callback('pa', 1)))
    assert social.get_chat_couple(-100, 1) is None
    asyncio.run(bot.cb_social_action(callback('pa', 2)))
    asyncio.run(bot.cb_social_action(callback('pa', 2)))
    assert social.get_chat_partner(-100, 1).user_id == 2
    assert social._conn.execute('select count(*) from chat_couples').fetchone()[0] == 1


def test_cancel_is_sender_only_and_prevents_acceptance(social):
    social.create_couple_request(-100, 1, 2)
    asyncio.run(bot.cb_social_action(callback('pc', 2)))
    assert social.couple_state(-100, 1, 2) == 'outgoing'
    asyncio.run(bot.cb_social_action(callback('pc', 1)))
    assert social.accept_couple_request(-100, 1, 2) == 'missing'


def test_expired_request_cannot_be_accepted_and_can_be_renewed(social):
    social.create_couple_request(-100, 1, 2)
    old = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat(timespec='seconds')
    social._conn.execute('update chat_couple_requests set created_at=?', (old,))
    social._conn.commit()
    assert social.list_couple_requests(-100, 2) == []
    assert social.accept_couple_request(-100, 1, 2) == 'missing'
    assert social.create_couple_request(-100, 1, 2) == 'created'


def test_breakup_requires_confirmation_and_works_after_partner_leaves(social, monkeypatch):
    social.create_couple_request(-100, 1, 2)
    social.accept_couple_request(-100, 1, 2)
    asyncio.run(bot.relationship_command(message('расстаться')))
    assert social.get_chat_couple(-100, 1)
    monkeypatch.setattr(bot, 'active_social_user', AsyncMock(return_value=None))
    asyncio.run(bot.cb_social_action(callback('px', 3)))
    assert social.get_chat_couple(-100, 1)
    asyncio.run(bot.cb_social_action(callback('px', 1)))
    assert social.get_chat_couple(-100, 1) is None
    assert social.friendship_state(-100, 1, 2) == 'friends'


def test_self_and_bot_proposals_rejected(social, monkeypatch):
    asyncio.run(bot.relationship_command(message('пара 1')))
    monkeypatch.setattr(bot, 'active_social_user', AsyncMock(return_value=User(id=2, first_name='Bot', is_bot=True)))
    asyncio.run(bot.relationship_command(message('пара 2')))
    assert social.list_couple_requests(-100, 1) == []


def test_relationship_commands_are_in_help():
    assert 'пара @ник' in bot.chat_help_text()
    assert 'расстаться' in bot.chat_help_text()
