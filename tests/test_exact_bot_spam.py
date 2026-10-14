import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import BanChatMember

from app import bot


def message(text="@psikh_lightbot"):
    return SimpleNamespace(
        text=text, caption=None, entities=[], caption_entities=[],
        chat=SimpleNamespace(id=-100, type="supergroup"),
        from_user=SimpleNamespace(id=9), sender_chat=None, is_automatic_forward=False,
        bot=SimpleNamespace(id=123, get_chat_member=AsyncMock(return_value=SimpleNamespace(status="member")),
                            ban_chat_member=AsyncMock(), ban_chat_sender_chat=AsyncMock()),
        delete=AsyncMock(),
    )


@pytest.mark.parametrize("text", [
    "прошла тест @psikh_lightbot", "тест @myppsychologybot", "@psohmarybot", "@psumarybot",
    "@PSUMARYBOT!", "https://t.me/psumarybot?start=test", "telegram.me/myppsychologybot",
])
def test_exact_matches(text):
    assert bot.exact_ad_bot_match(message(text)) in bot.BLOCKED_AD_BOTS


@pytest.mark.parametrize("text", [
    "эта тревога мне знакома", "@otherbot", "@psumarybot_extra", "@psumarybot123",
    "https://evil.t.me/psumarybot", "https://example.com/t.me/psumarybot",
])
def test_no_general_pattern_or_prefix_matches(text):
    assert bot.exact_ad_bot_match(message(text)) is None


def test_caption_and_hidden_link():
    msg = message(None)
    msg.caption = "@psohmarybot"
    assert bot.exact_ad_bot_match(msg) == "psohmarybot"
    msg.caption = "Пройди тест"
    msg.caption_entities = [SimpleNamespace(url="https://t.me/psikh_lightbot")]
    assert bot.exact_ad_bot_match(msg) == "psikh_lightbot"


@pytest.mark.parametrize("sender_channel", [False, True])
def test_ban_and_source_deletion(monkeypatch, sender_channel):
    msg = message()
    if sender_channel:
        msg.sender_chat = SimpleNamespace(id=-200)
    monkeypatch.setattr(bot, "notify_staff_moderation", AsyncMock())
    assert asyncio.run(bot.handle_exact_bot_spam(msg))
    msg.delete.assert_awaited_once()
    if sender_channel:
        msg.bot.ban_chat_sender_chat.assert_awaited_once_with(chat_id=-100, sender_chat_id=-200)
    else:
        msg.bot.ban_chat_member.assert_awaited_once_with(chat_id=-100, user_id=9)


@pytest.mark.parametrize("exemption", ["admin", "anonymous", "self", "forward", "private"])
def test_exemptions(exemption):
    msg = message()
    if exemption == "admin":
        msg.bot.get_chat_member.return_value.status = "administrator"
    elif exemption == "anonymous":
        msg.sender_chat = SimpleNamespace(id=-100)
    elif exemption == "self":
        msg.from_user.id = 123
    elif exemption == "forward":
        msg.is_automatic_forward = True
    else:
        msg.chat.type = "private"
    assert not asyncio.run(bot.handle_exact_bot_spam(msg))
    msg.delete.assert_not_awaited()
    msg.bot.ban_chat_member.assert_not_awaited()


def test_delete_even_if_ban_fails(monkeypatch):
    msg = message()
    msg.bot.ban_chat_member.side_effect = TelegramForbiddenError(
        method=BanChatMember(chat_id=-100, user_id=9), message="missing permissions",
    )
    monkeypatch.setattr(bot, "notify_staff_moderation", AsyncMock())
    assert asyncio.run(bot.handle_exact_bot_spam(msg))
    msg.delete.assert_awaited_once()


def test_unknown_admin_status_is_not_banned(monkeypatch):
    msg = message()
    msg.bot.get_chat_member.side_effect = TelegramForbiddenError(
        method=BanChatMember(chat_id=-100, user_id=9), message="unavailable",
    )
    monkeypatch.setattr(bot, "notify_staff_moderation", AsyncMock())
    assert asyncio.run(bot.handle_exact_bot_spam(msg))
    msg.delete.assert_awaited_once()
    msg.bot.ban_chat_member.assert_not_awaited()


@pytest.mark.parametrize("text,username", [
    ("Я проходила тест в @psykhodreambot и он помог понять тревогу", "psykhodreambot"),
    ("Недавно проходила тест у @pszch_larybot и была поражена", "pszch_larybot"),
    ("Тест у @psihology_marybot описал мой внутренний мир", "psihology_marybot"),
    ("Недавно проходила тест в @my_psycoseedbot", "my_psycoseedbot"),
])
def test_reported_ad_bots_are_banned_and_deleted(monkeypatch, text, username):
    msg = message(text)
    monkeypatch.setattr(bot, "notify_staff_moderation", AsyncMock())
    assert bot.exact_ad_bot_match(msg) == username
    assert asyncio.run(bot.handle_exact_bot_spam(msg))
    msg.bot.ban_chat_member.assert_awaited_once_with(chat_id=-100, user_id=9)
    msg.delete.assert_awaited_once()


@pytest.mark.parametrize("text,username", [
    ("Когда тревога накрывает, я проходила тест в @newmindseedbot, помог понять себя", "newmindseedbot"),
    ("При панике попробуй пройти тест по ссылке https://t.me/anotherpsybot?start=ad, мне помог", "anotherpsybot"),
    ("Переживания сильные. Недавно проходила тест у @future_helperbot и он помог", "future_helperbot"),
])
def test_rotating_ad_bot_pattern_bans_and_deletes(monkeypatch, text, username):
    msg = message(text)
    monkeypatch.setattr(bot, "notify_staff_moderation", AsyncMock())
    assert bot.exact_ad_bot_match(msg) == username
    assert asyncio.run(bot.handle_exact_bot_spam(msg))
    msg.bot.ban_chat_member.assert_awaited_once_with(chat_id=-100, user_id=9)
    msg.delete.assert_awaited_once()


@pytest.mark.parametrize("text", [
    "У меня тревога, кто знает хороший тест?",
    "Я проходила тест на тревогу, мне помог разобраться",
    "@newmindseedbot прислал обновление",
    "Тест у @newmindseedbot был скучным",
    "При панике мне помог тест у @human_contact, не у бота",
])
def test_pattern_does_not_ban_context_without_promotion(text):
    assert bot.exact_ad_bot_match(message(text)) is None
