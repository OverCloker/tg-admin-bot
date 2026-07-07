import sqlite3
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .premium import PremiumLimitError, PremiumService


SUPPORTED_TASK_TYPES = {
    "video_convert",
    "audio_convert",
    "extract_audio",
    "compress_video",
    "compress_audio",
    "trim_audio",
    "trim_video",
    "transcription",
    "transcription_timestamps",
    "gif_create",
    "youtube_video",
    "youtube_audio",
    "youtube_music_audio",
    "instagram_reel",
}
TASK_STATUSES = {"queued", "processing", "completed", "failed", "cancelled"}


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class MediaTask:
    id: int
    user_id: int
    task_type: str
    source_file_id: str | None
    source_file_path: str | None
    output_file_path: str | None
    status: str
    priority: int
    file_size_bytes: int
    duration_seconds: int | None
    error_text: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None


class MediaTaskService:
    def __init__(self, db_path: str) -> None:
        self.path = Path(db_path)
        self.premium = PremiumService(db_path)
        self._conn = sqlite3.connect(self.path, timeout=30)
        self._conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self._conn.close()
        self.premium.close()

    def create_media_task(
        self,
        user_id: int,
        task_type: str,
        source_file_id: str | None,
        file_size_bytes: int,
        duration_seconds: int | None = None,
        source_file_path: str | None = None,
    ) -> MediaTask:
        if task_type not in SUPPORTED_TASK_TYPES:
            raise ValueError(f"Неподдерживаемый task_type: {task_type}")
        try:
            plan = self.premium.check_media_limits(user_id, file_size_bytes, duration_seconds, task_type)
            now = utc_iso()
            self._conn.execute("begin immediate")
            today = datetime.now(timezone.utc).date().isoformat()
            usage = self._conn.execute(
                "select media_tasks_count from usage_daily where user_id = ? and date = ?",
                (user_id, today),
            ).fetchone()
            if usage and int(usage["media_tasks_count"]) >= plan.daily_media_tasks:
                raise PremiumLimitError("Дневной лимит медиа-задач исчерпан.")
            cur = self._conn.execute(
                """
                insert into media_tasks (
                    user_id, task_type, source_file_id, source_file_path, status,
                    priority, file_size_bytes, duration_seconds, created_at
                ) values (?, ?, ?, ?, 'queued', ?, ?, ?, ?)
                """,
                (user_id, task_type, source_file_id, source_file_path, plan.priority, file_size_bytes, duration_seconds, now),
            )
            self._conn.execute(
                """
                insert into usage_daily(user_id, date, media_tasks_count) values (?, ?, 1)
                on conflict(user_id, date) do update set media_tasks_count = usage_daily.media_tasks_count + 1
                """,
                (user_id, today),
            )
            self._conn.commit()
            task = self.get_media_task(int(cur.lastrowid))
            self.premium.log("INFO", f"Media task created: id={task.id}, user={user_id}, type={task_type}, priority={plan.priority}")
            return task
        except Exception as exc:
            if self._conn.in_transaction:
                self._conn.rollback()
            self.premium.log("ERROR", f"Media task creation failed: user={user_id}, type={task_type}, error={exc}")
            raise

    def get_user_media_tasks(self, user_id: int, limit: int = 20) -> list[MediaTask]:
        rows = self._conn.execute(
            "select * from media_tasks where user_id = ? order by id desc limit ?",
            (user_id, max(1, min(100, int(limit)))),
        ).fetchall()
        return [MediaTask(**dict(row)) for row in rows]

    def get_media_task(self, task_id: int) -> MediaTask | None:
        row = self._conn.execute("select * from media_tasks where id = ?", (task_id,)).fetchone()
        return MediaTask(**dict(row)) if row else None

    def update_media_task_status(self, task_id: int, status: str, error_text: str | None = None) -> bool:
        if status not in TASK_STATUSES:
            raise ValueError(f"Неподдерживаемый статус: {status}")
        started_at = utc_iso() if status == "processing" else None
        finished_at = utc_iso() if status in {"completed", "failed", "cancelled"} else None
        cur = self._conn.execute(
            """
            update media_tasks
            set status = ?, error_text = ?,
                started_at = coalesce(started_at, ?),
                finished_at = coalesce(?, finished_at)
            where id = ?
            """,
            (status, error_text, started_at, finished_at, task_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def set_output_file_path(self, task_id: int, output_file_path: str) -> bool:
        cur = self._conn.execute(
            "update media_tasks set output_file_path = ? where id = ?",
            (output_file_path, task_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def get_next_media_task(self) -> MediaTask | None:
        row = self._conn.execute(
            """
            select * from media_tasks
            where status = 'queued'
            order by priority asc, created_at asc, id asc
            limit 1
            """
        ).fetchone()
        return MediaTask(**dict(row)) if row else None

    def claim_next_youtube_task(self) -> MediaTask | None:
        try:
            self._conn.execute("begin immediate")
            row = self._conn.execute(
                """
                select * from media_tasks
                where status = 'queued'
                  and task_type in ('youtube_video', 'youtube_audio', 'youtube_music_audio', 'instagram_reel')
                order by priority asc, created_at asc, id asc
                limit 1
                """
            ).fetchone()
            if row is None:
                self._conn.commit()
                return None
            started_at = utc_iso()
            cur = self._conn.execute(
                """
                update media_tasks
                set status = 'processing', started_at = coalesce(started_at, ?)
                where id = ? and status = 'queued'
                """,
                (started_at, int(row["id"])),
            )
            self._conn.commit()
            return self.get_media_task(int(row["id"])) if cur.rowcount else None
        except Exception:
            if self._conn.in_transaction:
                self._conn.rollback()
            raise


def default_db_path() -> str:
    return os.getenv("DB_PATH", "bot.sqlite3").strip() or "bot.sqlite3"


def create_media_task(
    user_id: int,
    task_type: str,
    source_file_id: str | None,
    file_size_bytes: int,
    duration_seconds: int | None = None,
    source_file_path: str | None = None,
    db_path: str | None = None,
) -> MediaTask:
    service = MediaTaskService(db_path or default_db_path())
    try:
        return service.create_media_task(
            user_id, task_type, source_file_id, file_size_bytes, duration_seconds, source_file_path
        )
    finally:
        service.close()


def get_user_media_tasks(user_id: int, limit: int = 20, db_path: str | None = None) -> list[MediaTask]:
    service = MediaTaskService(db_path or default_db_path())
    try:
        return service.get_user_media_tasks(user_id, limit)
    finally:
        service.close()


def get_media_task(task_id: int, db_path: str | None = None) -> MediaTask | None:
    service = MediaTaskService(db_path or default_db_path())
    try:
        return service.get_media_task(task_id)
    finally:
        service.close()


def update_media_task_status(
    task_id: int, status: str, error_text: str | None = None, db_path: str | None = None
) -> bool:
    service = MediaTaskService(db_path or default_db_path())
    try:
        return service.update_media_task_status(task_id, status, error_text)
    finally:
        service.close()


def get_next_media_task(db_path: str | None = None) -> MediaTask | None:
    service = MediaTaskService(db_path or default_db_path())
    try:
        return service.get_next_media_task()
    finally:
        service.close()
