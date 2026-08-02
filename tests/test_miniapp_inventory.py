from app.db import Database
from app import bot as game
from app import miniapp
from app.miniapp import _gift_recipients, _gift_target_kind, _miniapp_social_people, _miniapp_social_target, _shop_catalog
from app.premium import PremiumService
from app.user_profile import build_user_profile


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
    assert inventory["Постоянные улучшения"]["shovel_2"]["name"] == "Кирка II"
    assert inventory["Припасы и билеты"]["golden_ticket"]["key"] == "golden_ticket"
    assert inventory["Припасы и билеты"]["golden_ticket"]["name"] == "Золотой билет"
    assert inventory["Припасы и билеты"]["golden_ticket"]["quantity"] == 2
    assert inventory["Припасы и билеты"]["golden_ticket"]["giftable"] is False


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


def test_shop_catalog_has_star_mute_purchase(tmp_path) -> None:
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()
    db.register_dig_player(0, 42, "miner", "Шахтёр")

    try:
        catalog = _shop_catalog(db, 42)
    finally:
        db.close()

    star_category = next(category for category in catalog["categories"] if category["key"] == "stars")
    mute = next(item for item in star_category["items"] if item["key"] == "super_mute30")
    assert mute["starPrice"] == 3
    assert mute["quantity"] == 0
    assert "полчаса" in mute["description"]


def test_shop_catalog_has_profile_gifts_and_relationship_sections(tmp_path) -> None:
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()
    db.register_dig_player(0, 42, "miner", "Шахтёр")

    try:
        catalog = _shop_catalog(db, 42)
    finally:
        db.close()

    categories = {category["key"]: category for category in catalog["categories"]}
    assert "profile" in categories
    assert "gifts" in categories
    assert "relationships" in categories
    assert any(item["key"] == "profile_frame_copper" and item["price"] == 500 for item in categories["profile"]["items"])
    assert any(item["key"] == "gift_tea_friend" and item["price"] == 50 for item in categories["gifts"]["items"])
    assert any(item["key"] == "couple_frame" and item["price"] == 3500 for item in categories["relationships"]["items"])


def test_profile_cosmetics_are_exposed_after_purchase(tmp_path) -> None:
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()
    db.register_dig_player(0, 42, "miner", "Шахтёр")
    db.add_dig_item(0, 42, "profile_frame_crystal", 1)
    db.add_dig_item(0, 42, "profile_bg_lava", 1)
    db.add_dig_item(0, 42, "profile_badge_gem", 1)
    premium = PremiumService(db)

    try:
        profile = build_user_profile(db, premium, 42, "miner", "Шахтёр")
    finally:
        db.close()

    cosmetics = profile["mine"]["cosmetics"]
    assert cosmetics["frame"]["key"] == "profile_frame_crystal"
    assert cosmetics["background"]["key"] == "profile_bg_lava"
    assert cosmetics["badges"][0]["key"] == "profile_badge_gem"


def test_gift_recipients_include_registered_friends_and_partner(tmp_path) -> None:
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()
    db.register_dig_player(0, 1, "sender", "Даритель")
    db.register_dig_player(0, 2, "friend", "Друг")
    db.register_dig_player(0, 3, "partner", "Пара")
    db.register_dig_player(0, 4, "stranger", "Не друг")
    db.upsert_seen_user(-100, 1, "sender", "Даритель", False)
    db.upsert_seen_user(-100, 2, "friend", "Друг", False)
    db.upsert_seen_user(-100, 3, "partner", "Пара", False)
    db.upsert_seen_user(-100, 4, "stranger", "Не друг", False)
    db.create_friend_request(-100, 1, 2)
    db.accept_friend_request(-100, 1, 2)
    db.create_couple_request(-100, 1, 3)
    db.accept_couple_request(-100, 1, 3)

    try:
        friend_targets = _gift_recipients(db, game, 1, "gift_yarn")
        partner_targets = _gift_recipients(db, game, 1, "couple_flower")
    finally:
        db.close()

    assert _gift_target_kind(game, "gift_yarn") == "friends"
    assert _gift_target_kind(game, "couple_flower") == "partner"
    assert {item["id"] for item in friend_targets} == {2, 3}
    assert {item["id"] for item in partner_targets} == {3}


def test_miniapp_social_people_include_profile_links_for_friends_and_partner(tmp_path) -> None:
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()
    db.register_dig_player(0, 1, "sender", "Даритель")
    db.register_dig_player(0, 2, "friend", "Друг")
    db.register_dig_player(0, 3, "partner", "Пара")
    db.upsert_seen_user(-100, 1, "sender", "Даритель", False)
    db.upsert_seen_user(-100, 2, "friend", "Друг", False)
    db.upsert_seen_user(-100, 3, "partner", "Пара", False)
    db.create_friend_request(-100, 1, 2)
    db.accept_friend_request(-100, 1, 2)
    db.create_couple_request(-100, 1, 3)
    db.accept_couple_request(-100, 1, 3)

    try:
        people = _miniapp_social_people(db, 1)
        target = _miniapp_social_target(db, 1, 2)
        stranger = _miniapp_social_target(db, 1, 999)
    finally:
        db.close()

    assert {item["id"] for item in people} == {2, 3}
    assert any(item["relation"] == "partner" and item["photoUrl"].startswith("/miniapp/avatar/3?sig=") for item in people)
    assert target and target["relation"] == "friend"
    assert stranger is None


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


def test_miniapp_does_not_rebind_bot_global_database() -> None:
    source = miniapp.__loader__.get_source(miniapp.__name__) or ""
    assert "game.db =" not in source
    assert "game.dig_items_map(" not in source
    assert "game.dig_route(" not in source
