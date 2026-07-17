import logging
import os
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from threading import RLock
from typing import Any


PREMIUM_PERIOD_DAYS = 30


@dataclass(frozen=True)
class PlanConfig:
    key: str
    title: str
    price_stars: int
    daily_media_tasks: int
    max_file_size_bytes: int
    max_transcription_seconds: int
    priority: int
    cooldown_multiplier: float
    coins_multiplier: float
    luck_regen_multiplier: float
    daily_radio_recognitions: int
    max_radio_recording_seconds: int
    radio_track_history: bool


PLANS: dict[str, PlanConfig] = {
    "basic": PlanConfig(
        key="basic",
        title="Базовый премиум",
        price_stars=50,
        daily_media_tasks=3,
        max_file_size_bytes=50 * 1024 * 1024,
        max_transcription_seconds=5 * 60,
        priority=10,
        cooldown_multiplier=0.85,
        coins_multiplier=1.15,
        luck_regen_multiplier=1.15,
        daily_radio_recognitions=10,
        max_radio_recording_seconds=10 * 60,
        radio_track_history=False,
    ),
    "extended": PlanConfig(
        key="extended",
        title="Расширенный премиум",
        price_stars=100,
        daily_media_tasks=30,
        max_file_size_bytes=200 * 1024 * 1024,
        max_transcription_seconds=30 * 60,
        priority=1,
        cooldown_multiplier=0.65,
        coins_multiplier=1.35,
        luck_regen_multiplier=1.35,
        daily_radio_recognitions=100,
        max_radio_recording_seconds=60 * 60,
        radio_track_history=True,
    ),
}


class PremiumError(ValueError):
    pass


class PremiumRequiredError(PremiumError):
    pass


class PremiumLimitError(PremiumError):
    pass


def synchronized(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapped


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat(timespec="seconds")


def plan_public_dict(plan: PlanConfig) -> dict[str, Any]:
    data = asdict(plan)
    data["max_file_size_mb"] = plan.max_file_size_bytes // (1024 * 1024)
    data["max_transcription_minutes"] = plan.max_transcription_seconds // 60
    data["queue"] = "ускоренная" if plan.priority == 1 else "обычная"
    return data


class PremiumService:
    def __init__(self, db_path: str) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self.init()

    @synchronized
    def close(self) -> None:
        self._conn.close()

    @synchronized
    def init(self) -> None:
        self._conn.executescript(
            """
            create table if not exists users (
                user_id integer primary key,
                username text,
                created_at text not null
            );
            create table if not exists subscriptions (
                id integer primary key autoincrement,
                user_id integer not null,
                plan text not null,
                status text not null,
                started_at text not null,
                expires_at text not null,
                telegram_payment_charge_id text,
                provider_payment_charge_id text
            );
            create index if not exists subscriptions_user_expires_idx
                on subscriptions(user_id, expires_at desc);
            create table if not exists media_tasks (
                id integer primary key autoincrement,
                user_id integer not null,
                task_type text not null,
                source_file_id text,
                source_file_path text,
                output_file_path text,
                status text not null,
                priority integer not null,
                file_size_bytes integer not null,
                duration_seconds integer,
                error_text text,
                created_at text not null,
                started_at text,
                finished_at text
            );
            create index if not exists media_tasks_queue_idx
                on media_tasks(status, priority, created_at);
            create table if not exists usage_daily (
                user_id integer not null,
                date text not null,
                media_tasks_count integer not null default 0,
                primary key(user_id, date)
            );
            create table if not exists radio_usage_daily (
                user_id integer not null,
                date text not null,
                recognitions_count integer not null default 0,
                primary key(user_id, date)
            );
            create table if not exists radio_track_history (
                id integer primary key autoincrement,
                user_id integer not null,
                station_name text,
                artist text not null,
                title text not null,
                album text,
                artwork_url text,
                recognized_at text not null
            );
            create index if not exists radio_track_history_user_idx
                on radio_track_history(user_id, id desc);
            """
        )
        self._conn.execute(
            "delete from subscriptions where telegram_payment_charge_id is not null "
            "and telegram_payment_charge_id <> '' and id not in "
            "(select min(id) from subscriptions where telegram_payment_charge_id is not null "
            "and telegram_payment_charge_id <> '' group by telegram_payment_charge_id)"
        )
        self._conn.execute(
            "create unique index if not exists subscriptions_charge_uidx on subscriptions(telegram_payment_charge_id) "
            "where telegram_payment_charge_id is not null and telegram_payment_charge_id <> ''"
        )
        self._conn.commit()

    @synchronized
    def get_plan_config(self, plan: str) -> PlanConfig:
        config = PLANS.get(plan)
        if not config:
            raise PremiumError(f"Неизвестный Premium-тариф: {plan}")
        return config

    @synchronized
    def ensure_user(self, user_id: int, username: str | None = None) -> None:
        self._conn.execute(
            """
            insert into users(user_id, username, created_at) values (?, ?, ?)
            on conflict(user_id) do update set username = coalesce(excluded.username, users.username)
            """,
            (user_id, username, utc_iso()),
        )
        self._conn.commit()

    @synchronized
    def get_user_subscription(self, user_id: int) -> sqlite3.Row | None:
        return self._conn.execute(
            """
            select id, user_id, plan, status, started_at, expires_at,
                   telegram_payment_charge_id, provider_payment_charge_id
            from subscriptions
            where user_id = ?
            order by expires_at desc, id desc
            limit 1
            """,
            (user_id,),
        ).fetchone()

    @synchronized
    def list_subscriptions(self, limit: int = 500) -> list[sqlite3.Row]:
        return self._conn.execute(
            """
            select s.id, s.user_id, u.username, s.plan, s.status, s.started_at, s.expires_at,
                   s.telegram_payment_charge_id, s.provider_payment_charge_id
            from subscriptions s
            left join users u on u.user_id = s.user_id
            order by s.id desc
            limit ?
            """,
            (max(1, min(2000, int(limit))),),
        ).fetchall()

    @synchronized
    def has_active_premium(self, user_id: int) -> bool:
        return self.get_user_plan(user_id) is not None

    @synchronized
    def get_user_plan(self, user_id: int) -> PlanConfig | None:
        subscription = self.get_user_subscription(user_id)
        if not subscription or subscription["status"] != "active":
            return None
        try:
            expires_at = datetime.fromisoformat(subscription["expires_at"])
        except (TypeError, ValueError):
            return None
        if expires_at <= utc_now():
            self._conn.execute("update subscriptions set status = 'expired' where id = ?", (subscription["id"],))
            self._conn.commit()
            return None
        return PLANS.get(subscription["plan"])

    @synchronized
    def activate_subscription(
        self,
        user_id: int,
        plan: str,
        telegram_payment_charge_id: str | None,
        provider_payment_charge_id: str | None = None,
        username: str | None = None,
        expires_at: datetime | None = None,
    ) -> sqlite3.Row:
        config = self.get_plan_config(plan)
        self.ensure_user(user_id, username)
        now = utc_now()
        current = self.get_user_subscription(user_id)
        base = now
        if current and current["status"] == "active":
            try:
                current_expiry = datetime.fromisoformat(current["expires_at"])
                if current_expiry > now and current["plan"] == plan:
                    base = current_expiry
            except (TypeError, ValueError):
                pass
        expiry = expires_at or (base + timedelta(days=PREMIUM_PERIOD_DAYS))
        self._conn.execute(
            """
            insert or ignore into subscriptions (
                user_id, plan, status, started_at, expires_at,
                telegram_payment_charge_id, provider_payment_charge_id
            ) values (?, ?, 'active', ?, ?, ?, ?)
            """,
            (
                user_id,
                config.key,
                utc_iso(now),
                utc_iso(expiry),
                telegram_payment_charge_id,
                provider_payment_charge_id,
            ),
        )
        self._conn.commit()
        self.log("INFO", f"Premium purchased: user={user_id}, plan={plan}, expires={utc_iso(expiry)}")
        return self.get_user_subscription(user_id)

    @synchronized
    def check_media_limits(
        self,
        user_id: int,
        file_size_bytes: int,
        duration_seconds: int | None = None,
        task_type: str | None = None,
    ) -> PlanConfig:
        plan = self.get_user_plan(user_id)
        if plan is None:
            self.log("WARNING", f"Media task denied: user={user_id}, reason=premium_required")
            raise PremiumRequiredError("Для этой функции нужен Premium.")
        count = self.daily_media_usage(user_id)
        if count >= plan.daily_media_tasks:
            self.log("WARNING", f"Media task denied: user={user_id}, reason=daily_limit, plan={plan.key}")
            raise PremiumLimitError("Дневной лимит медиа-задач исчерпан.")
        if file_size_bytes < 0 or file_size_bytes > plan.max_file_size_bytes:
            self.log("WARNING", f"Media task denied: user={user_id}, reason=file_size, plan={plan.key}")
            raise PremiumLimitError(f"Файл превышает лимит тарифа: {plan.max_file_size_bytes // (1024 * 1024)} МБ.")
        if task_type in {"transcription", "transcription_timestamps"} and duration_seconds is not None and duration_seconds > plan.max_transcription_seconds:
            self.log("WARNING", f"Media task denied: user={user_id}, reason=duration, plan={plan.key}")
            raise PremiumLimitError(f"Расшифровка превышает лимит тарифа: {plan.max_transcription_seconds // 60} мин.")
        return plan

    @synchronized
    def increment_daily_media_usage(self, user_id: int) -> int:
        today = utc_now().date().isoformat()
        self._conn.execute(
            """
            insert into usage_daily(user_id, date, media_tasks_count) values (?, ?, 1)
            on conflict(user_id, date) do update set media_tasks_count = usage_daily.media_tasks_count + 1
            """,
            (user_id, today),
        )
        self._conn.commit()
        return self.daily_media_usage(user_id)

    @synchronized
    def daily_media_usage(self, user_id: int) -> int:
        row = self._conn.execute(
            "select media_tasks_count from usage_daily where user_id = ? and date = ?",
            (user_id, utc_now().date().isoformat()),
        ).fetchone()
        return int(row["media_tasks_count"]) if row else 0

    @synchronized
    def check_radio_recognition_limit(self, user_id: int) -> PlanConfig:
        plan = self.get_user_plan(user_id)
        if plan is None:
            raise PremiumRequiredError("Для распознавания треков нужен Premium.")
        if self.daily_radio_recognition_usage(user_id) >= plan.daily_radio_recognitions:
            raise PremiumLimitError("Дневной лимит распознаваний исчерпан.")
        return plan

    @synchronized
    def claim_radio_recognition_slot(self, user_id: int) -> PlanConfig:
        plan = self.get_user_plan(user_id)
        if plan is None:
            raise PremiumRequiredError("Для распознавания треков нужен Premium.")
        today = utc_now().date().isoformat()
        self._conn.execute("begin immediate")
        try:
            row = self._conn.execute(
                "select recognitions_count from radio_usage_daily where user_id = ? and date = ?",
                (user_id, today),
            ).fetchone()
            current = int(row["recognitions_count"]) if row else 0
            if current >= plan.daily_radio_recognitions:
                self._conn.rollback()
                raise PremiumLimitError("Дневной лимит распознаваний исчерпан.")
            self._conn.execute(
                """
                insert into radio_usage_daily(user_id, date, recognitions_count) values (?, ?, 1)
                on conflict(user_id, date) do update set recognitions_count = radio_usage_daily.recognitions_count + 1
                """,
                (user_id, today),
            )
            self._conn.commit()
            return plan
        except (PremiumLimitError, PremiumRequiredError):
            raise
        except Exception:
            self._conn.rollback()
            raise

    @synchronized
    def release_radio_recognition_slot(self, user_id: int) -> None:
        today = utc_now().date().isoformat()
        self._conn.execute(
            """
            update radio_usage_daily
            set recognitions_count = max(0, recognitions_count - 1)
            where user_id = ? and date = ?
            """,
            (user_id, today),
        )
        self._conn.commit()

    @synchronized
    def increment_radio_recognition_usage(self, user_id: int) -> int:
        today = utc_now().date().isoformat()
        self._conn.execute(
            """
            insert into radio_usage_daily(user_id, date, recognitions_count) values (?, ?, 1)
            on conflict(user_id, date) do update set recognitions_count = radio_usage_daily.recognitions_count + 1
            """,
            (user_id, today),
        )
        self._conn.commit()
        return self.daily_radio_recognition_usage(user_id)

    @synchronized
    def daily_radio_recognition_usage(self, user_id: int) -> int:
        row = self._conn.execute(
            "select recognitions_count from radio_usage_daily where user_id = ? and date = ?",
            (user_id, utc_now().date().isoformat()),
        ).fetchone()
        return int(row["recognitions_count"]) if row else 0

    @synchronized
    def add_radio_track(
        self,
        user_id: int,
        station_name: str,
        artist: str,
        title: str,
        album: str | None,
        artwork_url: str | None,
    ) -> None:
        self._conn.execute(
            """
            insert into radio_track_history(user_id, station_name, artist, title, album, artwork_url, recognized_at)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, station_name, artist, title, album, artwork_url, utc_iso()),
        )
        self._conn.commit()

    @synchronized
    def radio_track_history(self, user_id: int, limit: int = 100) -> list[sqlite3.Row]:
        return self._conn.execute(
            """
            select id, station_name, artist, title, album, artwork_url, recognized_at
            from radio_track_history where user_id = ? order by id desc limit ?
            """,
            (user_id, max(1, min(500, int(limit)))),
        ).fetchall()

    @synchronized
    def get_mine_bonuses(self, user_id: int) -> dict[str, float | str | None]:
        plan = self.get_user_plan(user_id)
        if plan is None:
            return {
                "plan": None,
                "cooldown_multiplier": 1.0,
                "coins_multiplier": 1.0,
                "luck_regen_multiplier": 1.0,
            }
        return {
            "plan": plan.key,
            "cooldown_multiplier": plan.cooldown_multiplier,
            "coins_multiplier": plan.coins_multiplier,
            "luck_regen_multiplier": plan.luck_regen_multiplier,
        }

    @synchronized
    def log(self, level: str, text: str) -> None:
        try:
            self._conn.execute(
                "insert into logs(level, text, created_at) values (?, ?, ?)",
                (level.upper(), text, utc_iso()),
            )
            self._conn.commit()
        except sqlite3.OperationalError:
            logging.log(getattr(logging, level.upper(), logging.INFO), text)


def default_db_path() -> str:
    return os.getenv("DB_PATH", "bot.sqlite3").strip() or "bot.sqlite3"


def get_plan_config(plan: str) -> PlanConfig:
    config = PLANS.get(plan)
    if not config:
        raise PremiumError(f"Неизвестный Premium-тариф: {plan}")
    return config


def get_user_subscription(user_id: int, db_path: str | None = None) -> sqlite3.Row | None:
    service = PremiumService(db_path or default_db_path())
    try:
        return service.get_user_subscription(user_id)
    finally:
        service.close()


def has_active_premium(user_id: int, db_path: str | None = None) -> bool:
    service = PremiumService(db_path or default_db_path())
    try:
        return service.has_active_premium(user_id)
    finally:
        service.close()


def get_user_plan(user_id: int, db_path: str | None = None) -> PlanConfig | None:
    service = PremiumService(db_path or default_db_path())
    try:
        return service.get_user_plan(user_id)
    finally:
        service.close()


def check_media_limits(
    user_id: int,
    file_size_bytes: int,
    duration_seconds: int | None = None,
    task_type: str | None = None,
    db_path: str | None = None,
) -> PlanConfig:
    service = PremiumService(db_path or default_db_path())
    try:
        return service.check_media_limits(user_id, file_size_bytes, duration_seconds, task_type)
    finally:
        service.close()


def increment_daily_media_usage(user_id: int, db_path: str | None = None) -> int:
    service = PremiumService(db_path or default_db_path())
    try:
        return service.increment_daily_media_usage(user_id)
    finally:
        service.close()


def get_mine_bonuses(user_id: int, db_path: str | None = None) -> dict[str, float | str | None]:
    service = PremiumService(db_path or default_db_path())
    try:
        return service.get_mine_bonuses(user_id)
    finally:
        service.close()
