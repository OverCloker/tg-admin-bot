import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import pytest
from aiogram.types import ChatPermissions
from app.quiet_actions import unmute_member


def setup(status='restricted', pending=False):
    permissions = ChatPermissions(can_send_messages=True, can_send_other_messages=False, can_invite_users=False)
    bot = SimpleNamespace(get_chat_member=AsyncMock(return_value=SimpleNamespace(status=status)),
                          get_chat=AsyncMock(return_value=SimpleNamespace(permissions=permissions)),
                          restrict_chat_member=AsyncMock())
    db = Mock()
    db.get_chat_rule_agreement.return_value = {'agreed_at': None} if pending else None
    db.get_chat_rules_settings.return_value = SimpleNamespace(enabled=True, require_agreement=True)
    return bot, db, permissions


def test_unmute_preserves_default_group_permissions():
    bot, db, permissions = setup()
    asyncio.run(unmute_member(bot, db, -100, 42, 1))
    assert bot.restrict_chat_member.await_args.kwargs['permissions'] is permissions
    assert bot.restrict_chat_member.await_args.kwargs['use_independent_chat_permissions'] is True
    db.clear_quiet_admin.assert_called_once_with(-100, 42)
    db.add_moderator_action.assert_called_once_with(-100, 1, 42, 'unmute', None, '')


@pytest.mark.parametrize('status', ['administrator', 'creator'])
def test_unmute_admin_removes_only_internal_quiet_mode(status):
    bot, db, _ = setup(status)
    asyncio.run(unmute_member(bot, db, -100, 42, 1))
    bot.restrict_chat_member.assert_not_awaited()
    db.clear_quiet_admin.assert_called_once()


@pytest.mark.parametrize('status,pending', [('kicked', False), ('left', False), ('restricted', True)])
def test_unmute_does_not_unban_or_bypass_rules(status, pending):
    bot, db, _ = setup(status, pending)
    with pytest.raises(ValueError):
        asyncio.run(unmute_member(bot, db, -100, 42, 1))
    bot.restrict_chat_member.assert_not_awaited()
    db.clear_quiet_admin.assert_not_called()


def test_failed_telegram_unmute_retains_internal_state():
    bot, db, _ = setup()
    bot.restrict_chat_member.side_effect = RuntimeError('network unavailable')
    with pytest.raises(RuntimeError):
        asyncio.run(unmute_member(bot, db, -100, 42, 1))
    db.clear_quiet_admin.assert_not_called()


def test_unmute_present_in_both_menus():
    from app.keyboards import quiet_menu
    from app import admin_api, bot
    assert 'quiet:unmute:-100' in [b.callback_data for row in quiet_menu(-100, False).inline_keyboard for b in row]
    assert 'quietUnmute()' in admin_api.ADMIN_PANEL_HTML
    assert 'quiet.unmute' in bot.ADMIN_PERMISSION_IDS
    assert bot.STATE_FEATURES['set_quiet_unmute'] == 'quiet.unmute'
