from app.admin_api import api_audit_action, miniapp_shop_purchase_details
from app.db import Database


def test_super_game_audit_has_single_human_start_action() -> None:
    assert api_audit_action("POST", "/miniapp/super-game/start") == "Супер-игра 9×9 начата"
    assert api_audit_action("POST", "/miniapp/super-game/pick") == "Супер-игра 9×9 завершена"


def test_shop_buy_audit_details_include_item_name_and_quantity(tmp_path) -> None:
    db_path = tmp_path / "audit_shop.sqlite3"
    db = Database(str(db_path))
    db.init()
    try:
        db.register_dig_player(0, 42, "miner", "Шахтёр")
        db.add_dig_item(0, 42, "tea", 3)

        assert miniapp_shop_purchase_details(db, 42, "tea") == "купил Чай перед сменой x3"
    finally:
        db.close()
