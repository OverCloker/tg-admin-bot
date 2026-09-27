import sqlite3
from pathlib import Path

import pytest

from app.restore_repair import repair


def recovered_copy(tmp_path):
    original = Path(__file__).resolve().parents[1] / 'bot.sqlite3'
    if not original.exists():
        pytest.skip('Recovered local database unavailable')
    path = tmp_path / 'bot.sqlite3'
    with sqlite3.connect(original.as_uri() + '?mode=ro', uri=True) as source, sqlite3.connect(path) as target:
        source.backup(target)
    return path


def test_repair_preserves_inventory_archives_orphans_and_is_idempotent(tmp_path):
    path = recovered_copy(tmp_path)
    with sqlite3.connect(path) as c:
        inventory = c.execute('SELECT * FROM dig_items ORDER BY chat_id,user_id,item_key').fetchall()
        chats = c.execute('SELECT * FROM chats ORDER BY chat_id').fetchall()
        ids = {row[0] for row in c.execute('SELECT DISTINCT chat_id FROM seen_users WHERE chat_id NOT IN (SELECT chat_id FROM chats)')}
    result = repair(path, ids)
    assert result['audit']['ok'], result
    assert result['archivedRecords'] == 130  # 84 orphans plus 46 dependent activity records
    assert result['restoredPlayers'] == 2
    assert Path(result['backup']).exists()
    with sqlite3.connect(path) as c:
        assert c.execute('SELECT * FROM dig_items ORDER BY chat_id,user_id,item_key').fetchall() == inventory
        assert c.execute('SELECT * FROM chats ORDER BY chat_id').fetchall() == chats
        assert c.execute('SELECT COUNT(*) FROM restore_record_archive').fetchone()[0] == 130
        assert c.execute('PRAGMA foreign_key_list(dig_players)').fetchall() == []
    repeated = repair(path, ids)
    assert repeated['archivedRecords'] == repeated['restoredPlayers'] == 0
    assert repeated['audit']['ok']


def test_unapproved_chats_abort_data_changes(tmp_path):
    path = recovered_copy(tmp_path)
    with pytest.raises(RuntimeError, match='Unresolved relationships'):
        repair(path, {-999999})
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='restore_record_archive'").fetchone()[0] == 0


def test_rejects_global_chat_for_archiving(tmp_path):
    with pytest.raises(ValueError):
        repair(tmp_path / 'none.sqlite3', {0})
