from app import bot
from app.db import Database
from app.miniapp import _shop_catalog


def test_rank_discount_applies_only_to_consumable_items() -> None:
    items = {"rank_4": 1}

    assert bot.dig_rank_discount(items) == 20
    assert bot.dig_shop_price("tea", items) == 32
    assert bot.dig_shop_price("shovel_1", items) == 250
    assert bot.dig_shop_price("golden_ticket", items) == 1500


def test_shift_contract_has_no_standard_contract_xp() -> None:
    assert bot.dig_contract_xp_reward(["Сменное задание «Смена» выполнено: +80 котоинов"]) == 0
    assert bot.dig_contract_xp_reward(["Контракт «Глубина» выполнен: +60 котоинов, +40 XP"]) == 40


def test_dig_effects_text_does_not_duplicate_paid_special_items() -> None:
    text = bot.dig_effects_text({"super_mute30": 1, "super_tag": 1})

    assert text.count("Право на мут 30 минут x1") == 1
    assert text.count("Право выбрать тег x1") == 1


def test_shop_catalog_returns_discounted_server_price(tmp_path) -> None:
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()
    db.register_dig_player(0, 7, "miner", "Miner")
    db.add_dig_item(0, 7, "rank_2", 1)

    try:
        catalog = _shop_catalog(db, 7)
    finally:
        db.close()

    products = {
        item["key"]: item
        for category in catalog["categories"]
        for item in category["items"]
    }
    assert products["tea"]["price"] == 36
    assert products["tea"]["discount"] == 10
    assert products["shovel_1"]["price"] == 250
    assert products["shovel_1"]["discount"] == 0


def test_weekly_ranking_keeps_only_players_with_ranks(tmp_path) -> None:
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()
    db.register_dig_player(0, 1, "ranked", "Ranked")
    db.register_dig_player(0, 2, "newbie", "Newbie")
    db.add_dig_item(0, 1, "rank_2", 1)
    db.add_dig_weekly_depth(1, "2026-07-13", 7)
    db.add_dig_weekly_depth(2, "2026-07-13", 99)

    try:
        rows = db.list_dig_weekly_rankings("2026-07-13")
    finally:
        db.close()

    assert rows == [{"user_id": 1, "depth": 7, "username": "ranked", "full_name": "Ranked", "rank_level": 2}]
