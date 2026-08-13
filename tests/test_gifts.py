import asyncio
from types import SimpleNamespace

from app import bot as bot_module


class FakeState:
    def __init__(self) -> None:
        self.cleared = 0
        self.state = None
        self.data = {}

    async def clear(self) -> None:
        self.cleared += 1
        self.state = None
        self.data.clear()

    async def set_state(self, state) -> None:
        self.state = state

    async def update_data(self, **kwargs) -> None:
        self.data.update(kwargs)

    async def get_data(self):
        return dict(self.data)


def test_gift_command_is_bot_admin_only(monkeypatch) -> None:
    answers: list[str] = []

    class FakeBot:
        async def get_available_gifts(self):
            raise AssertionError("ordinary users must not load gifts")

    class FakeMessage:
        bot = FakeBot()
        from_user = SimpleNamespace(id=7, username="user", full_name="User")
        text = "/gift"
        reply_to_message = None

        async def answer(self, text, **_kwargs):
            answers.append(text)

    monkeypatch.setattr(bot_module, "is_bot_admin", lambda user_id: False)

    asyncio.run(bot_module.start_gift_flow(FakeMessage(), FakeState()))

    assert answers == ["Команда /gift доступна только администраторам бота."]


def test_gift_confirm_is_not_sent_twice(monkeypatch) -> None:
    sent_gifts: list[tuple[int, str]] = []
    edits: list[str] = []
    answers: list[str] = []
    token = "gift-token"
    flow = bot_module.GiftFlow(
        token=token,
        admin_id=42,
        created_at=bot_module.time.monotonic(),
        gifts=[bot_module.GiftSummary(gift_id="gift-1", star_count=5, emoji="🎁", title="🎁 · 5 ⭐")],
        selected_gift_id="gift-1",
        recipient_id=1001,
        recipient_label="@target / 1001",
    )

    class FakeBot:
        async def get_available_gifts(self):
            gift = SimpleNamespace(
                id="gift-1",
                star_count=5,
                sticker=SimpleNamespace(emoji="🎁", file_id="sticker-file"),
                remaining_count=None,
                total_count=None,
                upgrade_star_count=None,
                is_premium=False,
            )
            return SimpleNamespace(gifts=[gift])

        async def send_gift(self, *, user_id: int, gift_id: str):
            sent_gifts.append((user_id, gift_id))
            return True

    class FakeCallback:
        data = f"gift:send:{token}"
        from_user = SimpleNamespace(id=42)
        bot = FakeBot()
        message = SimpleNamespace()

        async def answer(self, text=None, **_kwargs):
            answers.append(text or "")

    async def fake_safe_edit(_callback, text, **_kwargs):
        edits.append(text)

    async def fake_bot_star_balance(_bot):
        return SimpleNamespace(amount=20, nanostar_amount=None)

    bot_module.GIFT_SELECTIONS.clear()
    bot_module.GIFT_CONFIRM_IN_PROGRESS.clear()
    bot_module.GIFT_COMPLETED.clear()
    bot_module.GIFT_SELECTIONS[token] = flow
    monkeypatch.setattr(bot_module, "is_bot_admin", lambda user_id: user_id == 42)
    monkeypatch.setattr(bot_module, "safe_edit", fake_safe_edit)
    monkeypatch.setattr(bot_module, "bot_star_balance", fake_bot_star_balance)

    callback = FakeCallback()
    state = FakeState()
    asyncio.run(bot_module.cb_gift_send(callback, state))
    asyncio.run(bot_module.cb_gift_send(callback, state))

    assert sent_gifts == [(1001, "gift-1")]
    assert any("Подарок отправлен" in item for item in edits)
    assert answers[-1] == "Этот подарок уже был отправлен."
