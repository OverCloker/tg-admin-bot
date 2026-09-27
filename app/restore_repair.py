"""Explicit, backed-up repair of approved orphaned recovery records."""
import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .db import Database
from .restore_audit import audit_database


def repair(path: Path, chat_ids: set[int]) -> dict:
    if not chat_ids or any(value >= 0 for value in chat_ids):
        raise ValueError("Explicit negative Telegram chat IDs required")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"bot-before-repair-{stamp}-{uuid4().hex[:8]}.sqlite3")
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as source, sqlite3.connect(backup) as target:
        source.backup(target)
    os.chmod(backup, 0o600)
    database = Database(str(path))
    try:
        database.init()
    finally:
        database.close()
    batch = uuid4().hex
    archived = 0
    restored = 0
    with sqlite3.connect(path) as c:
        c.row_factory = sqlite3.Row
        c.execute('BEGIN IMMEDIATE')
        c.execute('CREATE TABLE IF NOT EXISTS restore_record_archive (batch TEXT NOT NULL, source_table TEXT NOT NULL, source_rowid INTEGER NOT NULL, payload TEXT NOT NULL, archived_at TEXT NOT NULL)')
        # Repeat for dependent activity records after archiving their seen_users.
        # Only explicitly approved chat IDs are ever removed, even in descendants.
        while True:
            removed = 0
            violations = c.execute('PRAGMA foreign_key_check').fetchall()
            for table, rowid, parent, _ in violations:
                quoted = table.replace('"', '""')
                row = c.execute(f'SELECT * FROM "{quoted}" WHERE rowid=?', (rowid,)).fetchone()
                if row is None or 'chat_id' not in row.keys() or row['chat_id'] not in chat_ids:
                    continue
                c.execute('INSERT INTO restore_record_archive VALUES (?,?,?,?,?)',
                          (batch, table, rowid, json.dumps(dict(row), ensure_ascii=False), stamp))
                c.execute(f'DELETE FROM "{quoted}" WHERE rowid=?', (rowid,))
                archived += 1
                removed += 1
            if not removed:
                break
        for row in c.execute('SELECT DISTINCT i.user_id FROM dig_items i LEFT JOIN dig_players p ON p.chat_id=i.chat_id AND p.user_id=i.user_id WHERE i.chat_id=0 AND p.user_id IS NULL').fetchall():
            user_id = row['user_id']
            identity = c.execute('SELECT username,full_name FROM seen_users WHERE user_id=? ORDER BY updated_at DESC LIMIT 1', (user_id,)).fetchone()
            name = identity['full_name'] if identity else f'User {user_id}'
            username = identity['username'] if identity else None
            now = datetime.now(timezone.utc).isoformat()
            c.execute('INSERT INTO dig_players (chat_id,user_id,username,full_name,coins,total_depth,best_session_depth,luck,last_luck_at,created_at,updated_at) VALUES (0,?,?,?,0,0,0,100,?,?,?)', (user_id, username, name, now, now, now))
            restored += 1
        remaining = c.execute('PRAGMA foreign_key_check').fetchall()
        if remaining:
            raise RuntimeError("Unresolved relationships: data transaction rolled back; backup retained: " + str([tuple(row) for row in remaining]))
        if c.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError("Integrity check failed; data transaction rolled back")
    result = audit_database(path)
    return {"backup": str(backup), "archivedRecords": archived,
            "restoredPlayers": restored, "audit": result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--archive-chats', required=True, help='Comma-separated approved chat IDs')
    args = parser.parse_args()
    print(json.dumps(repair(args.database, {int(value) for value in args.archive_chats.split(',')}), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
