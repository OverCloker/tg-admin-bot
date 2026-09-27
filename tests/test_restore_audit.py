import sqlite3
from pathlib import Path

from app.db import Database
from app.restore_audit import audit_database


def test_current_schema_passes_without_changes(tmp_path):
    path = tmp_path / "bot.sqlite3"
    db = Database(str(path))
    db.init()
    db.close()
    before = path.read_bytes()
    assert audit_database(path)["ok"]
    assert path.read_bytes() == before


def test_old_schema_reports_missing_tables_without_migrating(tmp_path):
    path = tmp_path / "bot.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE chats (chat_id integer primary key)")
    before = path.read_bytes()
    result = audit_database(path)
    assert not result["ok"]
    assert "missing column: chats.title" in result["schemaIssues"]
    assert path.read_bytes() == before


def test_missing_database_is_not_created(tmp_path):
    import pytest
    path = tmp_path / "missing.sqlite3"
    with pytest.raises(sqlite3.OperationalError):
        audit_database(path)
    assert not path.exists()


def test_entrypoint_writes_marker_as_volume_owner():
    script = (Path(__file__).resolve().parents[1] / "docker-entrypoint.sh").read_text()
    assert 'gosu app touch "$marker"' in script
    assert '\n        touch "$marker"' not in script


def test_recovered_database_migrates_idempotently(tmp_path):
    import pytest
    original = Path(__file__).resolve().parents[1] / "bot.sqlite3"
    if not original.is_file():
        pytest.skip("Recovered local database not available")
    path = tmp_path / "restored.sqlite3"
    with sqlite3.connect(original.as_uri() + "?mode=ro", uri=True) as source, sqlite3.connect(path) as target:
        source.backup(target)
        counts = {name: source.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
                  for name in ("chats", "advertisements")}
    db = Database(str(path))
    db.init()
    db.init()
    db.close()
    result = audit_database(path)
    assert result["schemaOk"], result["schemaIssues"]
    assert result["integrity"] == ["ok"]
    with sqlite3.connect(path) as migrated:
        for name, count in counts.items():
            assert migrated.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] == count
