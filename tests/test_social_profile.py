from app.db import Database
from app.premium import PremiumService
from app.user_profile import build_user_profile, profile_chat_text


def make_social_db(tmp_path):
    db_path = tmp_path / "social.sqlite3"
    db = Database(str(db_path))
    db.init()
    db.upsert_chat(-1001, "Тестовая группа", "supergroup", None)
    db.upsert_seen_user(-1001, 1, "first", "Первый", False)
    db.upsert_seen_user(-1001, 2, None, "Второй без username", False)
    db.upsert_seen_user(-1001, 3, "third", "Третий", False)
    return db, db_path


def test_friend_request_requires_acceptance_and_does_not_duplicate(tmp_path):
    db, _ = make_social_db(tmp_path)
    try:
        assert db.friendship_state(-1001, 1, 2) == "none"
        assert db.create_friend_request(-1001, 1, 2) == "created"
        assert db.create_friend_request(-1001, 1, 2) == "outgoing"
        assert db.friendship_state(-1001, 2, 1) == "incoming"
        assert db.accept_friend_request(-1001, 1, 2)
        assert db.friendship_state(-1001, 1, 2) == "friends"
        assert db.count_chat_friends(-1001, 1) == 1
        assert db.list_chat_friends(-1001, 1)[0].full_name == "Второй без username"
        assert not db.accept_friend_request(-1001, 1, 2)
    finally:
        db.close()


def test_couple_is_unique_per_chat_and_also_creates_friendship(tmp_path):
    db, _ = make_social_db(tmp_path)
    try:
        assert db.create_couple_request(-1001, 1, 2) == "created"
        assert db.accept_couple_request(-1001, 1, 2) == "accepted"
        assert db.couple_state(-1001, 1, 2) == "couple"
        assert db.friendship_state(-1001, 1, 2) == "friends"
        assert db.create_couple_request(-1001, 1, 3) == "user_busy"
        assert db.create_couple_request(-1001, 3, 2) == "target_busy"
        assert db.get_chat_partner(-1001, 1).user_id == 2
        assert db.end_chat_couple(-1001, 1, 2)
        assert db.get_chat_partner(-1001, 1) is None
        assert db.friendship_state(-1001, 1, 2) == "friends"
    finally:
        db.close()


def test_chat_profile_contains_social_summary(tmp_path):
    db, db_path = make_social_db(tmp_path)
    premium = PremiumService(str(db_path))
    try:
        assert db.create_friend_request(-1001, 1, 2) == "created"
        assert db.accept_friend_request(-1001, 1, 2)
        assert db.create_couple_request(-1001, 1, 2) == "created"
        assert db.accept_couple_request(-1001, 1, 2) == "accepted"

        profile = build_user_profile(
            db,
            premium,
            1,
            "first",
            "Первый",
            chat_id=-1001,
        )
        text = profile_chat_text(profile, short=False)
        assert profile["social"]["friendsCount"] == 1
        assert profile["social"]["partner"]["fullName"] == "Второй без username"
        assert "Отношения в этом чате" in text
        assert "Второй без username" in text
        assert "Друзей: <b>1</b>" in text
    finally:
        premium.close()
        db.close()


def test_user_profile_translates_artifacts_and_rank_achievements(tmp_path):
    db_path = tmp_path / "profile.sqlite3"
    db = Database(str(db_path))
    db.init()
    premium = PremiumService(str(db_path))
    try:
        db.register_dig_player(0, 42, "miner", "Шахтёр")
        db.add_dig_item(0, 42, "artifact_badge", 1)
        db.add_dig_item(0, 42, "artifact_coin", 1)
        db.add_dig_item(0, 42, "artifact_set_reward", 1)
        db.add_dig_achievement(0, 42, "rank_depth")
        db.add_dig_achievement(0, 42, "rank_digger")

        profile = build_user_profile(db, premium, 42, "miner", "Шахтёр")
    finally:
        premium.close()
        db.close()

    item_names = {item["name"] for item in profile["mine"]["activeItems"]}
    achievement_names = {item["name"] for item in profile["mine"]["achievements"]}
    assert "Знак старой бригады" in item_names
    assert "Старая монета" in item_names
    assert "Бонус полной коллекции" in item_names
    assert "artifact_badge" not in item_names
    assert "Барон глубин" in achievement_names
    assert "Знак проходчика" in achievement_names
    assert "rank_depth" not in achievement_names


def test_user_profile_exposes_item_groups_and_rarest_achievements(tmp_path):
    db_path = tmp_path / "profile_rarity.sqlite3"
    db = Database(str(db_path))
    db.init()
    premium = PremiumService(str(db_path))
    try:
        db.register_dig_player(0, 42, "miner", "Шахтёр")
        db.add_dig_item(0, 42, "artifact_badge", 1)
        db.add_dig_item(0, 42, "super_mute30", 1)
        db.add_dig_item(0, 42, "tea", 2)
        db.add_dig_achievement(0, 42, "first_dig")
        db.add_dig_achievement(0, 42, "rank_depth")
        db.add_dig_achievement(0, 42, "collector_all")

        profile = build_user_profile(db, premium, 42, "miner", "Шахтёр")
    finally:
        premium.close()
        db.close()

    items = {item["key"]: item for item in profile["mine"]["activeItems"]}
    assert items["artifact_badge"]["group"] == "collection"
    assert items["super_mute30"]["group"] == "paid"
    assert items["tea"]["group"] == "consumable"

    rare = profile["mine"]["rareAchievements"]
    assert rare[0]["key"] in {"collector_all", "rank_depth"}
    assert rare[0]["rarity"] == "mythic"
    assert all("rarityTitle" in item and "rarityScore" in item for item in rare)
