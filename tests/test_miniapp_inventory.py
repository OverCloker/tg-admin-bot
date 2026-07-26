from app.db import Database
from app.miniapp import _shop_catalog


def test_inventory_uses_display_names_and_only_best_upgrade(tmp_path) -> None:
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()
    db.register_dig_player(0, 42, "miner", "Шахтёр")
    db.add_dig_item(0, 42, "artifact_badge", 1)
    db.add_dig_item(0, 42, "artifact_set_reward", 1)
    db.add_dig_item(0, 42, "shovel_1", 1)
    db.add_dig_item(0, 42, "shovel_2", 1)
    db.add_dig_item(0, 42, "golden_ticket", 2)

    try:
        catalog = _shop_catalog(db, 42)
    finally:
        db.close()

    inventory = {
        group["title"]: {item["key"]: item for item in group["items"]}
        for group in catalog["inventory"]
    }

    assert inventory["Коллекция"]["artifact_badge"]["name"] == "Знак старой бригады"
    assert inventory["Коллекция"]["artifact_set_reward"]["name"] == "Бонус полной коллекции"
    assert "shovel_1" not in inventory["Постоянные улучшения"]
    assert inventory["Постоянные улучшения"]["shovel_2"]["name"] == "Лопата II"
    assert inventory["Припасы и билеты"]["golden_ticket"] == {
        "key": "golden_ticket",
        "name": "Золотой билет",
        "quantity": 2,
    }


def test_shop_requirement_is_human_readable(tmp_path) -> None:
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()
    db.register_dig_player(0, 42, "miner", "Шахтёр")

    try:
        catalog = _shop_catalog(db, 42)
    finally:
        db.close()

    products = {
        item["key"]: item
        for category in catalog["categories"]
        for item in category["items"]
    }
    assert products["helmet_2"]["requirement"] == "helmet_1"
    assert products["helmet_2"]["requirementName"] == "Каска I"


def test_dig_player_tag_can_be_saved(tmp_path) -> None:
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()

    try:
        assert db.get_dig_player_tag(42) is None
        db.set_dig_player_tag(42, "Lucky Miner")
        assert db.get_dig_player_tag(42) == "Lucky Miner"
        db.set_dig_player_tag(42, "Deep Baron")
        assert db.get_dig_player_tag(42) == "Deep Baron"
    finally:
        db.close()
