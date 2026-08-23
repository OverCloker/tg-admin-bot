import json

import pytest
from fastapi import HTTPException

from app import miniapp
from app.admin_api import api_audit_action, should_skip_api_audit
from app.db import Database
from app.miniapp import MinesweeperPick, minesweeper_adjacent_mines, minesweeper_mine_count
from app.miniapp_ui import MINI_APP_HTML


def test_mine_count_scales_with_starting_luck() -> None:
    assert minesweeper_mine_count(100, -2) == 10
    assert minesweeper_mine_count(100, 2) == 10
    assert minesweeper_mine_count(55, 0) == 30
    assert minesweeper_mine_count(10, 2) == 50
    assert minesweeper_mine_count(0, 2) == 50


def test_adjacent_mines_respect_edges_and_corners() -> None:
    mines = {0, 1, 9, 10, 80}

    assert minesweeper_adjacent_mines(0, mines) == 3
    assert minesweeper_adjacent_mines(11, mines) == 2
    assert minesweeper_adjacent_mines(79, mines) == 1


def test_minesweeper_session_persists(tmp_path) -> None:
    db_path = tmp_path / "bot.sqlite3"
    db = Database(str(db_path))
    db.init()
    db.save_minesweeper_game(42, "[0, 8]", '{"4":{"adjacent":1}}', 2, 100, 4, "2026-08-23T10:00:00+00:00")
    db.close()

    reopened = Database(str(db_path))
    try:
        session = reopened.get_minesweeper_game(42)
        assert session is not None
        assert json.loads(session["mines_json"]) == [0, 8]
        assert session["earned_coins"] == 4
        reopened.clear_minesweeper_game(42)
        assert reopened.get_minesweeper_game(42) is None
    finally:
        reopened.close()


def test_safe_pick_is_paid_once_and_mine_costs_luck(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "bot.sqlite3"
    db = Database(str(db_path))
    db.init()
    db.register_dig_player(0, 10, "miner", "Шахтёр")
    db.save_minesweeper_game(10, "[0]", "{}", 1, 100, 0, "2026-08-23T10:00:00+00:00")
    db.close()

    monkeypatch.setattr(miniapp, "_telegram_user", lambda _data: {"id": 10})
    monkeypatch.setattr(miniapp, "_db", lambda: Database(str(db_path)))
    monkeypatch.setattr(miniapp.secrets, "randbelow", lambda limit: limit - 1)

    safe = miniapp.minesweeper_pick(MinesweeperPick(cell=1), x_telegram_init_data="test")
    assert safe["mine"] is False
    assert safe["adjacent"] == 1
    assert safe["coins"] == 6

    with pytest.raises(HTTPException, match="уже открыта"):
        miniapp.minesweeper_pick(MinesweeperPick(cell=1), x_telegram_init_data="test")

    hit = miniapp.minesweeper_pick(MinesweeperPick(cell=0), x_telegram_init_data="test")
    assert hit["mine"] is True
    assert hit["luckLost"] == 10
    assert hit["state"]["luck"] == 90

    db = Database(str(db_path))
    try:
        assert db.get_dig_player(0, 10).coins == 6
        assert db.get_minesweeper_game(10) is None
    finally:
        db.close()


def test_minesweeper_ui_and_audit_are_compact() -> None:
    assert "Сапёр 9×9" in MINI_APP_HTML
    assert "minesweeper-grid" in MINI_APP_HTML
    assert "mine-tile-mark" in MINI_APP_HTML
    assert "Ну ты и лох!" in MINI_APP_HTML
    assert "showMinesweeperLoss(result)" in MINI_APP_HTML
    assert "await revealMinesweeperField(result)" in MINI_APP_HTML
    assert "Поле раскрыто. Итоги через" in MINI_APP_HTML
    assert "hit-mine" in MINI_APP_HTML
    assert 'api("/miniapp/minesweeper/pick"' in MINI_APP_HTML
    assert api_audit_action("POST", "/miniapp/minesweeper/start") == "Сапёр 9×9 начат"
    assert should_skip_api_audit("/miniapp/minesweeper/pick")
    assert not should_skip_api_audit("/miniapp/minesweeper/exit")
