from app import bot


def test_only_the_highest_rank_bonus_is_applied() -> None:
    items = {"rank_1": 1, "rank_2": 1, "rank_3": 1}

    assert bot.dig_rank_bonuses(items) == {"coins": 15, "chance": 1, "luck_regen": 2}


def test_rank_coin_bonus_is_not_stacked() -> None:
    effects: list[str] = []

    result = bot.apply_dig_rank_coin_bonus({"rank_1": 1, "rank_4": 1}, 100, effects)

    assert result == 120
    assert effects == ["Ранг: +20% котоинов"]


def test_golden_ticket_chance_is_five_percent_per_completed_meter(monkeypatch) -> None:
    monkeypatch.setattr(bot.secrets, "randbelow", lambda _: 49)
    assert bot.find_golden_ticket(10) is True

    monkeypatch.setattr(bot.secrets, "randbelow", lambda _: 50)
    assert bot.find_golden_ticket(10) is False

    monkeypatch.setattr(bot.secrets, "randbelow", lambda _: 4)
    assert bot.find_golden_ticket(1) is True

    monkeypatch.setattr(bot.secrets, "randbelow", lambda _: 5)
    assert bot.find_golden_ticket(1) is False
