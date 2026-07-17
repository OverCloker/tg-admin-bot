from concurrent.futures import ThreadPoolExecutor
from threading import get_ident

from app.premium import PremiumService


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
