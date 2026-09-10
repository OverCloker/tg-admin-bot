import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import bot as game
from app import miniapp
from app.mine_access import can_use_mine_in_chat, has_mine_access, user_is_active_chat_member


class FakeBot:
    def __init__(self, members):
        self.members = members

    async def get_me(self):
        return SimpleNamespace(id=999)

    async def get_chat_member(self, chat_id, user_id):
        status, is_member, is_bot = self.members[(chat_id, user_id)]
        return SimpleNamespace(
            status=status,
            is_member=is_member,
            user=SimpleNamespace(is_bot=is_bot),
        )


def test_mine_requires_bot_admin_and_active_user_membership() -> None:
    user_id = 42
    bot = FakeBot({(-100, 999): ("member", True, True), (-100, user_id): ("member", True, False)})
    assert asyncio.run(can_use_mine_in_chat(bot, -100, user_id)) is False

    bot.members[(-100, 999)] = ("administrator", True, True)
    assert asyncio.run(can_use_mine_in_chat(bot, -100, user_id)) is True

    bot.members[(-100, user_id)] = ("left", False, False)
    assert asyncio.run(can_use_mine_in_chat(bot, -100, user_id)) is False


def test_private_mine_access_accepts_any_eligible_registered_group() -> None:
    user_id = 42
    bot = FakeBot(
        {
            (-100, 999): ("member", True, True),
            (-200, 999): ("administrator", True, True),
            (-200, user_id): ("restricted", True, False),
        }
    )
    chats = [SimpleNamespace(chat_id=-100), SimpleNamespace(chat_id=-200)]
    assert asyncio.run(has_mine_access(bot, chats, user_id)) is True

    bot.members[(-200, user_id)] = ("restricted", False, False)
    assert asyncio.run(user_is_active_chat_member(bot, -200, user_id)) is False
    assert asyncio.run(has_mine_access(bot, chats, user_id)) is False


def test_miniapp_mine_guard_denies_and_caches_failed_check(monkeypatch) -> None:
    calls = []

    async def denied(user_id):
        calls.append(user_id)
        return False

    monkeypatch.setattr(miniapp, "_check_miniapp_mine_access", denied)
    miniapp.MINE_ACCESS_CACHE.clear()

    for _ in range(2):
        with pytest.raises(HTTPException) as error:
            miniapp._ensure_miniapp_mine_access(42)
        assert error.value.status_code == 403
    assert calls == [42]


def test_dig_command_stops_before_registration_when_access_is_denied(monkeypatch) -> None:
    replies = []

    class FakeDb:
        def get_dig_block(self, _user_id):
            return None

    class FakeMessage:
        from_user = SimpleNamespace(id=42, username="miner", full_name="Miner")
        chat = SimpleNamespace(id=-100, type="supergroup")
        bot = object()

    async def denied(_bot, _user_id, _chat_id=0):
        return False

    async def reply(_message, text, *args, **kwargs):
        replies.append(text)

    monkeypatch.setattr(game, "db", FakeDb(), raising=False)
    monkeypatch.setattr(game, "can_user_use_mine", denied)
    monkeypatch.setattr(game, "temporary_reply", reply)

    asyncio.run(game.dig_command(FakeMessage()))

    assert replies == [game.MINE_ACCESS_DENIED_TEXT]
