from concurrent.futures import ThreadPoolExecutor
from threading import get_ident

from app.premium import PremiumService
from app.db import Database
from app.media_tasks import MediaTaskService
from app.staff_db import StaffDatabase


def test_shared_premium_service_works_from_fastapi_worker_thread(tmp_path) -> None:
    service = PremiumService(str(tmp_path / "premium.sqlite3"))
    creator_thread = get_ident()

    def read_bonuses() -> tuple[int, dict[str, float | str | None]]:
        return get_ident(), service.get_mine_bonuses(42)

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            worker_thread, bonuses = executor.submit(read_bonuses).result()
    finally:
        service.close()

    assert worker_thread != creator_thread
    assert bonuses == {
        "plan": None,
        "cooldown_multiplier": 1.0,
        "coins_multiplier": 1.0,
        "luck_regen_multiplier": 1.0,
    }


def test_shared_premium_service_serializes_concurrent_writes(tmp_path) -> None:
    service = PremiumService(str(tmp_path / "premium.sqlite3"))

    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(lambda user_id: service.ensure_user(user_id), range(1, 41)))
        rows = service._conn.execute("select count(*) from users").fetchone()
    finally:
        service.close()

    assert rows[0] == 40


def test_shared_database_handles_fastapi_worker_thread(tmp_path) -> None:
    service = Database(str(tmp_path / "bot.sqlite3"))
    service.init()
    creator_thread = get_ident()

    def register_from_worker() -> tuple[int, bool]:
        created = service.register_dig_player(0, 42, "miner", "Miner")
        return get_ident(), created

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            worker_thread, created = executor.submit(register_from_worker).result()
    finally:
        service.close()

    assert worker_thread != creator_thread
    assert created is True


def test_shared_media_task_service_handles_worker_thread(tmp_path) -> None:
    service = MediaTaskService(str(tmp_path / "media.sqlite3"))
    creator_thread = get_ident()

    def count_from_worker() -> tuple[int, int]:
        row = service._conn.execute("select count(*) from media_tasks").fetchone()
        return get_ident(), int(row[0])

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            worker_thread, count = executor.submit(count_from_worker).result()
    finally:
        service.close()

    assert worker_thread != creator_thread
    assert count == 0


def test_shared_staff_database_handles_worker_thread(tmp_path) -> None:
    service = StaffDatabase(str(tmp_path / "staff.sqlite3"))
    service.init()
    creator_thread = get_ident()

    def log_from_worker() -> tuple[int, int]:
        return get_ident(), service.add_log("INFO", "worker log")

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            worker_thread, log_id = executor.submit(log_from_worker).result()
    finally:
        service.close()

    assert worker_thread != creator_thread
    assert log_id == 1
