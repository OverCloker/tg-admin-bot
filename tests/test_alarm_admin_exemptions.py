import asyncio
from types import SimpleNamespace

import app.bot as bot_module


ACTIVE_ALARM_RUNTIME = (True, True, "A", True)


class FakeMessage:
    def __init__(self, user_id: int | None = 42) -> None:
        self.bot = object()
        self.chat = SimpleNamespace(id=-100, type="supergroup")
        self.from_user = SimpleNamespace(id=user_id) if user_id is not None else None
        self.deleted = False

    async def delete(self) -> None:
        self.deleted = True


class FakeReactionBot:
    def __init__(self) -> None:
        self.deleted_reactions: list[dict] = []

    async def delete_message_reaction(self, **kwargs) -> None:
        self.deleted_reactions.append(kwargs)


class FakeQuietDb:
    def get_active_quiet_admin(self, chat_id, user_id, now):
        return None


def test_alarm_does_not_delete_admin_single_emoji(monkeypatch) -> None:
    async def fake_is_chat_admin(bot, chat_id, user_id):
        return True

    monkeypatch.setattr(bot_module, "cached_alarm_runtime", lambda chat_id: ACTIVE_ALARM_RUNTIME)
    monkeypatch.setattr(bot_module, "is_chat_admin", fake_is_chat_admin)

    message = FakeMessage()
    result = asyncio.run(bot_module.delete_single_emoji_during_alarm(message))

    assert result is False
    assert message.deleted is False


def test_alarm_deletes_member_single_emoji(monkeypatch) -> None:
    async def fake_is_chat_admin(bot, chat_id, user_id):
        return False

    monkeypatch.setattr(bot_module, "cached_alarm_runtime", lambda chat_id: ACTIVE_ALARM_RUNTIME)
    monkeypatch.setattr(bot_module, "is_chat_admin", fake_is_chat_admin)

    message = FakeMessage()
    result = asyncio.run(bot_module.delete_single_emoji_during_alarm(message))

    assert result is True
    assert message.deleted is True


def test_alarm_does_not_delete_admin_reaction(monkeypatch) -> None:
    async def fake_is_chat_admin(bot, chat_id, user_id):
        return True

    monkeypatch.setattr(bot_module, "cached_alarm_runtime", lambda chat_id: ACTIVE_ALARM_RUNTIME)
    monkeypatch.setattr(bot_module, "is_chat_admin", fake_is_chat_admin)
    monkeypatch.setattr(bot_module, "db", FakeQuietDb(), raising=False)

    bot = FakeReactionBot()
    event = SimpleNamespace(
        chat=SimpleNamespace(id=-100, type="supergroup"),
        user=SimpleNamespace(id=42),
        actor_chat=None,
        message_id=777,
        new_reaction=[SimpleNamespace(type="emoji", emoji="👍")],
    )

    asyncio.run(bot_module.delete_reactions_during_alarm(event, bot))

    assert bot.deleted_reactions == []


def test_alarm_deletes_member_reaction(monkeypatch) -> None:
    async def fake_is_chat_admin(bot, chat_id, user_id):
        return False

    monkeypatch.setattr(bot_module, "cached_alarm_runtime", lambda chat_id: ACTIVE_ALARM_RUNTIME)
    monkeypatch.setattr(bot_module, "is_chat_admin", fake_is_chat_admin)
    monkeypatch.setattr(bot_module, "db", FakeQuietDb(), raising=False)

    bot = FakeReactionBot()
    event = SimpleNamespace(
        chat=SimpleNamespace(id=-100, type="supergroup"),
        user=SimpleNamespace(id=42),
        actor_chat=None,
        message_id=777,
        new_reaction=[SimpleNamespace(type="emoji", emoji="👍")],
    )

    asyncio.run(bot_module.delete_reactions_during_alarm(event, bot))

    assert bot.deleted_reactions == [
        {"chat_id": -100, "message_id": 777, "user_id": 42, "actor_chat_id": None}
    ]


def test_alarm_apply_does_not_disable_reactions_globally(monkeypatch) -> None:
    class FakeDb:
        def get_alarm_settings(self, chat_id):
            return SimpleNamespace(permissions_json="{}", reactions_json=None)

    class FakeBot:
        async def set_chat_permissions(self, **kwargs) -> None:
            pass

    async def fail_set_reactions(bot, chat_id, reactions):
        raise AssertionError("alarm must not disable reactions globally")

    monkeypatch.setattr(bot_module, "db", FakeDb(), raising=False)
    monkeypatch.setattr(bot_module, "set_chat_available_reactions", fail_set_reactions)

    asyncio.run(bot_module.apply_alarm_restrictions(FakeBot(), -100))
