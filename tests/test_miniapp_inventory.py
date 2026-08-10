from app.db import Database
from app import bot as game
from app import miniapp
from app.miniapp import (
    MINIAPP_ASSIGNABLE_PROFILE_ROLES,
    MINIAPP_OWNER_PROFILE_ROLE,
    MiniAppTriggerDelete,
    MiniAppTriggerSave,
    MiniAppTriggerVariant,
    _gift_recipients,
    _gift_target_kind,
    _miniapp_can_manage_mine_admin,
    _miniapp_can_manage_triggers,
    _miniapp_can_view_admin_panel,
    _miniapp_can_view_mine_admin,
    _miniapp_profile_role_groups,
    _miniapp_profile_roles,
    _miniapp_social_people,
    _miniapp_social_target,
    _shop_catalog,
)
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


def test_shop_catalog_has_all_star_donate_purchases(tmp_path) -> None:
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()
    db.register_dig_player(0, 42, "miner", "Шахтёр")
    db.add_dig_item(0, 42, "star_dig", 2)

    try:
        catalog = _shop_catalog(db, 42)
    finally:
        db.close()

    star_category = next(category for category in catalog["categories"] if category["key"] == "stars")
    star_items = {item["key"]: item for item in star_category["items"]}
    assert set(game.DIG_STAR_ACTIONS) <= set(star_items)
    assert star_items["luck"]["starPrice"] == 3
    assert star_items["luck"]["instant"] is True
    assert star_items["digs3"]["quantity"] == 2
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


def test_shop_catalog_exposes_mined_resources_and_merchant(tmp_path) -> None:
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()
    db.register_dig_player(0, 42, "miner", "Шахтёр")
    db.add_dig_item(0, 42, "res_iron", 3)
    db.add_dig_item(0, 42, "res_crystal", 1)

    try:
        catalog = _shop_catalog(db, 42)
    finally:
        db.close()

    inventory = {
        group["title"]: {item["key"]: item for item in group["items"]}
        for group in catalog["inventory"]
    }
    assert inventory["Добыча"]["res_iron"]["name"] == "Железная руда"
    assert inventory["Добыча"]["res_iron"]["quantity"] == 3
    merchant = {item["key"]: item for item in catalog["merchant"]["items"]}
    assert merchant["res_iron"]["quantity"] == 3
    assert merchant["res_iron"]["total"] == merchant["res_iron"]["price"] * 3
    assert catalog["merchant"]["total"] >= merchant["res_iron"]["total"]


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
    db.register_dig_player(0, 3, "partner", "Пара")
    db.register_dig_player(0, 4, "miner", "Шахтёр")
    db.upsert_seen_user(-100, 1, "sender", "Даритель", False)
    db.upsert_seen_user(-100, 2, "friend", "Друг без шахты", False)
    db.upsert_seen_user(-100, 3, "partner", "Пара", False)
    db.upsert_seen_user(-100, 4, "miner", "Шахтёр", False)
    db.create_friend_request(-100, 1, 2)
    db.accept_friend_request(-100, 1, 2)
    db.create_friend_request(-100, 1, 4)
    db.accept_friend_request(-100, 1, 4)
    db.create_couple_request(-100, 1, 3)
    db.accept_couple_request(-100, 1, 3)

    try:
        people = _miniapp_social_people(db, 1)
        target = _miniapp_social_target(db, 1, 2)
        stranger = _miniapp_social_target(db, 1, 999)
    finally:
        db.close()

    assert {item["id"] for item in people} == {2, 3, 4}
    assert any(item["id"] == 2 and item["fullName"] == "Друг без шахты" for item in people)
    assert any(item["relation"] == "partner" and item["photoUrl"].startswith("/miniapp/avatar/3?sig=") for item in people)
    assert target and target["relation"] == "friend"
    assert _miniapp_social_target(db, 1, 1) == {"relation": "self", "relationTitle": ""}
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


def test_miniapp_profile_roles_include_owner_custom_and_moderation(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OWNER_ID", "42")
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()
    db.upsert_chat(-100, "Чат", "supergroup", None)
    db.upsert_seen_user(-100, 42, "owner", "Владелец", False)
    db.set_miniapp_profile_role(42, "Технарь", 42)
    db.set_chat_moderator_role(-100, 42, "senior", 42)

    try:
        roles = _miniapp_profile_roles(db, 42)
    finally:
        db.close()

    assert [role["title"] for role in roles] == ["Владелец", "Технарь", "Старший модератор"]
    assert roles[0]["kind"] == "owner"
    assert roles[1]["kind"] == "custom"
    assert roles[2]["chatCount"] == 1


def test_miniapp_mine_admin_access_is_owner_or_moderator(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OWNER_ID", "42")
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()
    db.upsert_chat(-100, "Р§Р°С‚", "supergroup", None)
    db.set_chat_moderator_role(-100, 7, "assistant", 42)
    db.set_miniapp_profile_role(8, "Админ", 42)

    try:
        assert _miniapp_can_view_mine_admin(db, 42) is True
        assert _miniapp_can_view_mine_admin(db, 7) is True
        assert _miniapp_can_view_mine_admin(db, 8) is True
        assert _miniapp_can_view_admin_panel(db, 8) is True
        assert _miniapp_can_manage_mine_admin(db, 42) is True
        assert _miniapp_can_manage_mine_admin(db, 8) is False
        assert _miniapp_can_manage_mine_admin(db, 7) is False
        assert _miniapp_can_view_mine_admin(db, 9) is False
    finally:
        db.close()


def test_miniapp_trigger_admin_can_list_save_and_delete(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OWNER_ID", "42")
    db_path = tmp_path / "bot.sqlite3"
    db = Database(str(db_path))
    db.init()
    db.upsert_chat(-100, "Чат", "supergroup", None)
    db.set_miniapp_profile_role(8, "Админ", 42)
    db.close()
    monkeypatch.setattr(miniapp, "_telegram_user", lambda _init_data: {"id": 8})
    monkeypatch.setattr(miniapp, "_db", lambda: Database(str(db_path)))

    saved = miniapp.miniapp_profile_trigger_save(
        MiniAppTriggerSave(chatId=-100, trigger="  Привет   бот ", text="Здравствуй"),
        x_telegram_init_data="test",
    )
    listed = miniapp.miniapp_profile_triggers(chat_id=-100, x_telegram_init_data="test")
    deleted = miniapp.miniapp_profile_trigger_delete(
        MiniAppTriggerDelete(chatId=-100, trigger="привет бот"),
        x_telegram_init_data="test",
    )
    listed_after_delete = miniapp.miniapp_profile_triggers(chat_id=-100, x_telegram_init_data="test")

    assert saved["trigger"]["trigger"] == "привет бот"
    assert listed["selectedChatId"] == -100
    assert listed["chats"][0]["title"] == "Чат"
    assert listed["triggers"][0]["trigger"] == "привет бот"
    assert listed["triggers"][0]["text"] == "Здравствуй"
    assert deleted["deleted"] is True
    assert listed_after_delete["triggers"] == []


def test_miniapp_trigger_edit_preserves_existing_media(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OWNER_ID", "42")
    db_path = tmp_path / "bot.sqlite3"
    db = Database(str(db_path))
    db.init()
    db.upsert_chat(-100, "Чат", "supergroup", None)
    db.set_trigger(-100, "кот", "старый ответ", 42, "photo", "file-1")
    db.close()
    monkeypatch.setattr(miniapp, "_telegram_user", lambda _init_data: {"id": 42})
    monkeypatch.setattr(miniapp, "_db", lambda: Database(str(db_path)))

    saved = miniapp.miniapp_profile_trigger_save(
        MiniAppTriggerSave(chatId=-100, trigger="кот", text="новый ответ"),
        x_telegram_init_data="test",
    )
    listed = miniapp.miniapp_profile_triggers(chat_id=-100, x_telegram_init_data="test")

    assert saved["trigger"]["mediaType"] == "photo"
    assert saved["trigger"]["hasMedia"] is True
    assert listed["triggers"][0]["text"] == "новый ответ"
    assert listed["triggers"][0]["mediaType"] == "photo"
    assert listed["triggers"][0]["hasMedia"] is True
    assert listed["triggers"][0]["variants"][0]["variantType"] == "photo"


def test_miniapp_trigger_can_store_multiple_variants(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OWNER_ID", "42")
    db_path = tmp_path / "bot.sqlite3"
    db = Database(str(db_path))
    db.init()
    db.upsert_chat(-100, "Чат", "supergroup", None)
    db.close()
    monkeypatch.setattr(miniapp, "_telegram_user", lambda _init_data: {"id": 42})
    monkeypatch.setattr(miniapp, "_db", lambda: Database(str(db_path)))

    miniapp.miniapp_profile_trigger_save(
        MiniAppTriggerSave(
            chatId=-100,
            trigger="кот",
            aliases=["котик", "кошак", "кот"],
            variants=[
                MiniAppTriggerVariant(variantType="text", text="мяу"),
                MiniAppTriggerVariant(variantType="text", text="мур"),
                MiniAppTriggerVariant(variantType="photo", text="смотри", mediaType="photo", mediaFileId="local:/tmp/cat.jpg"),
                MiniAppTriggerVariant(variantType="animation", text="гиф", mediaType="animation", mediaFileId="local:/tmp/cat.gif"),
                MiniAppTriggerVariant(variantType="audio", text="", mediaType="audio", mediaFileId="local:/tmp/cat.mp3"),
            ],
        ),
        x_telegram_init_data="test",
    )
    db = Database(str(db_path))
    try:
        options = db.list_trigger_answer_options(-100)
        listed = miniapp.miniapp_profile_triggers(chat_id=-100, x_telegram_init_data="test")
    finally:
        db.close()

    assert len(options) == 5
    assert [item.text for item in options[:2]] == ["мяу", "мур"]
    assert options[0].aliases == ("котик", "кошак")
    assert listed["triggers"][0]["aliases"] == ["котик", "кошак"]
    assert listed["triggers"][0]["aliasCount"] == 2
    assert listed["triggers"][0]["variants"][2]["variantType"] == "photo"
    assert listed["triggers"][0]["variants"][4]["mediaType"] == "audio"


def test_trigger_matching_uses_aliases() -> None:
    item = type("TriggerItem", (), {"trigger": "сон", "aliases": ("спать", "спал", "сплю")})()

    assert game.trigger_item_matches(game.normalize_trigger("хочу спать"), item) is True
    assert game.trigger_item_matches(game.normalize_trigger("он спал днем"), item) is True
    assert game.trigger_item_matches(game.normalize_trigger("сон пришел"), item) is True
    assert game.trigger_item_matches(game.normalize_trigger("спальня"), item) is False


def test_miniapp_trigger_text_variants_are_limited_to_ten(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OWNER_ID", "42")
    db_path = tmp_path / "bot.sqlite3"
    db = Database(str(db_path))
    db.init()
    db.upsert_chat(-100, "Чат", "supergroup", None)
    db.close()
    monkeypatch.setattr(miniapp, "_telegram_user", lambda _init_data: {"id": 42})
    monkeypatch.setattr(miniapp, "_db", lambda: Database(str(db_path)))

    try:
        miniapp.miniapp_profile_trigger_save(
            MiniAppTriggerSave(
                chatId=-100,
                trigger="кот",
                variants=[MiniAppTriggerVariant(variantType="text", text=str(index)) for index in range(11)],
            ),
            x_telegram_init_data="test",
        )
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 400
    else:
        raise AssertionError("Expected HTTP 400 for eleven text variants")


def test_miniapp_trigger_management_is_owner_or_app_admin(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OWNER_ID", "42")
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()
    db.set_miniapp_profile_role(8, "Админ", 42)

    try:
        assert _miniapp_can_manage_triggers(db, 42) is True
        assert _miniapp_can_manage_triggers(db, 8) is True
        assert _miniapp_can_manage_triggers(db, 9) is False
    finally:
        db.close()


def test_miniapp_admin_profile_role_uses_admin_badge(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OWNER_ID", "42")
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()
    db.set_miniapp_profile_role(8, "Админ", 42)

    try:
        roles = _miniapp_profile_roles(db, 8)
    finally:
        db.close()

    assert roles[0]["key"] == "admin"
    assert roles[0]["kind"] == "admin"
    assert roles[0]["emoji"] == "🛡️"


def test_miniapp_profile_role_groups_sync_owner_and_chat_moderators(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OWNER_ID", "42")
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()
    db.upsert_chat(-100, "Chat", "supergroup", None)
    db.upsert_seen_user(-100, 42, "owner", "Owner", False)
    db.upsert_seen_user(-100, 7, "helper", "Helper", False)
    db.set_chat_moderator_role(-100, 7, "assistant", 42)
    db.set_miniapp_profile_role(8, "Админ", 42)

    try:
        groups = _miniapp_profile_role_groups(db)
    finally:
        db.close()

    assert [group["label"] for group in groups] == [
        str(MINIAPP_OWNER_PROFILE_ROLE["label"]),
        *[str(role["label"]) for role in MINIAPP_ASSIGNABLE_PROFILE_ROLES],
    ]
    owner_group = next(group for group in groups if group["key"] == "owner")
    admin_group = next(group for group in groups if group["key"] == "admin")
    assistant_group = next(group for group in groups if group["key"] == "assistant")
    assert owner_group["items"][0]["user_id"] == 42
    assert owner_group["items"][0]["source"] == "owner"
    assert owner_group["items"][0]["canRemove"] is False
    assert owner_group["assignable"] is False
    assert admin_group["items"][0]["user_id"] == 8
    assert admin_group["items"][0]["source"] == "miniapp"
    assert admin_group["assignable"] is True
    assert assistant_group["items"][0]["user_id"] == 7
    assert assistant_group["items"][0]["source"] == "moderation"
    assert assistant_group["items"][0]["chatCount"] == 1


def test_dig_player_can_be_deleted_and_blocked(tmp_path) -> None:
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()
    db.register_dig_player(0, 42, "miner", "Шахтёр")
    db.add_dig_item(0, 42, "tea", 2)
    db.add_dig_achievement(0, 42, "first_dig")

    try:
        db.block_dig_user(42, 1, "spam")
        block = db.get_dig_block(42)
        deleted = db.delete_dig_player(42)
        blocks = db.list_dig_blocks()
    finally:
        db.close()

    assert block and block["reason"] == "spam"
    assert deleted is True
    assert blocks[0]["user_id"] == 42

def test_miniapp_profile_role_can_be_saved_and_resolved_by_username(tmp_path) -> None:
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()
    db.upsert_chat(-100, "Чат", "supergroup", None)
    db.upsert_seen_user(-100, 7, "helper", "Помощник", False)

    try:
        user = db.get_known_user_by_username("@helper")
        assert user and user.user_id == 7
        db.set_miniapp_profile_role(user.user_id, "Модерация", 42)
        role = db.get_miniapp_profile_role(7)
        roles = db.list_miniapp_profile_roles()
    finally:
        db.close()

    assert role and role.label == "Модерация"
    assert roles[0]["username"] == "helper"
    assert roles[0]["full_name"] == "Помощник"


def test_miniapp_does_not_rebind_bot_global_database() -> None:
    source = miniapp.__loader__.get_source(miniapp.__name__) or ""
    assert "game.db =" not in source
    assert "game.dig_items_map(" not in source
    assert "game.dig_route(" not in source
