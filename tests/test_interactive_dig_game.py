import json
import random
from datetime import datetime

from app import miniapp
from app.db import Database
from app.dig_game import (
    INTERACTIVE_DIG_MAX_CELLS_PER_METER,
    INTERACTIVE_DIG_MIN_CELLS_PER_METER,
    INTERACTIVE_DIG_SUCCESS_CHANCES,
    cell_ore_units,
    cell_row_is_exhausted,
    cell_reward,
    collapse_payout,
    final_cell_chance,
    final_depth_bonus,
    generate_dig_cells,
    generate_dig_stage,
    merchant_ore_price,
    mined_resource_drops,
    mine_resource_price,
    mine_resource_prices,
    mine_type_for_total_depth,
    replacement_cell_stage,
    resolve_cell,
    scale_interactive_reward,
)
from app.miniapp import MineToolUse


def test_generation_keeps_cell_limits() -> None:
    for depth in range(1, 11):
        cells = generate_dig_cells(depth, random.Random(depth))
        kinds = [cell["kind"] for cell in cells]

        assert INTERACTIVE_DIG_MIN_CELLS_PER_METER <= len(cells) <= INTERACTIVE_DIG_MAX_CELLS_PER_METER
        assert kinds.count("normal") >= 2
        assert kinds.count("hard") <= (1 if len(cells) <= 5 else 2)
        assert sum(1 for kind in kinds if kind in {"ore", "hard"}) <= (2 if len(cells) <= 5 else 3)


def test_first_and_tenth_meter_base_chances_are_preserved() -> None:
    assert INTERACTIVE_DIG_SUCCESS_CHANCES[0] == 90.0
    assert INTERACTIVE_DIG_SUCCESS_CHANCES[9] == 1.0


def test_cell_modifiers_and_chance_clamp() -> None:
    ore = resolve_cell({"kind": "ore"}, random.Random(1))
    hard = resolve_cell({"kind": "hard"}, random.Random(1))

    assert ore["chance_modifier"] == -3.0
    assert ore["reward_multiplier"] == 1.35
    assert hard["chance_modifier"] == -8.0
    assert hard["reward_multiplier"] == 1.6
    assert final_cell_chance(90.0, 25.0, {"chance_modifier": 0}) == 100.0
    assert final_cell_chance(1.0, -50.0, {"chance_modifier": -8}) == 1.0


def test_roots_and_unknown_resolve_after_selection() -> None:
    roots = resolve_cell({"kind": "roots"}, random.Random(4))
    unknown = resolve_cell({"kind": "unknown"}, random.Random(8))

    assert roots["resolved_kind"] == "roots"
    assert -4 <= roots["chance_modifier"] <= 4
    assert 0.8 <= roots["reward_multiplier"] <= 1.5
    assert unknown["resolved_kind"] in {"normal", "ore", "hard", "roots"}


def test_temp_reward_and_collapse_payout() -> None:
    assert cell_reward(10, 1.0, {"reward_multiplier": 1.35}, 0) == 14
    assert cell_reward(10, 2.0, {"reward_multiplier": 1.6}, 20) == 39
    assert scale_interactive_reward(14) == 6
    assert scale_interactive_reward(39) == 17
    assert collapse_payout(100) == (70, 30)
    assert collapse_payout(100, protected_loss_percent=10) == (80, 20)


def test_ore_and_merchant_price_are_predictable_for_current_hour() -> None:
    moment = datetime.fromisoformat("2026-07-28T08:15:00+00:00")

    assert cell_ore_units({"resolved_kind": "ore"}) == 1
    assert cell_ore_units({"resolved_kind": "hard"}) == 2
    assert cell_ore_units({"resolved_kind": "normal"}) == 0
    assert merchant_ore_price(moment) == merchant_ore_price(moment.replace(minute=59))
    assert 10 <= merchant_ore_price(moment) <= 40
    assert mine_resource_price("res_iron", moment) == mine_resource_price("res_iron", moment.replace(minute=59))
    assert mine_resource_prices(moment)["res_crystal"] >= 45


def test_manual_mine_cells_drop_sellable_resources() -> None:
    ore_drops = mined_resource_drops({"resolved_kind": "ore"}, "crystal_mine", 8, random.Random(4))
    hard_drops = mined_resource_drops({"resolved_kind": "hard"}, "old_mine", 6, random.Random(1))
    roots_drops = mined_resource_drops({"resolved_kind": "roots"}, "mushroom_cave", 4, random.Random(1))

    assert ore_drops
    assert set(ore_drops) <= {"res_coal", "res_iron", "res_silver", "res_crystal"}
    assert hard_drops["res_stone"] == 2
    assert roots_drops


def test_interactive_session_blocks_same_cell_and_foreign_user(tmp_path) -> None:
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()
    try:
        session = db.create_interactive_dig_session(
            session_id="session1",
            user_id=10,
            chat_id=-100,
            route_key="old_mine",
            depth=0,
            durability=3,
            temporary_coins=0,
            luck_snapshot=100,
            equipment_snapshot=json.dumps({}),
            cells_json=json.dumps(generate_dig_cells(1, random.Random(1))),
        )

        assert db.lock_interactive_dig_cell(session["id"], 11, 0, 0) is None
        locked = db.lock_interactive_dig_cell(session["id"], 10, 0, 0)
        assert locked is not None
        assert db.lock_interactive_dig_cell(session["id"], 10, 0, 0) is None
        db.update_interactive_dig_session(session["id"], used_cells_json=json.dumps([0]), processing=0)
        assert db.lock_interactive_dig_cell(session["id"], 10, 0, 0) is None
    finally:
        db.close()


def test_interactive_session_restores_after_restart(tmp_path) -> None:
    db_path = tmp_path / "bot.sqlite3"
    db = Database(str(db_path))
    db.init()
    try:
        db.create_interactive_dig_session(
            session_id="session2",
            user_id=10,
            chat_id=-100,
            route_key="deep_zone",
            depth=4,
            durability=2,
            temporary_coins=77,
            luck_snapshot=66,
            equipment_snapshot=json.dumps({"route_name": "Глубинная зона"}, ensure_ascii=False),
            cells_json=json.dumps(generate_dig_cells(5, random.Random(5))),
        )

        reopened = Database(str(db_path))
        try:
            restored = reopened.get_active_interactive_dig_session(10)
        finally:
            reopened.close()

        assert restored is not None
        assert restored["route_key"] == "deep_zone"
        assert restored["depth"] == 4
        assert restored["temporary_coins"] == 77
    finally:
        db.close()


def test_mine_type_progression_unlocks_every_ten_total_meters() -> None:
    assert mine_type_for_total_depth(0)["key"] == "old_mine"
    assert mine_type_for_total_depth(10)["key"] == "ice_cave"
    assert mine_type_for_total_depth(20)["key"] == "volcanic_tunnels"
    assert mine_type_for_total_depth(50)["key"] == "crystal_mine"


def test_event_stage_can_replace_cell_row() -> None:
    stage = generate_dig_stage(9, "ancient_ruins", random.Random(1))

    assert stage["type"] in {"cells", "event"}
    if stage["type"] == "event":
        assert stage["choices"]
        assert "title" in stage


def test_failed_row_can_be_replaced_when_all_cells_are_used() -> None:
    cells = [{"kind": "normal"}, {"kind": "hard"}, {"kind": "ore"}]

    assert not cell_row_is_exhausted(cells, [0, 2])
    assert cell_row_is_exhausted(cells, [0, 1, 2])

    stage = replacement_cell_stage(3, "crystal_mine", random.Random(3))

    assert stage["type"] == "cells"
    assert 3 <= len(stage["cells"]) <= 7
    assert cell_row_is_exhausted(stage["cells"], []) is False


def test_miniapp_dynamite_can_misfire_without_breaking_meter(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "bot.sqlite3"
    db = Database(str(db_path))
    db.init()
    cells = [{"kind": "hard"}, {"kind": "normal"}, {"kind": "roots"}]
    db.register_dig_player(0, 10, "miner", "Шахтёр")
    db.add_dig_item(0, 10, "dynamite", 1)
    session = db.create_interactive_dig_session(
        session_id="dynamite-misfire",
        user_id=10,
        chat_id=0,
        route_key="old_mine",
        depth=2,
        durability=3,
        temporary_coins=0,
        luck_snapshot=50,
        equipment_snapshot=json.dumps({"dynamite_count": 1, "used_tools": []}, ensure_ascii=False),
        cells_json=json.dumps({"type": "cells", "cells": cells}, ensure_ascii=False),
    )
    db.close()
    monkeypatch.setattr(miniapp, "_telegram_user", lambda _init_data: {"id": 10, "username": "miner", "first_name": "Шахтёр"})
    monkeypatch.setattr(miniapp, "_db", lambda: Database(str(db_path)))
    monkeypatch.setattr(miniapp.secrets, "randbelow", lambda _limit: 0)

    result = miniapp.miniapp_interactive_tool(MineToolUse(item_key="dynamite"), x_telegram_init_data="test")

    db = Database(str(db_path))
    try:
        updated = db.get_interactive_dig_session(session["id"])
        snapshot = json.loads(updated["equipment_snapshot"])
        stage = json.loads(updated["cells_json"])
    finally:
        db.close()

    assert "взорвался в руках" in result["message"]
    assert "Метр не пробит" in result["message"]
    assert updated["depth"] == 2
    assert updated["durability"] == 2
    assert snapshot["dynamite_count"] == 0
    assert snapshot["used_tools"] == ["dynamite"]
    assert all("revealed" not in cell and "bonus" not in cell for cell in stage["cells"])


def test_depth_ten_has_final_bonus() -> None:
    bonus, text = final_depth_bonus(10, "crystal_mine", random.Random(2))

    assert bonus >= 73
    assert "Финальная находка" in text
