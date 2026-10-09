"""Shared unmute action for the private bot menu and the web panel."""
from aiogram.types import ChatPermissions


async def unmute_member(bot, db, chat_id: int, user_id: int, actor_id: int) -> None:
    member = await bot.get_chat_member(chat_id, user_id)
    status = str(getattr(member.status, 'value', member.status))
    if status in {'kicked', 'left'}:
        raise ValueError('Пользователь заблокирован или покинул чат. Размут не снимает бан.')
    if status not in {'creator', 'administrator'}:
        agreement = db.get_chat_rule_agreement(chat_id, user_id)
        rules = db.get_chat_rules_settings(chat_id)
        if agreement and not agreement.get('agreed_at') and rules.enabled and rules.require_agreement:
            raise ValueError('Сначала пользователь должен принять правила. Размут не снимает это ограничение.')
        chat = await bot.get_chat(chat_id)
        permissions = chat.permissions
        if permissions is None:
            # Never grant pinning, chat editing or invitations as part of unmuting.
            permissions = ChatPermissions(
                can_send_messages=True, can_send_audios=True, can_send_documents=True,
                can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
                can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
                can_add_web_page_previews=True, can_react_to_messages=True,
            )
        await bot.restrict_chat_member(chat_id=chat_id, user_id=user_id,
                                       permissions=permissions, use_independent_chat_permissions=True)
    db.clear_quiet_admin(chat_id, user_id)
    db.add_moderator_action(chat_id, actor_id, user_id, 'unmute', None, '')
