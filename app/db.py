import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
import json


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class AutoReply:
    chat_id: int
    username: str
    text: str
    updated_by: int | None
    updated_at: str


@dataclass(frozen=True)
class RegisteredChat:
    chat_id: int
    title: str
    type: str
    username: str | None
    updated_at: str


@dataclass(frozen=True)
class TriggerReply:
    chat_id: int
    trigger: str
    text: str
    updated_by: int | None
    updated_at: str


@dataclass(frozen=True)
class SeenUser:
    chat_id: int
    user_id: int
    username: str | None
    full_name: str
    is_bot: int
    updated_at: str


@dataclass(frozen=True)
class ChatTopic:
    chat_id: int
    thread_id: int
    title: str
    updated_at: str


@dataclass(frozen=True)
class GiveawaySettings:
    chat_id: int
    trigger: str
    title: str
    winners_count: int
    updated_by: int | None
    updated_at: str


@dataclass(frozen=True)
class AlarmSettings:
    chat_id: int
    enabled: int
    permissions_json: str | None
    reactions_json: str | None
    alarm_text: str | None
    clear_text: str | None
    updated_by: int | None
    updated_at: str


@dataclass(frozen=True)
class GiveawayStat:
    chat_id: int
    user_id: int
    username: str | None
    full_name: str
    wins_count: int


@dataclass(frozen=True)
class StarPayment:
    id: int
    user_id: int
    username: str | None
    full_name: str
    chat_id: int | None
    amount: int
    currency: str
    charge_id: str
    created_at: str


@dataclass(frozen=True)
class Quote:
    id: int
    chat_id: int
    text: str
    author_name: str | None
    added_by: int | None
    created_at: str


@dataclass(frozen=True)
class Birthday:
    id: int
    chat_id: int
    day: int
    month: int
    text: str
    added_by: int | None
    created_at: str


@dataclass(frozen=True)
class BlacklistWord:
    chat_id: int
    word: str
    added_by: int | None
    created_at: str


@dataclass(frozen=True)
class RollMuteSettings:
    chat_id: int
    mute_minutes: int
    cooldown_minutes: int
    updated_by: int | None
    updated_at: str
    last_used_at: str | None


@dataclass(frozen=True)
class RollMuteStat:
    chat_id: int
    user_id: int
    username: str | None
    full_name: str
    unlucky_count: int


@dataclass(frozen=True)
class QuietSettings:
    chat_id: int
    reply_text: str | None
    media_type: str | None
    media_file_id: str | None
    updated_by: int | None
    updated_at: str


class Database:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self._conn.close()

    def init(self) -> None:
        self._conn.executescript(
            """
            create table if not exists chats (
                chat_id integer primary key,
                title text not null,
                type text not null,
                username text,
                updated_at text not null
            );

            create table if not exists auto_replies (
                chat_id integer not null,
                username text not null,
                text text not null,
                updated_by integer,
                updated_at text not null,
                primary key (chat_id, username),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists trigger_replies (
                chat_id integer not null,
                trigger text not null,
                text text not null,
                updated_by integer,
                updated_at text not null,
                primary key (chat_id, trigger),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists seen_users (
                chat_id integer not null,
                user_id integer not null,
                username text,
                full_name text not null,
                is_bot integer not null default 0,
                updated_at text not null,
                primary key (chat_id, user_id),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists daily_picks (
                chat_id integer not null,
                pick_key text not null,
                pick_date text not null,
                user_id integer not null,
                created_at text not null,
                primary key (chat_id, pick_key, pick_date),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists chat_topics (
                chat_id integer not null,
                thread_id integer not null,
                title text not null,
                updated_at text not null,
                primary key (chat_id, thread_id),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists giveaway_settings (
                chat_id integer primary key,
                trigger text not null,
                title text not null,
                winners_count integer not null default 1,
                updated_by integer,
                updated_at text not null,
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists giveaway_daily_picks (
                chat_id integer not null,
                pick_key text not null,
                pick_date text not null,
                pick_rank integer not null,
                user_id integer not null,
                created_at text not null,
                primary key (chat_id, pick_key, pick_date, pick_rank),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists alarm_settings (
                chat_id integer primary key,
                enabled integer not null default 0,
                permissions_json text,
                reactions_json text,
                alarm_text text,
                clear_text text,
                updated_by integer,
                updated_at text not null,
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists giveaway_stats (
                chat_id integer not null,
                user_id integer not null,
                wins_count integer not null default 0,
                updated_at text not null,
                primary key (chat_id, user_id),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists giveaway_stat_awards (
                chat_id integer not null,
                pick_key text not null,
                pick_date text not null,
                created_at text not null,
                primary key (chat_id, pick_key, pick_date),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists star_payments (
                id integer primary key autoincrement,
                user_id integer not null,
                username text,
                full_name text not null,
                chat_id integer,
                amount integer not null,
                currency text not null,
                charge_id text not null,
                created_at text not null
            );

            create table if not exists quotes (
                id integer primary key autoincrement,
                chat_id integer not null,
                text text not null,
                author_name text,
                added_by integer,
                created_at text not null,
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists birthdays (
                id integer primary key autoincrement,
                chat_id integer not null,
                day integer not null,
                month integer not null,
                text text not null,
                added_by integer,
                created_at text not null,
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists birthday_sent (
                chat_id integer not null,
                birthday_id integer not null,
                sent_date text not null,
                primary key (chat_id, birthday_id, sent_date),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists blacklist_words (
                chat_id integer not null,
                word text not null,
                added_by integer,
                created_at text not null,
                primary key (chat_id, word),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists roll_mute_settings (
                chat_id integer primary key,
                mute_minutes integer not null default 60,
                cooldown_minutes integer not null default 30,
                updated_by integer,
                updated_at text not null,
                last_used_at text,
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists roll_mute_stats (
                chat_id integer not null,
                user_id integer not null,
                unlucky_count integer not null default 0,
                updated_at text not null,
                primary key (chat_id, user_id),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists quiet_settings (
                chat_id integer primary key,
                reply_text text,
                media_type text,
                media_file_id text,
                updated_by integer,
                updated_at text not null,
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );
            """
        )
        self._migrate_alarm_settings()
        self._conn.commit()

    def _migrate_alarm_settings(self) -> None:
        columns = {
            row["name"]
            for row in self._conn.execute("pragma table_info(alarm_settings)").fetchall()
        }
        if "alarm_text" not in columns:
            self._conn.execute("alter table alarm_settings add column alarm_text text")
        if "clear_text" not in columns:
            self._conn.execute("alter table alarm_settings add column clear_text text")
        if "reactions_json" not in columns:
            self._conn.execute("alter table alarm_settings add column reactions_json text")

    def upsert_chat(self, chat_id: int, title: str, chat_type: str, username: str | None) -> None:
        self._conn.execute(
            """
            insert into chats (chat_id, title, type, username, updated_at)
            values (?, ?, ?, ?, ?)
            on conflict(chat_id) do update set
                title = excluded.title,
                type = excluded.type,
                username = excluded.username,
                updated_at = excluded.updated_at
            """,
            (chat_id, title, chat_type, username, utc_now()),
        )
        self._conn.commit()

    def list_chats(self) -> list[RegisteredChat]:
        rows = self._conn.execute(
            "select chat_id, title, type, username, updated_at from chats order by title collate nocase"
        ).fetchall()
        return [RegisteredChat(**dict(row)) for row in rows]

    def get_chat(self, chat_id: int) -> RegisteredChat | None:
        row = self._conn.execute(
            "select chat_id, title, type, username, updated_at from chats where chat_id = ?",
            (chat_id,),
        ).fetchone()
        return RegisteredChat(**dict(row)) if row else None

    def delete_chat(self, chat_id: int) -> None:
        self._conn.execute("delete from chats where chat_id = ?", (chat_id,))
        self._conn.commit()

    def set_reply(self, chat_id: int, username: str, text: str, updated_by: int | None) -> None:
        self._conn.execute(
            """
            insert into auto_replies (chat_id, username, text, updated_by, updated_at)
            values (?, ?, ?, ?, ?)
            on conflict(chat_id, username) do update set
                text = excluded.text,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (chat_id, normalize_username(username), text.strip(), updated_by, utc_now()),
        )
        self._conn.commit()

    def delete_reply(self, chat_id: int, username: str) -> bool:
        cur = self._conn.execute(
            "delete from auto_replies where chat_id = ? and username = ?",
            (chat_id, normalize_username(username)),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def get_reply(self, chat_id: int, username: str) -> AutoReply | None:
        row = self._conn.execute(
            """
            select chat_id, username, text, updated_by, updated_at
            from auto_replies
            where chat_id = ? and username = ?
            """,
            (chat_id, normalize_username(username)),
        ).fetchone()
        return AutoReply(**dict(row)) if row else None

    def list_replies(self, chat_id: int) -> list[AutoReply]:
        rows = self._conn.execute(
            """
            select chat_id, username, text, updated_by, updated_at
            from auto_replies
            where chat_id = ?
            order by username collate nocase
            """,
            (chat_id,),
        ).fetchall()
        return [AutoReply(**dict(row)) for row in rows]

    def replies_for_mentions(self, chat_id: int, usernames: Iterable[str]) -> list[AutoReply]:
        normalized = sorted({normalize_username(item) for item in usernames if item})
        if not normalized:
            return []

        placeholders = ",".join("?" for _ in normalized)
        rows = self._conn.execute(
            f"""
            select chat_id, username, text, updated_by, updated_at
            from auto_replies
            where chat_id = ? and username in ({placeholders})
            order by username collate nocase
            """,
            (chat_id, *normalized),
        ).fetchall()
        return [AutoReply(**dict(row)) for row in rows]

    def set_trigger(self, chat_id: int, trigger: str, text: str, updated_by: int | None) -> None:
        self._conn.execute(
            """
            insert into trigger_replies (chat_id, trigger, text, updated_by, updated_at)
            values (?, ?, ?, ?, ?)
            on conflict(chat_id, trigger) do update set
                text = excluded.text,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (chat_id, normalize_trigger(trigger), text.strip(), updated_by, utc_now()),
        )
        self._conn.commit()

    def delete_trigger(self, chat_id: int, trigger: str) -> bool:
        cur = self._conn.execute(
            "delete from trigger_replies where chat_id = ? and trigger = ?",
            (chat_id, normalize_trigger(trigger)),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def list_triggers(self, chat_id: int) -> list[TriggerReply]:
        rows = self._conn.execute(
            """
            select chat_id, trigger, text, updated_by, updated_at
            from trigger_replies
            where chat_id = ?
            order by trigger collate nocase
            """,
            (chat_id,),
        ).fetchall()
        return [TriggerReply(**dict(row)) for row in rows]

    def upsert_seen_user(
        self,
        chat_id: int,
        user_id: int,
        username: str | None,
        full_name: str,
        is_bot: bool,
    ) -> None:
        self._conn.execute(
            """
            insert into seen_users (chat_id, user_id, username, full_name, is_bot, updated_at)
            values (?, ?, ?, ?, ?, ?)
            on conflict(chat_id, user_id) do update set
                username = excluded.username,
                full_name = excluded.full_name,
                is_bot = excluded.is_bot,
                updated_at = excluded.updated_at
            """,
            (chat_id, user_id, normalize_username(username) if username else None, full_name, int(is_bot), utc_now()),
        )
        self._conn.commit()

    def list_pickable_users(self, chat_id: int) -> list[SeenUser]:
        rows = self._conn.execute(
            """
            select chat_id, user_id, username, full_name, is_bot, updated_at
            from seen_users
            where chat_id = ? and is_bot = 0 and username is not null
            order by updated_at desc
            """,
            (chat_id,),
        ).fetchall()
        return [SeenUser(**dict(row)) for row in rows]

    def get_seen_user_by_username(self, chat_id: int, username: str) -> SeenUser | None:
        row = self._conn.execute(
            """
            select chat_id, user_id, username, full_name, is_bot, updated_at
            from seen_users
            where chat_id = ? and username = ? and is_bot = 0
            """,
            (chat_id, normalize_username(username)),
        ).fetchone()
        return SeenUser(**dict(row)) if row else None

    def get_daily_pick(self, chat_id: int, pick_key: str, pick_date: str) -> SeenUser | None:
        row = self._conn.execute(
            """
            select u.chat_id, u.user_id, u.username, u.full_name, u.is_bot, u.updated_at
            from daily_picks p
            join seen_users u on u.chat_id = p.chat_id and u.user_id = p.user_id
            where p.chat_id = ? and p.pick_key = ? and p.pick_date = ?
            """,
            (chat_id, pick_key, pick_date),
        ).fetchone()
        return SeenUser(**dict(row)) if row else None

    def set_daily_pick(self, chat_id: int, pick_key: str, pick_date: str, user_id: int) -> None:
        self._conn.execute(
            """
            insert or replace into daily_picks (chat_id, pick_key, pick_date, user_id, created_at)
            values (?, ?, ?, ?, ?)
            """,
            (chat_id, pick_key, pick_date, user_id, utc_now()),
        )
        self._conn.commit()

    def upsert_topic(self, chat_id: int, thread_id: int, title: str) -> None:
        self._conn.execute(
            """
            insert into chat_topics (chat_id, thread_id, title, updated_at)
            values (?, ?, ?, ?)
            on conflict(chat_id, thread_id) do update set
                title = excluded.title,
                updated_at = excluded.updated_at
            """,
            (chat_id, thread_id, title, utc_now()),
        )
        self._conn.commit()

    def list_topics(self, chat_id: int) -> list[ChatTopic]:
        rows = self._conn.execute(
            """
            select chat_id, thread_id, title, updated_at
            from chat_topics
            where chat_id = ?
            order by updated_at desc
            """,
            (chat_id,),
        ).fetchall()
        return [ChatTopic(**dict(row)) for row in rows]

    def delete_topics(self, chat_id: int) -> None:
        self._conn.execute("delete from chat_topics where chat_id = ?", (chat_id,))
        self._conn.commit()

    def get_giveaway_settings(self, chat_id: int) -> GiveawaySettings:
        row = self._conn.execute(
            """
            select chat_id, trigger, title, winners_count, updated_by, updated_at
            from giveaway_settings
            where chat_id = ?
            """,
            (chat_id,),
        ).fetchone()
        if row:
            return GiveawaySettings(**dict(row))

        return GiveawaySettings(
            chat_id=chat_id,
            trigger=normalize_trigger("кто пидор"),
            title="Пидор дня",
            winners_count=1,
            updated_by=None,
            updated_at=utc_now(),
        )

    def set_giveaway_settings(
        self,
        chat_id: int,
        trigger: str,
        title: str,
        winners_count: int,
        updated_by: int | None,
    ) -> None:
        count = max(1, min(20, int(winners_count)))
        self._conn.execute(
            """
            insert into giveaway_settings (chat_id, trigger, title, winners_count, updated_by, updated_at)
            values (?, ?, ?, ?, ?, ?)
            on conflict(chat_id) do update set
                trigger = excluded.trigger,
                title = excluded.title,
                winners_count = excluded.winners_count,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (chat_id, normalize_trigger(trigger), title.strip(), count, updated_by, utc_now()),
        )
        self._conn.commit()

    def get_giveaway_picks(self, chat_id: int, pick_key: str, pick_date: str) -> list[SeenUser]:
        rows = self._conn.execute(
            """
            select u.chat_id, u.user_id, u.username, u.full_name, u.is_bot, u.updated_at
            from giveaway_daily_picks p
            join seen_users u on u.chat_id = p.chat_id and u.user_id = p.user_id
            where p.chat_id = ? and p.pick_key = ? and p.pick_date = ?
            order by p.pick_rank
            """,
            (chat_id, pick_key, pick_date),
        ).fetchall()
        return [SeenUser(**dict(row)) for row in rows]

    def set_giveaway_picks(self, chat_id: int, pick_key: str, pick_date: str, user_ids: list[int]) -> None:
        self._conn.execute(
            "delete from giveaway_daily_picks where chat_id = ? and pick_key = ? and pick_date = ?",
            (chat_id, pick_key, pick_date),
        )
        for index, user_id in enumerate(user_ids, start=1):
            self._conn.execute(
                """
                insert into giveaway_daily_picks (chat_id, pick_key, pick_date, pick_rank, user_id, created_at)
                values (?, ?, ?, ?, ?, ?)
                """,
                (chat_id, pick_key, pick_date, index, user_id, utc_now()),
            )
        self._conn.commit()

    def increment_giveaway_stats(self, chat_id: int, user_ids: list[int]) -> None:
        for user_id in user_ids:
            self._conn.execute(
                """
                insert into giveaway_stats (chat_id, user_id, wins_count, updated_at)
                values (?, ?, 1, ?)
                on conflict(chat_id, user_id) do update set
                    wins_count = wins_count + 1,
                    updated_at = excluded.updated_at
                """,
                (chat_id, user_id, utc_now()),
            )
        self._conn.commit()

    def award_giveaway_stats_once(self, chat_id: int, pick_key: str, pick_date: str, user_ids: list[int]) -> bool:
        cur = self._conn.execute(
            """
            insert or ignore into giveaway_stat_awards (chat_id, pick_key, pick_date, created_at)
            values (?, ?, ?, ?)
            """,
            (chat_id, pick_key, pick_date, utc_now()),
        )
        if cur.rowcount == 0:
            self._conn.commit()
            return False

        for user_id in user_ids:
            self._conn.execute(
                """
                insert into giveaway_stats (chat_id, user_id, wins_count, updated_at)
                values (?, ?, 1, ?)
                on conflict(chat_id, user_id) do update set
                    wins_count = wins_count + 1,
                    updated_at = excluded.updated_at
                """,
                (chat_id, user_id, utc_now()),
            )
        self._conn.commit()
        return True

    def top_giveaway_stats(self, chat_id: int, limit: int = 10) -> list[GiveawayStat]:
        rows = self._conn.execute(
            """
            select
                s.chat_id,
                s.user_id,
                u.username,
                coalesce(u.full_name, cast(s.user_id as text)) as full_name,
                s.wins_count
            from giveaway_stats s
            left join seen_users u on u.chat_id = s.chat_id and u.user_id = s.user_id
            where s.chat_id = ?
            order by s.wins_count desc, u.username collate nocase
            limit ?
            """,
            (chat_id, limit),
        ).fetchall()
        return [GiveawayStat(**dict(row)) for row in rows]

    def get_alarm_settings(self, chat_id: int) -> AlarmSettings:
        row = self._conn.execute(
            """
            select chat_id, enabled, permissions_json, reactions_json, alarm_text, clear_text, updated_by, updated_at
            from alarm_settings
            where chat_id = ?
            """,
            (chat_id,),
        ).fetchone()
        if row:
            return AlarmSettings(**dict(row))
        return AlarmSettings(
            chat_id=chat_id,
            enabled=0,
            permissions_json=None,
            reactions_json=None,
            alarm_text=None,
            clear_text=None,
            updated_by=None,
            updated_at=utc_now(),
        )

    def set_alarm_enabled(self, chat_id: int, enabled: bool, updated_by: int | None) -> None:
        current = self.get_alarm_settings(chat_id)
        self._conn.execute(
            """
            insert into alarm_settings (chat_id, enabled, permissions_json, reactions_json, alarm_text, clear_text, updated_by, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(chat_id) do update set
                enabled = excluded.enabled,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (
                chat_id,
                int(enabled),
                current.permissions_json,
                current.reactions_json,
                current.alarm_text,
                current.clear_text,
                updated_by,
                utc_now(),
            ),
        )
        self._conn.commit()

    def set_alarm_texts(
        self,
        chat_id: int,
        alarm_text: str | None = None,
        clear_text: str | None = None,
        updated_by: int | None = None,
    ) -> None:
        current = self.get_alarm_settings(chat_id)
        self._conn.execute(
            """
            insert into alarm_settings (chat_id, enabled, permissions_json, reactions_json, alarm_text, clear_text, updated_by, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(chat_id) do update set
                alarm_text = excluded.alarm_text,
                clear_text = excluded.clear_text,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (
                chat_id,
                current.enabled,
                current.permissions_json,
                current.reactions_json,
                alarm_text if alarm_text is not None else current.alarm_text,
                clear_text if clear_text is not None else current.clear_text,
                updated_by,
                utc_now(),
            ),
        )
        self._conn.commit()

    def save_alarm_permissions(self, chat_id: int, permissions: dict) -> None:
        current = self.get_alarm_settings(chat_id)
        self._conn.execute(
            """
            insert into alarm_settings (chat_id, enabled, permissions_json, reactions_json, alarm_text, clear_text, updated_by, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(chat_id) do update set
                permissions_json = excluded.permissions_json,
                updated_at = excluded.updated_at
            """,
            (
                chat_id,
                current.enabled,
                json.dumps(permissions, ensure_ascii=False),
                current.reactions_json,
                current.alarm_text,
                current.clear_text,
                current.updated_by,
                utc_now(),
            ),
        )
        self._conn.commit()

    def save_alarm_reactions(self, chat_id: int, reactions: list | None) -> None:
        current = self.get_alarm_settings(chat_id)
        self._conn.execute(
            """
            insert into alarm_settings (chat_id, enabled, permissions_json, reactions_json, alarm_text, clear_text, updated_by, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(chat_id) do update set
                reactions_json = excluded.reactions_json,
                updated_at = excluded.updated_at
            """,
            (
                chat_id,
                current.enabled,
                current.permissions_json,
                json.dumps(reactions, ensure_ascii=False) if reactions is not None else None,
                current.alarm_text,
                current.clear_text,
                current.updated_by,
                utc_now(),
            ),
        )
        self._conn.commit()

    def pop_alarm_reactions(self, chat_id: int) -> list | None:
        current = self.get_alarm_settings(chat_id)
        if current.reactions_json is None:
            return None
        self._conn.execute(
            "update alarm_settings set reactions_json = null, updated_at = ? where chat_id = ?",
            (utc_now(), chat_id),
        )
        self._conn.commit()
        return json.loads(current.reactions_json)

    def pop_alarm_permissions(self, chat_id: int) -> dict | None:
        current = self.get_alarm_settings(chat_id)
        if not current.permissions_json:
            return None
        self._conn.execute(
            "update alarm_settings set permissions_json = null, updated_at = ? where chat_id = ?",
            (utc_now(), chat_id),
        )
        self._conn.commit()
        return json.loads(current.permissions_json)

    def add_star_payment(
        self,
        user_id: int,
        username: str | None,
        full_name: str,
        chat_id: int | None,
        amount: int,
        currency: str,
        charge_id: str,
    ) -> None:
        self._conn.execute(
            """
            insert into star_payments (user_id, username, full_name, chat_id, amount, currency, charge_id, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, normalize_username(username) if username else None, full_name, chat_id, amount, currency, charge_id, utc_now()),
        )
        self._conn.commit()

    def list_star_payments(self, limit: int = 25) -> list[StarPayment]:
        rows = self._conn.execute(
            """
            select id, user_id, username, full_name, chat_id, amount, currency, charge_id, created_at
            from star_payments
            order by id desc
            limit ?
            """,
            (limit,),
        ).fetchall()
        return [StarPayment(**dict(row)) for row in rows]

    def add_quote(self, chat_id: int, text: str, author_name: str | None, added_by: int | None) -> None:
        self._conn.execute(
            """
            insert into quotes (chat_id, text, author_name, added_by, created_at)
            values (?, ?, ?, ?, ?)
            """,
            (chat_id, text, author_name, added_by, utc_now()),
        )
        self._conn.commit()

    def random_quote(self, chat_id: int) -> Quote | None:
        row = self._conn.execute(
            """
            select id, chat_id, text, author_name, added_by, created_at
            from quotes
            where chat_id = ?
            order by random()
            limit 1
            """,
            (chat_id,),
        ).fetchone()
        return Quote(**dict(row)) if row else None

    def add_birthday(self, chat_id: int, day: int, month: int, text: str, added_by: int | None) -> None:
        self._conn.execute(
            """
            insert into birthdays (chat_id, day, month, text, added_by, created_at)
            values (?, ?, ?, ?, ?, ?)
            """,
            (chat_id, day, month, text, added_by, utc_now()),
        )
        self._conn.commit()

    def list_birthdays(self, chat_id: int) -> list[Birthday]:
        rows = self._conn.execute(
            """
            select id, chat_id, day, month, text, added_by, created_at
            from birthdays
            where chat_id = ?
            order by month, day, text collate nocase
            """,
            (chat_id,),
        ).fetchall()
        return [Birthday(**dict(row)) for row in rows]

    def birthdays_for_date(self, chat_id: int, day: int, month: int, sent_date: str) -> list[Birthday]:
        rows = self._conn.execute(
            """
            select b.id, b.chat_id, b.day, b.month, b.text, b.added_by, b.created_at
            from birthdays b
            left join birthday_sent s
                on s.chat_id = b.chat_id and s.birthday_id = b.id and s.sent_date = ?
            where b.chat_id = ? and b.day = ? and b.month = ? and s.birthday_id is null
            order by b.text collate nocase
            """,
            (sent_date, chat_id, day, month),
        ).fetchall()
        return [Birthday(**dict(row)) for row in rows]

    def mark_birthday_sent(self, chat_id: int, birthday_id: int, sent_date: str) -> None:
        self._conn.execute(
            "insert or ignore into birthday_sent (chat_id, birthday_id, sent_date) values (?, ?, ?)",
            (chat_id, birthday_id, sent_date),
        )
        self._conn.commit()

    def add_blacklist_word(self, chat_id: int, word: str, added_by: int | None) -> None:
        self._conn.execute(
            """
            insert into blacklist_words (chat_id, word, added_by, created_at)
            values (?, ?, ?, ?)
            on conflict(chat_id, word) do update set
                added_by = excluded.added_by,
                created_at = excluded.created_at
            """,
            (chat_id, normalize_trigger(word), added_by, utc_now()),
        )
        self._conn.commit()

    def delete_blacklist_word(self, chat_id: int, word: str) -> bool:
        cur = self._conn.execute(
            "delete from blacklist_words where chat_id = ? and word = ?",
            (chat_id, normalize_trigger(word)),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def list_blacklist_words(self, chat_id: int) -> list[BlacklistWord]:
        rows = self._conn.execute(
            """
            select chat_id, word, added_by, created_at
            from blacklist_words
            where chat_id = ?
            order by word collate nocase
            """,
            (chat_id,),
        ).fetchall()
        return [BlacklistWord(**dict(row)) for row in rows]

    def get_roll_mute_settings(self, chat_id: int) -> RollMuteSettings:
        row = self._conn.execute(
            """
            select chat_id, mute_minutes, cooldown_minutes, updated_by, updated_at, last_used_at
            from roll_mute_settings
            where chat_id = ?
            """,
            (chat_id,),
        ).fetchone()
        if row:
            return RollMuteSettings(**dict(row))
        return RollMuteSettings(
            chat_id=chat_id,
            mute_minutes=60,
            cooldown_minutes=30,
            updated_by=None,
            updated_at=utc_now(),
            last_used_at=None,
        )

    def set_roll_mute_settings(
        self,
        chat_id: int,
        mute_minutes: int,
        cooldown_minutes: int,
        updated_by: int | None,
    ) -> None:
        current = self.get_roll_mute_settings(chat_id)
        self._conn.execute(
            """
            insert into roll_mute_settings (chat_id, mute_minutes, cooldown_minutes, updated_by, updated_at, last_used_at)
            values (?, ?, ?, ?, ?, ?)
            on conflict(chat_id) do update set
                mute_minutes = excluded.mute_minutes,
                cooldown_minutes = excluded.cooldown_minutes,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (
                chat_id,
                max(1, min(10080, int(mute_minutes))),
                max(0, min(10080, int(cooldown_minutes))),
                updated_by,
                utc_now(),
                current.last_used_at,
            ),
        )
        self._conn.commit()

    def set_roll_mute_last_used(self, chat_id: int, used_at: str) -> None:
        current = self.get_roll_mute_settings(chat_id)
        self._conn.execute(
            """
            insert into roll_mute_settings (chat_id, mute_minutes, cooldown_minutes, updated_by, updated_at, last_used_at)
            values (?, ?, ?, ?, ?, ?)
            on conflict(chat_id) do update set
                last_used_at = excluded.last_used_at
            """,
            (chat_id, current.mute_minutes, current.cooldown_minutes, current.updated_by, current.updated_at, used_at),
        )
        self._conn.commit()

    def increment_roll_mute_stat(self, chat_id: int, user_id: int) -> None:
        self._conn.execute(
            """
            insert into roll_mute_stats (chat_id, user_id, unlucky_count, updated_at)
            values (?, ?, 1, ?)
            on conflict(chat_id, user_id) do update set
                unlucky_count = unlucky_count + 1,
                updated_at = excluded.updated_at
            """,
            (chat_id, user_id, utc_now()),
        )
        self._conn.commit()

    def top_roll_mute_stats(self, chat_id: int, limit: int = 10) -> list[RollMuteStat]:
        rows = self._conn.execute(
            """
            select
                s.chat_id,
                s.user_id,
                u.username,
                coalesce(u.full_name, 'user ' || s.user_id) as full_name,
                s.unlucky_count
            from roll_mute_stats s
            left join seen_users u on u.chat_id = s.chat_id and u.user_id = s.user_id
            where s.chat_id = ?
            order by s.unlucky_count desc, u.username collate nocase
            limit ?
            """,
            (chat_id, limit),
        ).fetchall()
        return [RollMuteStat(**dict(row)) for row in rows]

    def get_quiet_settings(self, chat_id: int) -> QuietSettings:
        row = self._conn.execute(
            """
            select chat_id, reply_text, media_type, media_file_id, updated_by, updated_at
            from quiet_settings
            where chat_id = ?
            """,
            (chat_id,),
        ).fetchone()
        if row:
            return QuietSettings(**dict(row))
        return QuietSettings(
            chat_id=chat_id,
            reply_text=None,
            media_type=None,
            media_file_id=None,
            updated_by=None,
            updated_at=utc_now(),
        )

    def set_quiet_text(self, chat_id: int, reply_text: str, updated_by: int | None) -> None:
        current = self.get_quiet_settings(chat_id)
        self._conn.execute(
            """
            insert into quiet_settings (chat_id, reply_text, media_type, media_file_id, updated_by, updated_at)
            values (?, ?, ?, ?, ?, ?)
            on conflict(chat_id) do update set
                reply_text = excluded.reply_text,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (chat_id, reply_text.strip(), current.media_type, current.media_file_id, updated_by, utc_now()),
        )
        self._conn.commit()

    def set_quiet_media(self, chat_id: int, media_type: str, media_file_id: str, updated_by: int | None) -> None:
        current = self.get_quiet_settings(chat_id)
        self._conn.execute(
            """
            insert into quiet_settings (chat_id, reply_text, media_type, media_file_id, updated_by, updated_at)
            values (?, ?, ?, ?, ?, ?)
            on conflict(chat_id) do update set
                media_type = excluded.media_type,
                media_file_id = excluded.media_file_id,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (chat_id, current.reply_text, media_type, media_file_id, updated_by, utc_now()),
        )
        self._conn.commit()

    def clear_quiet_media(self, chat_id: int, updated_by: int | None) -> None:
        current = self.get_quiet_settings(chat_id)
        self._conn.execute(
            """
            insert into quiet_settings (chat_id, reply_text, media_type, media_file_id, updated_by, updated_at)
            values (?, ?, null, null, ?, ?)
            on conflict(chat_id) do update set
                media_type = null,
                media_file_id = null,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (chat_id, current.reply_text, updated_by, utc_now()),
        )
        self._conn.commit()


def normalize_username(username: str) -> str:
    return username.strip().lstrip("@").lower()


def normalize_trigger(trigger: str) -> str:
    return " ".join(trigger.strip().casefold().split())
