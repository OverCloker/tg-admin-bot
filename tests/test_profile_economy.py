import json

import pytest
from fastapi import HTTPException

from app import miniapp
from app.db import Database
from app.user_profile import _profile_cosmetics


@pytest.fixture
def db(tmp_path):
    service = Database(str(tmp_path / 'economy.sqlite3'))
    service.init()
    service.register_dig_player(0, 1, 'sender', 'Sender')
    service.register_dig_player(0, 2, 'recipient', 'Recipient')
    yield service
    service.close()


def test_gifts_are_consumed_once_and_cannot_be_recirculated(db):
    db.add_dig_item(0, 1, 'gift_yarn', 2)
    assert db.deliver_profile_gift(1, 2, 'gift_yarn', 'one') == 'sent'
    assert db.deliver_profile_gift(1, 2, 'gift_yarn', 'one') == 'duplicate'
    assert len(db.list_profile_gifts(2)) == 1
    assert db.deliver_profile_gift(2, 1, 'gift_yarn', 'two') == 'empty'
    assert db.deliver_profile_gift(1, 2, 'gift_yarn', 'three') == 'sent'
    assert db.deliver_profile_gift(1, 2, 'gift_yarn', 'four') == 'empty'


def test_only_recipient_can_pin_gift(db):
    db.add_dig_item(0, 1, 'gift_yarn', 1)
    db.deliver_profile_gift(1, 2, 'gift_yarn', 'one')
    gift = db.list_profile_gifts(2)[0]
    assert not db.pin_profile_gift(1, gift['id'], True)
    assert db.pin_profile_gift(2, gift['id'], True)
    assert db.list_profile_gifts(2)[0]['pinned'] == 1


def test_style_selection_uses_owned_items_and_can_remove_them(db):
    items = {'profile_frame_copper': 1, 'profile_frame_crystal': 1}
    assert _profile_cosmetics(items, {'frame': 'profile_frame_copper'})['frame']['key'] == 'profile_frame_copper'
    assert _profile_cosmetics(items, {'frame': 'profile_frame_aurora'})['frame'] is None
    db.set_profile_style(1, {'frame': ''})
    assert _profile_cosmetics(items, db.get_profile_style(1))['frame'] is None


def test_cannot_equip_unpurchased_decoration(db, monkeypatch):
    monkeypatch.setattr(miniapp, '_telegram_user', lambda data: {'id': 1})
    monkeypatch.setattr(miniapp, '_db', lambda: db)
    monkeypatch.setattr(db, 'close', lambda: None)
    with pytest.raises(HTTPException) as error:
        miniapp.profile_style(miniapp.ProfileStyleSet(frame='profile_frame_aurora'), 'signed')
    assert error.value.status_code == 400
    assert db.get_profile_style(1) is None


def test_hint_charges_once_and_never_reveals_a_mine(db):
    db.add_dig_coins(0, 1, 100)
    db.save_minesweeper_game(1, json.dumps([0, 1]), '{}', 2, 100, 0, '2026-09-05T00:00:00+00:00')
    cell = db.buy_minesweeper_hint(1)
    assert cell not in (0, 1)
    assert db.buy_minesweeper_hint(1) == cell
    assert db.get_dig_player(0, 1).coins == 40
    db.clear_minesweeper_game(1)
    db.save_minesweeper_game(1, json.dumps([2, 3]), '{}', 2, 100, 0, '2026-09-05T00:01:00+00:00')
    with pytest.raises(ValueError):
        db.buy_minesweeper_hint(1)
    assert db.get_dig_player(0, 1).coins == 40


def test_new_endpoints_require_telegram_auth():
    for call in [lambda: miniapp.profile_wardrobe(None), lambda: miniapp.profile_style(miniapp.ProfileStyleSet(), None), lambda: miniapp.minesweeper_hint(None)]:
        with pytest.raises(HTTPException) as error:
            call()
        assert error.value.status_code == 401


def test_gift_failure_rolls_back_consumption(db):
    db.add_dig_item(0, 1, 'gift_yarn', 1)
    db._conn.execute("create trigger reject_gift before insert on profile_gifts begin select raise(ABORT, 'test failure'); end")
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        db.deliver_profile_gift(1, 2, 'gift_yarn', 'one')
    db._conn.execute('drop trigger reject_gift')
    assert db.deliver_profile_gift(1, 2, 'gift_yarn', 'one') == 'sent'


def test_request_id_cannot_be_reused_for_another_recipient(db):
    db.add_dig_item(0, 1, 'gift_yarn', 2)
    db.deliver_profile_gift(1, 2, 'gift_yarn', 'one')
    with pytest.raises(ValueError):
        db.deliver_profile_gift(1, 3, 'gift_yarn', 'one')
    assert db.list_profile_gifts(3) == []


def test_expensive_cosmetics_are_unique_purchases(db):
    from app import bot
    key = 'profile_frame_aurora'
    assert key in bot.DIG_PERMANENT_ITEMS
    db.add_dig_coins(0, 1, 15000)
    db.purchase_dig_item(0, 1, key, bot.DIG_SHOP_ITEMS[key][1], unique=True)
    db.purchase_dig_item(0, 1, key, bot.DIG_SHOP_ITEMS[key][1], unique=True)
    assert db.get_dig_player(0, 1).coins == 7500
