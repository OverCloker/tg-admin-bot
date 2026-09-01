from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = """
create table if not exists media_files (
    id integer primary key,
    path text not null unique,
    filename text not null,
    size integer not null,
    modified real not null,
    fingerprint text not null,
    status text not null default 'SCANNED',
    updated_at text not null
);
create table if not exists metadata_cache (
    cache_key text primary key,
    provider text not null,
    payload text not null,
    updated_at text not null
);
create table if not exists metadata_selections (
    lookup_key text primary key,
    payload text not null,
    updated_at text not null
);
create table if not exists publication_state (
    operation_key text primary key,
    card_sent integer not null default 0,
    next_batch integer not null default 0,
    completed integer not null default 0,
    error_text text,
    updated_at text not null
);
create table if not exists publications (
    id integer primary key,
    season_key text not null,
    batch_key text not null unique,
    chat_id text not null,
    card_message_id integer,
    status text not null,
    published_at text,
    error_text text
);
create table if not exists settings (key text primary key, value text not null);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class PublisherDatabase:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def remember_files(self, files) -> None:
        for item in files:
            stat = item.path.stat()
            fingerprint = hashlib.sha256(f"{item.path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}".encode()).hexdigest()
            self.connection.execute(
                "insert into media_files(path,filename,size,modified,fingerprint,status,updated_at) values(?,?,?,?,?,?,?) "
                "on conflict(path) do update set filename=excluded.filename,size=excluded.size,modified=excluded.modified,fingerprint=excluded.fingerprint,updated_at=excluded.updated_at",
                (str(item.path.resolve()), item.filename, stat.st_size, stat.st_mtime, fingerprint, "SCANNED", _now()),
            )
        self.connection.commit()

    def publication_status(self, path: str | Path) -> str | None:
        row = self.connection.execute("select status from media_files where path = ?", (str(Path(path).resolve()),)).fetchone()
        return str(row["status"]) if row else None

    def set_file_status(self, path: str | Path, status: str) -> None:
        self.connection.execute("update media_files set status=?, updated_at=? where path=?", (status, _now(), str(Path(path).resolve())))
        self.connection.commit()

    def load_metadata_selection(self, lookup_key: str) -> str | None:
        row = self.connection.execute("select payload from metadata_selections where lookup_key=?", (lookup_key,)).fetchone()
        return str(row["payload"]) if row else None

    def save_metadata_selection(self, lookup_key: str, payload: str) -> None:
        self.connection.execute(
            "insert or replace into metadata_selections(lookup_key,payload,updated_at) values(?,?,?)",
            (lookup_key, payload, _now()),
        )
        self.connection.commit()

    def publication_state(self, operation_key: str) -> dict:
        row = self.connection.execute("select * from publication_state where operation_key=?", (operation_key,)).fetchone()
        return dict(row) if row else {"card_sent": 0, "next_batch": 0, "completed": 0, "error_text": None}

    def save_publication_state(self, operation_key: str, *, card_sent: int, next_batch: int, completed: int, error_text: str | None = None) -> None:
        self.connection.execute(
            "insert or replace into publication_state(operation_key,card_sent,next_batch,completed,error_text,updated_at) values(?,?,?,?,?,?)",
            (operation_key, card_sent, next_batch, completed, error_text, _now()),
        )
        self.connection.commit()
