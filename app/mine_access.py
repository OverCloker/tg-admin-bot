"""Live Telegram access checks for the mine.

Database registrations are deliberately not enough here: a user keeps a player
record after leaving a chat, and a registered chat may remain after the bot loses
administrator rights.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError


MINE_ACCESS_DENIED_TEXT = (
    "Шахта доступна только участникам групп, где бот назначен администратором."
)
_BOT_ADMIN_STATUSES = {"creator", "administrator"}
_ACTIVE_MEMBER_STATUSES = {"creator", "administrator", "member", "restricted"}
_TELEGRAM_ACCESS_ERRORS = (TelegramAPIError,)


def _status_text(value: Any) -> str:
    status = getattr(value, "value", value)
    return str(status).strip().lower()


async def bot_is_chat_admin(bot: Bot, chat_id: int, *, bot_user_id: int | None = None) -> bool:
    """Return whether the current bot is an administrator of ``chat_id``."""
    try:
        if bot_user_id is None:
            bot_user_id = int((await bot.get_me()).id)
        member = await bot.get_chat_member(int(chat_id), int(bot_user_id))
    except _TELEGRAM_ACCESS_ERRORS:
        return False
    return _status_text(member.status) in _BOT_ADMIN_STATUSES


async def user_is_active_chat_member(bot: Bot, chat_id: int, user_id: int) -> bool:
    """Return whether a non-bot user currently belongs to ``chat_id``."""
    try:
        member = await bot.get_chat_member(int(chat_id), int(user_id))
    except _TELEGRAM_ACCESS_ERRORS:
        return False
    status = _status_text(member.status)
    if status not in _ACTIVE_MEMBER_STATUSES:
        return False
    if status == "restricted" and getattr(member, "is_member", True) is False:
        return False
    return not bool(getattr(member.user, "is_bot", False))


async def can_use_mine_in_chat(bot: Bot, chat_id: int, user_id: int) -> bool:
    """Check both sides of the mine access rule for one registered group."""
    try:
        bot_user_id = int((await bot.get_me()).id)
    except _TELEGRAM_ACCESS_ERRORS:
        return False
    if not await bot_is_chat_admin(bot, chat_id, bot_user_id=bot_user_id):
        return False
    return await user_is_active_chat_member(bot, chat_id, user_id)


async def has_mine_access(bot: Bot, chats: Iterable[Any], user_id: int) -> bool:
    """Check access through any registered group where the bot is an admin."""
    try:
        bot_user_id = int((await bot.get_me()).id)
    except _TELEGRAM_ACCESS_ERRORS:
        return False
    for chat in chats:
        chat_id = int(getattr(chat, "chat_id", chat))
        if not await bot_is_chat_admin(bot, chat_id, bot_user_id=bot_user_id):
            continue
        if await user_is_active_chat_member(bot, chat_id, user_id):
            return True
    return False
