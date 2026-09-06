from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app import miniapp
from app.db import Database
from app.relationships import LEVELS, relationship_level


@pytest.fixture
def pair(tmp_path):
    path = tmp_path / 'levels.sqlite3'
    db = Database(str(path))
    db.init()
    db.upsert_chat(-100, 'Chat', 'supergroup', None)
    for uid in (1, 2, 3):
        db.upsert_seen_user(-100, uid, f'user{uid}', f'User {uid}', False)
        db.register_dig_player(0, uid, f'user{uid}', f'User {uid}')
    db.create_couple_request(-100, 1, 2)
    db.accept_couple_request(-100, 1, 2)
    yield db, path
    db.close()


def test_all_level_boundaries():
    for index, (threshold, title) in enumerate(LEVELS):
        progress = relationship_level(threshold)
        assert progress['level'] == index + 1
        assert progress['title'] == title
        if threshold:
            assert relationship_level(threshold - 1)['level'] == index
    assert relationship_level(99999)['percent'] == 100
    assert relationship_level(99999)['nextXp'] is None


def test_care_daily_for_each_partner_and_next_day(pair):
    db, _ = pair
    with patch('app.relationships.relationship_day', return_value='2026-09-06'):
        assert db.care_for_partner(-100, 1)
        assert not db.care_for_partner(-100, 1)
        assert db.care_for_partner(-100, 2)
        assert db.relationship_progress(-100, 1)['xp'] == 40
        assert not db.relationship_progress(-100, 1)['canCare']
    with patch('app.relationships.relationship_day', return_value='2026-09-07'):
        assert db.relationship_progress(-100, 1)['canCare']
        assert db.care_for_partner(-100, 1)
        assert db.relationship_progress(-100, 2)['xp'] == 60


def test_gift_xp_is_atomic_idempotent_and_capped(pair):
    db, _ = pair
    db.add_dig_item(0, 1, 'couple_crystal', 6)
    with patch('app.relationships.relationship_day', return_value='2026-09-06'):
        db.deliver_profile_gift(1, 2, 'couple_crystal', 'one')
        db.deliver_profile_gift(1, 2, 'couple_crystal', 'one')
        assert db.relationship_progress(-100, 1)['xp'] == 30
        for i in range(4):
            db.deliver_profile_gift(1, 2, 'couple_crystal', str(i))
        assert db.relationship_progress(-100, 1)['xp'] == 100
        assert db.relationship_progress(-100, 2)['level'] == 2
    with patch('app.relationships.relationship_day', return_value='2026-09-07'):
        db.deliver_profile_gift(1, 2, 'couple_crystal', 'tomorrow')
        assert db.relationship_progress(-100, 1)['xp'] == 130


def test_only_current_pair_earns_gift_xp(pair):
    db, _ = pair
    db.add_dig_item(0, 1, 'couple_flower', 1)
    db.deliver_profile_gift(1, 3, 'couple_flower', 'other')
    assert db.relationship_progress(-100, 1)['xp'] == 0


def test_breakup_resets_progress_but_preserves_gifts(pair):
    db, _ = pair
    db.care_for_partner(-100, 1)
    db.add_dig_item(0, 1, 'couple_flower', 1)
    db.deliver_profile_gift(1, 2, 'couple_flower', 'flower')
    db.end_chat_couple(-100, 1, 2)
    assert db.relationship_progress(-100, 1) is None
    assert len(db.list_profile_gifts(2)) == 1
    db.create_couple_request(-100, 1, 2)
    db.accept_couple_request(-100, 1, 2)
    assert db.relationship_progress(-100, 1)['xp'] == 0


def test_concurrent_care_requests_charge_once(pair):
    db, path = pair
    def care(_):
        connection = Database(str(path))
        try:
            return connection.care_for_partner(-100, 1)
        finally:
            connection.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(care, (1, 2))) == [False, True]
    assert db.relationship_progress(-100, 1)['xp'] == 20


def test_non_partner_and_unsigned_care_rejected(pair):
    db, path = pair
    with pytest.raises(ValueError):
        db.care_for_partner(-100, 3)
    with pytest.raises(HTTPException) as error:
        miniapp.relationship_care(miniapp.RelationshipCare(chat_id=-100), None)
    assert error.value.status_code == 401
    with patch.object(miniapp, '_telegram_user', return_value={'id': 3}), patch.object(miniapp, '_db', side_effect=lambda: Database(str(path))):
        with pytest.raises(HTTPException) as error:
            miniapp.relationship_care(miniapp.RelationshipCare(chat_id=-100), 'signed')
        assert error.value.status_code == 400
    assert db.relationship_progress(-100, 1)['xp'] == 0


def test_profile_progress_covers_groups_separately(pair):
    db, _ = pair
    db.upsert_chat(-200, 'Other', 'supergroup', None)
    db.create_couple_request(-200, 1, 3)
    db.accept_couple_request(-200, 1, 3)
    db.care_for_partner(-100, 1)
    levels = {row['chatId']: row for row in db.list_relationship_progress(1)}
    assert levels[-100]['xp'] == 20
    assert levels[-200]['xp'] == 0
