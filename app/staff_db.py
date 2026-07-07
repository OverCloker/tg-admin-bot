import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class StaffDatabase:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self._conn.close()

    def init(self) -> None:
        self._conn.executescript(
            """
            create table if not exists settings (
                key text primary key,
                value text
            );
            create table if not exists bugs (
                id integer primary key autoincrement,
                author_id integer not null,
                author_username text,
                text text not null,
                status text not null default 'OPEN',
                created_at text not null
            );
            create table if not exists tasks (
                id integer primary key autoincrement,
                author_id integer not null,
                author_username text,
                text text not null,
                status text not null default 'OPEN',
                created_at text not null,
                closed_at text
            );
            create table if not exists ideas (
                id integer primary key autoincrement,
                author_id integer not null,
                author_username text,
                text text not null,
                status text not null default 'OPEN',
                created_at text not null
            );
            create table if not exists notes (
                id integer primary key autoincrement,
                author_id integer not null,
                author_username text,
                text text not null,
                created_at text not null
            );
            create table if not exists logs (
                id integer primary key autoincrement,
                level text not null,
                text text not null,
                created_at text not null
            );
            """
        )
        self._conn.commit()

    def setting(self, key: str) -> str | None:
        row = self._conn.execute("select value from settings where key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        self._conn.execute(
            "insert into settings (key, value) values (?, ?) on conflict(key) do update set value = excluded.value",
            (key, value),
        )
        self._conn.commit()

    def add_log(self, level: str, text: str) -> int:
        cur = self._conn.execute(
            "insert into logs (level, text, created_at) values (?, ?, ?)",
            (level.upper(), text, utc_now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def latest_logs(self, limit: int = 10) -> list[sqlite3.Row]:
        return self._conn.execute(
            "select id, level, text, created_at from logs order by id desc limit ?",
            (limit,),
        ).fetchall()

    def add_bug(self, author_id: int, username: str | None, text: str) -> int:
        cur = self._conn.execute(
            "insert into bugs (author_id, author_username, text, status, created_at) values (?, ?, ?, 'OPEN', ?)",
            (author_id, username, text, utc_now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def add_task(self, author_id: int, username: str | None, text: str) -> int:
        cur = self._conn.execute(
            "insert into tasks (author_id, author_username, text, status, created_at) values (?, ?, ?, 'OPEN', ?)",
            (author_id, username, text, utc_now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def open_tasks(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "select id, author_username, text, created_at from tasks where status = 'OPEN' order by id"
        ).fetchall()

    def close_task(self, task_id: int) -> bool:
        cur = self._conn.execute(
            "update tasks set status = 'DONE', closed_at = ? where id = ? and status = 'OPEN'",
            (utc_now(), task_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def add_idea(self, author_id: int, username: str | None, text: str) -> int:
        cur = self._conn.execute(
            "insert into ideas (author_id, author_username, text, status, created_at) values (?, ?, ?, 'OPEN', ?)",
            (author_id, username, text, utc_now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def add_note(self, author_id: int, username: str | None, text: str) -> int:
        cur = self._conn.execute(
            "insert into notes (author_id, author_username, text, created_at) values (?, ?, ?, ?)",
            (author_id, username, text, utc_now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def count_open_bugs(self) -> int:
        return int(self._conn.execute("select count(*) from bugs where status = 'OPEN'").fetchone()[0])

    def count_open_tasks(self) -> int:
        return int(self._conn.execute("select count(*) from tasks where status = 'OPEN'").fetchone()[0])

    def count_auto_replies(self) -> int:
        replies = self._count_if_exists("auto_replies")
        triggers = self._count_if_exists("trigger_replies")
        return replies + triggers

    def known_topics(self, chat_id: int) -> list[sqlite3.Row]:
        exists = self._conn.execute(
            "select 1 from sqlite_master where type = 'table' and name = 'chat_topics'"
        ).fetchone()
        if not exists:
            return []
        return self._conn.execute(
            "select thread_id, title from chat_topics where chat_id = ? order by updated_at desc",
            (chat_id,),
        ).fetchall()

    def _count_if_exists(self, table: str) -> int:
        exists = self._conn.execute(
            "select 1 from sqlite_master where type = 'table' and name = ?",
            (table,),
        ).fetchone()
        return int(self._conn.execute(f"select count(*) from {table}").fetchone()[0]) if exists else 0
