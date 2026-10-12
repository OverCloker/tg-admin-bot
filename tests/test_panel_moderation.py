import asyncio
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import pytest
from fastapi import HTTPException
from app import admin_api as api


def setup(monkeypatch, status):
    member=SimpleNamespace(status=status,user=SimpleNamespace(id=42,username='target',full_name='Target'))
    bot=SimpleNamespace(id=99,get_chat_member=AsyncMock(side_effect=lambda chat,user: SimpleNamespace(can_delete_messages=True) if user==99 else member),ban_chat_member=AsyncMock(),unban_chat_member=AsyncMock(),session=SimpleNamespace(close=AsyncMock()))
    db=Mock()
    monkeypatch.setattr(api,'open_db',lambda:nullcontext(db))
    monkeypatch.setattr(api,'create_bot',lambda *a,**k:bot)
    monkeypatch.setattr(api,'load_config',lambda:None)
    monkeypatch.setattr(api,'require_chat',Mock())
    monkeypatch.setattr(api,'require_admin_feature',Mock())
    monkeypatch.setattr(api,'current_actor_id',lambda:1)
    monkeypatch.setattr(api,'resolve_quiet_target',AsyncMock(return_value=(42,'Target')))
    return bot,db


@pytest.mark.parametrize('action,status',[('admin','administrator'),('ban','member'),('unban','kicked')])
def test_allowed_actions(monkeypatch,action,status):
    bot,db=setup(monkeypatch,status)
    payload=api.QuietManualPayload(target='42',minutes=60,reason='test')
    asyncio.run(api.perform_panel_moderation(-100,payload,action))
    api.require_admin_feature.assert_called_once_with(db,'quiet.'+action)
    db.add_moderator_action.assert_called_once()
    bot.session.close.assert_awaited_once()
    if action=='admin':
        db.set_quiet_admin.assert_called_once()
        bot.ban_chat_member.assert_not_awaited()
    if action=='unban':
        bot.unban_chat_member.assert_awaited_once_with(chat_id=-100,user_id=42,only_if_banned=True)


@pytest.mark.parametrize('action,status',[('admin','creator'),('admin','member'),('ban','administrator'),('ban','creator'),('unban','member')])
def test_protected_targets(monkeypatch,action,status):
    bot,db=setup(monkeypatch,status)
    with pytest.raises(HTTPException):
        asyncio.run(api.perform_panel_moderation(-100,api.QuietManualPayload(target='42',minutes=60),action))
    db.set_quiet_admin.assert_not_called()
    db.add_moderator_action.assert_not_called()
    bot.ban_chat_member.assert_not_awaited()
    bot.unban_chat_member.assert_not_awaited()


@pytest.mark.parametrize('action',['admin','ban','unban'])
def test_denied_access_has_no_telegram_side_effects(monkeypatch,action):
    bot,db=setup(monkeypatch,'member')
    api.require_admin_feature.side_effect=HTTPException(403,'denied')
    with pytest.raises(HTTPException):
        asyncio.run(api.perform_panel_moderation(-100,api.QuietManualPayload(target='42',minutes=60),action))
    api.resolve_quiet_target.assert_not_awaited()
    bot.get_chat_member.assert_not_awaited()


def test_access_catalogs_match():
    from app import bot
    for key in ['quiet.admin','quiet.ban','quiet.unban']:
        assert key in api.ADMIN_PERMISSION_IDS and key in bot.ADMIN_PERMISSION_IDS
        assert f'canWrite("{key}")' in api.ADMIN_PANEL_HTML
