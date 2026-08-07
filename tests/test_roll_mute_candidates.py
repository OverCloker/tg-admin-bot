import asyncio
from types import SimpleNamespace

import pytest

import app.bot as bot_module
from app.bot import current_roll_mute_target_member
from app.db import Database


class FakeBot:
    def __init__(self, member):
        self.member = member

    async def get_chat_member(self, chat_id, user_id):
        return self.member


def _member(status: str, user_id: int = 42, username: str | None = "fresh"):
    return SimpleNamespace(
        status=status,
        user=SimpleNamespace(
            id=user_id,
            username=username,
            full_name="Fresh User",
            is_bot=False,
        ),
    )


@pytest.fixture()
def roll_db(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()
    db.upsert_chat(-100, "Chat", "supergroup", None)
    db.upsert_seen_user(-100, 42, "oldname", "Old User", False)
    monkeypatch.setattr(bot_module, "db", db, raising=False)
    return db


def test_roll_mute_refreshes_changed_username(roll_db) -> None:
    member = asyncio.run(current_roll_mute_target_member(FakeBot(_member("member", username="freshname")), -100, 42))

    assert member is not None
    user = roll_db.get_seen_user_by_username(-100, "freshname")
    assert user is not None
    assert user.user_id == 42
    assert roll_db.get_seen_user_by_username(-100, "oldname") is None


def test_roll_mute_removes_left_user_from_pickable_cache(roll_db) -> None:
    member = asyncio.run(current_roll_mute_target_member(FakeBot(_member("left", username="oldname")), -100, 42))

    assert member is None
    assert [user.user_id for user in roll_db.list_pickable_users(-100)] == []
