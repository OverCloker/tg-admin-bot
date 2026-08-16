import asyncio
from io import BytesIO

import pytest
from aiogram.exceptions import TelegramBadRequest
from starlette.datastructures import Headers

from app.db import Database
from app import bot as game
from app import miniapp
from app.miniapp import (
    MINIAPP_ASSIGNABLE_PROFILE_ROLES,
    MINIAPP_OWNER_PROFILE_ROLE,
    MiniAppChatLockSet,
    MiniAppModeratorRoleClear,
    MiniAppModeratorRoleSet,
    MiniAppSlowModeSet,
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
    _miniapp_role_tabs,
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


def test_miniapp_profile_payload_does_not_include_roles(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OWNER_ID", "42")
    db_path = tmp_path / "bot.sqlite3"
    monkeypatch.setenv("DB_PATH", str(db_path))
    db = Database(str(db_path))
    db.init()
    db.upsert_seen_user(0, 8, "admin", "Admin", False)
    db.set_miniapp_profile_role(8, "Админ", 42)
    db.close()
    monkeypatch.setattr(miniapp, "_telegram_user", lambda _init_data: {"id": 8, "username": "admin", "full_name": "Admin"})

    profile = asyncio.run(miniapp.miniapp_profile(user_id=None, x_telegram_init_data="test"))

    assert "roles" not in profile
    assert profile["viewer"]["isAppAdmin"] is True


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
                MiniAppTriggerVariant(variantType="video", text="video", mediaType="video", mediaFileId="local:/tmp/cat.mp4"),
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

    assert len(options) == 6
    assert [item.text for item in options[:2]] == ["мяу", "мур"]
    assert options[0].aliases == ("котик", "кошак")
    assert listed["triggers"][0]["aliases"] == ["котик", "кошак"]
    assert listed["triggers"][0]["aliasCount"] == 2
    assert listed["triggers"][0]["variants"][2]["variantType"] == "photo"
    assert listed["triggers"][0]["variants"][4]["mediaType"] == "audio"
    assert listed["triggers"][0]["variants"][5]["mediaType"] == "video"


def test_miniapp_trigger_video_upload_accepts_octet_stream(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OWNER_ID", "42")
    db_path = tmp_path / "bot.sqlite3"
    monkeypatch.setenv("DB_PATH", str(db_path))
    db = Database(str(db_path))
    db.init()
    db.close()
    monkeypatch.setattr(miniapp, "_telegram_user", lambda _init_data: {"id": 42})
    monkeypatch.setattr(miniapp, "_db", lambda: Database(str(db_path)))

    async def fake_duration(_path):
        return 4.0

    monkeypatch.setattr(miniapp, "_media_duration_seconds", fake_duration)

    async def fake_store(_user_id, _media_type, _path, _filename=None):
        return None

    monkeypatch.setattr(miniapp, "_store_trigger_media_in_telegram", fake_store)
    file = miniapp.UploadFile(
        BytesIO(b"not a real video, duration is mocked"),
        filename="clip.mp4",
        headers=Headers({"content-type": "application/octet-stream"}),
    )

    result = asyncio.run(
        miniapp.miniapp_profile_trigger_media_upload(
            "video",
            file=file,
            x_telegram_init_data="test",
        )
    )

    assert result["mediaType"] == "video"
    assert result["mediaFileId"].startswith("local:")
    assert result["storage"] == "local"


def test_miniapp_trigger_video_upload_prefers_telegram_file_id(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OWNER_ID", "42")
    db_path = tmp_path / "bot.sqlite3"
    monkeypatch.setenv("DB_PATH", str(db_path))
    db = Database(str(db_path))
    db.init()
    db.close()
    monkeypatch.setattr(miniapp, "_telegram_user", lambda _init_data: {"id": 42})
    monkeypatch.setattr(miniapp, "_db", lambda: Database(str(db_path)))

    async def fake_duration(_path):
        return 4.0

    async def fake_store(user_id, media_type, path, filename=None):
        assert user_id == 42
        assert media_type == "video"
        assert path.exists()
        assert filename == "clip.mp4"
        return "document", "telegram-file-id"

    monkeypatch.setattr(miniapp, "_media_duration_seconds", fake_duration)
    monkeypatch.setattr(miniapp, "_store_trigger_media_in_telegram", fake_store)
    file = miniapp.UploadFile(
        BytesIO(b"not a real video, duration is mocked"),
        filename="clip.mp4",
        headers=Headers({"content-type": "application/octet-stream"}),
    )

    result = asyncio.run(
        miniapp.miniapp_profile_trigger_media_upload(
            "video",
            file=file,
            x_telegram_init_data="test",
        )
    )

    assert result["mediaType"] == "document"
    assert result["mediaFileId"] == "telegram-file-id"
    assert result["storage"] == "telegram"


def test_local_video_trigger_falls_back_to_document(tmp_path) -> None:
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"fake video payload")

    class FakeChat:
        id = -100

    class FakeBot:
        def __init__(self) -> None:
            self.video_calls = 0
            self.document_calls = 0

        async def send_video(self, **_kwargs):
            self.video_calls += 1
            raise TelegramBadRequest(method="sendVideo", message="video format invalid")

        async def send_document(self, **kwargs):
            self.document_calls += 1
            assert kwargs["caption"] == "caption"

    class FakeMessage:
        chat = FakeChat()
        message_id = 77

        def __init__(self) -> None:
            self.bot = FakeBot()

        async def reply(self, *_args, **_kwargs):
            raise AssertionError("text fallback should not be used when document fallback works")

    message = FakeMessage()
    item = type(
        "TriggerItem",
        (),
        {"text": "caption", "media_type": "video", "media_file_id": f"local:{video_path}"},
    )()

    asyncio.run(game.send_auto_reply_item(message, item))

    assert message.bot.video_calls == 1
    assert message.bot.document_calls == 1


def test_telegram_video_file_id_falls_back_to_document() -> None:
    class FakeChat:
        id = -100

    class FakeBot:
        def __init__(self) -> None:
            self.video_calls = 0
            self.document_calls = 0

        async def send_video(self, **_kwargs):
            self.video_calls += 1
            raise TelegramBadRequest(method="sendVideo", message="video rejected")

        async def send_document(self, **kwargs):
            self.document_calls += 1
            assert kwargs["document"] == "telegram-video-file-id"

    class FakeMessage:
        chat = FakeChat()
        message_id = 77

        def __init__(self) -> None:
            self.bot = FakeBot()

        async def reply(self, *_args, **_kwargs):
            raise AssertionError("text fallback should not be used when document fallback works")

    message = FakeMessage()
    item = type(
        "TriggerItem",
        (),
        {"trigger": "clip", "text": "", "media_type": "video", "media_file_id": "telegram-video-file-id"},
    )()

    asyncio.run(game.send_auto_reply_item(message, item))

    assert message.bot.video_calls == 1
    assert message.bot.document_calls == 1


def test_dig_command_sends_command_result_before_matching_trigger(monkeypatch) -> None:
    calls: list[str] = []
    trigger = type(
        "TriggerItem",
        (),
        {
            "trigger": "\u043a\u043e\u043f\u0430\u0439",
            "aliases": (),
            "text": "",
            "media_type": "video",
            "media_file_id": "telegram-video-file-id",
        },
    )()

    class FakeDb:
        def get_dig_block(self, _user_id):
            return None

        def get_dig_player(self, _chat_id, _user_id):
            return object()

    class FakeChat:
        id = -100
        type = "supergroup"

    class FakeUser:
        id = 42
        username = "miner"
        full_name = "Miner"

    class FakeMessage:
        chat = FakeChat()
        from_user = FakeUser()
        text = "\u043a\u043e\u043f\u0430\u0439"
        caption = None
        message_id = 77
        bot = object()

    async def fake_remember_sender(_message):
        return None

    async def fake_temporary_reply(_message, *_args, **_kwargs):
        calls.append("command")

    async def fake_send_auto_reply_item(_message, _item):
        calls.append("trigger")

    monkeypatch.setattr(game, "db", FakeDb(), raising=False)
    monkeypatch.setattr(game, "remember_sender", fake_remember_sender)
    monkeypatch.setattr(game, "temporary_reply", fake_temporary_reply)
    monkeypatch.setattr(game, "send_auto_reply_item", fake_send_auto_reply_item)
    monkeypatch.setattr(game, "cached_triggers", lambda _chat_id: [trigger])
    game.AUTO_TRIGGER_SENT_MESSAGES.clear()

    asyncio.run(game.dig_command(FakeMessage()))

    assert calls == ["command", "trigger"]


def test_miniapp_trigger_marks_missing_local_media(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OWNER_ID", "42")
    db_path = tmp_path / "bot.sqlite3"
    db = Database(str(db_path))
    db.init()
    db.upsert_chat(-100, "Чат", "supergroup", None)
    db.replace_trigger_variants(
        -100,
        "клип",
        [{"variant_type": "video", "text": "", "media_type": "video", "media_file_id": f"local:{tmp_path / 'missing.mp4'}"}],
        42,
    )
    db.close()
    monkeypatch.setattr(miniapp, "_telegram_user", lambda _init_data: {"id": 42})
    monkeypatch.setattr(miniapp, "_db", lambda: Database(str(db_path)))

    listed = miniapp.miniapp_profile_triggers(chat_id=-100, x_telegram_init_data="test")
    variant = listed["triggers"][0]["variants"][0]

    assert variant["mediaBroken"] is True


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
    db.upsert_chat(-100, "Chat", "supergroup", None)
    db.set_miniapp_profile_role(8, "Админ", 42)
    db.set_admin_feature_permission(-100, 10, "triggers.manage", True, 42)

    try:
        assert _miniapp_can_manage_triggers(db, 42) is True
        assert _miniapp_can_manage_triggers(db, 8) is True
        assert _miniapp_can_manage_triggers(db, 10) is True
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
    db.upsert_chat(-200, "Other", "supergroup", None)
    db.upsert_seen_user(-100, 42, "owner", "Owner", False)
    db.upsert_seen_user(-100, 7, "helper", "Helper", False)
    db.upsert_seen_user(-100, 9, "chatadmin", "Chat Admin", False)
    db.set_chat_moderator_role(-100, 7, "assistant", 42)
    db.set_miniapp_profile_role(8, "Админ", 42)
    db.set_admin_feature_permission(-100, 9, "triggers.manage", True, 42)
    db.set_admin_feature_permission(-200, 9, "triggers.manage", True, 42)
    db.set_admin_feature_permission(-100, 42, "triggers.manage", True, 42)

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
    assert admin_group["items"][1]["user_id"] == 9
    assert admin_group["items"][1]["source"] == "chat_admin"
    assert admin_group["items"][1]["canRemove"] is False
    assert admin_group["items"][1]["chatCount"] == 2
    assert 42 not in {item["user_id"] for item in admin_group["items"]}
    assert admin_group["assignable"] is True
    assert assistant_group["items"][0]["user_id"] == 7
    assert assistant_group["items"][0]["source"] == "moderation"
    assert assistant_group["items"][0]["chatCount"] == 1


def test_miniapp_role_tabs_split_app_roles_and_chat_roles(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OWNER_ID", "42")
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()
    db.upsert_chat(-100, "Main Chat", "supergroup", None)
    db.upsert_chat(-200, "Side Chat", "supergroup", None)
    db.upsert_seen_user(-100, 42, "owner", "Owner", False)
    db.set_miniapp_profile_role(8, "Админ", 42)
    db.replace_chat_telegram_admins(
        -100,
        [
            {"user_id": 9, "username": "chatadmin", "full_name": "Chat Admin", "status": "administrator", "is_bot": False},
            {"user_id": 42, "username": "owner", "full_name": "Owner", "status": "creator", "is_bot": False},
        ],
    )
    db.set_chat_moderator_role(-100, 7, "assistant", 42)
    db.set_chat_moderator_role(-200, 11, "moderator", 42)

    try:
        tabs = _miniapp_role_tabs(db)
    finally:
        db.close()

    app_tab = tabs[0]
    main_tab = next(tab for tab in tabs if tab["chatId"] == -100)
    side_tab = next(tab for tab in tabs if tab["chatId"] == -200)
    assert app_tab["title"] == "Роли приложения"
    assert app_tab["groups"][1]["items"][0]["user_id"] == 8
    telegram_admin_group = next(group for group in main_tab["groups"] if group["key"] == "telegram_admin")
    assistant_group = next(group for group in main_tab["groups"] if group["key"] == "assistant")
    side_moderator_group = next(group for group in side_tab["groups"] if group["key"] == "moderator")
    assert [item["user_id"] for item in telegram_admin_group["items"]] == [9]
    assert telegram_admin_group["items"][0]["source"] == "telegram_admin"
    assert assistant_group["items"][0]["user_id"] == 7
    assert side_moderator_group["items"][0]["user_id"] == 11
    assert 42 not in {item["user_id"] for item in telegram_admin_group["items"]}


def test_miniapp_telegram_admin_cache_grants_app_admin_access(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OWNER_ID", "42")
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()
    db.upsert_chat(-100, "Main Chat", "supergroup", None)
    db.replace_chat_telegram_admins(
        -100,
        [{"user_id": 9, "username": "chatadmin", "full_name": "Chat Admin", "status": "administrator", "is_bot": False}],
    )
    try:
        assert _miniapp_can_view_admin_panel(db, 9) is True
        assert _miniapp_can_manage_triggers(db, 9) is True
    finally:
        db.close()


def test_miniapp_moderation_roles_are_owner_managed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OWNER_ID", "42")
    db_path = tmp_path / "bot.sqlite3"
    db = Database(str(db_path))
    db.init()
    db.upsert_chat(-100, "Chat", "supergroup", None)
    db.upsert_seen_user(-100, 7, "helper", "Helper", False)
    db.set_miniapp_profile_role(8, "Админ", 42)
    db.close()
    monkeypatch.setattr(miniapp, "_db", lambda: Database(str(db_path)))

    monkeypatch.setattr(miniapp, "_telegram_user", lambda _init_data: {"id": 42})
    result = miniapp.miniapp_profile_moderation_role_set(
        MiniAppModeratorRoleSet(chatId=-100, target="@helper", role="moderator"),
        x_telegram_init_data="test",
    )
    listed = miniapp.miniapp_profile_moderation(chat_id=-100, x_telegram_init_data="test")
    assert result["role"] == "moderator"
    assert "roles" not in listed
    assert "canManageRoles" not in listed
    db_check = Database(str(db_path))
    try:
        tabs = _miniapp_role_tabs(db_check)
    finally:
        db_check.close()
    chat_tab = next(tab for tab in tabs if tab["chatId"] == -100)
    moderator_group = next(group for group in chat_tab["groups"] if group["key"] == "moderator")
    assert moderator_group["items"][0]["user_id"] == 7

    monkeypatch.setattr(miniapp, "_telegram_user", lambda _init_data: {"id": 8})
    with pytest.raises(Exception) as exc_info:
        miniapp.miniapp_profile_moderation_role_set(
            MiniAppModeratorRoleSet(chatId=-100, target="@helper", role="senior"),
            x_telegram_init_data="test",
        )
    assert getattr(exc_info.value, "status_code", None) == 403

    monkeypatch.setattr(miniapp, "_telegram_user", lambda _init_data: {"id": 42})
    cleared = miniapp.miniapp_profile_moderation_role_clear(
        MiniAppModeratorRoleClear(chatId=-100, target="7"),
        x_telegram_init_data="test",
    )
    assert cleared["removed"] is True


def test_miniapp_moderation_chat_lock_respects_role_limits(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OWNER_ID", "42")
    db_path = tmp_path / "bot.sqlite3"
    db = Database(str(db_path))
    db.init()
    db.upsert_chat(-100, "Chat", "supergroup", None)
    db.set_chat_moderator_role(-100, 7, "moderator", 42)
    db.set_chat_moderator_role(-100, 9, "assistant", 42)
    db.close()
    monkeypatch.setattr(miniapp, "_db", lambda: Database(str(db_path)))

    monkeypatch.setattr(miniapp, "_telegram_user", lambda _init_data: {"id": 7})
    ok = miniapp.miniapp_profile_moderation_chat_lock(
        MiniAppChatLockSet(chatId=-100, seconds=10 * 60, reason="test"),
        x_telegram_init_data="test",
    )
    assert ok["lock"]["reason"] == "test"
    with pytest.raises(Exception) as exc_info:
        miniapp.miniapp_profile_moderation_chat_lock(
            MiniAppChatLockSet(chatId=-100, seconds=11 * 60, reason="too long"),
            x_telegram_init_data="test",
        )
    assert getattr(exc_info.value, "status_code", None) == 403

    monkeypatch.setattr(miniapp, "_telegram_user", lambda _init_data: {"id": 9})
    with pytest.raises(Exception) as exc_info:
        miniapp.miniapp_profile_moderation_chat_lock(
            MiniAppChatLockSet(chatId=-100, seconds=60, reason="assistant"),
            x_telegram_init_data="test",
        )
    assert getattr(exc_info.value, "status_code", None) == 403


def test_miniapp_moderation_slow_mode_can_be_disabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OWNER_ID", "42")
    db_path = tmp_path / "bot.sqlite3"
    db = Database(str(db_path))
    db.init()
    db.upsert_chat(-100, "Chat", "supergroup", None)
    db.close()
    monkeypatch.setattr(miniapp, "_db", lambda: Database(str(db_path)))
    monkeypatch.setattr(miniapp, "_telegram_user", lambda _init_data: {"id": 42})

    enabled = asyncio.run(
        miniapp.miniapp_profile_moderation_slow_mode(
            MiniAppSlowModeSet(chatId=-100, delay=30),
            x_telegram_init_data="test",
        )
    )
    assert enabled["delay"] == 30
    db_check = Database(str(db_path))
    try:
        assert db_check.get_chat_slow_mode(-100)["delay_seconds"] == 30
    finally:
        db_check.close()

    disabled = asyncio.run(
        miniapp.miniapp_profile_moderation_slow_mode(
            MiniAppSlowModeSet(chatId=-100, delay=0),
            x_telegram_init_data="test",
        )
    )
    assert disabled["delay"] == 0
    db_check = Database(str(db_path))
    try:
        assert db_check.get_chat_slow_mode(-100) is None
        assert db_check.get_chat_slow_mode_state(-100) is None
    finally:
        db_check.close()


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
