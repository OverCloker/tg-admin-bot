import asyncio
from unittest.mock import Mock

import app.admin_api as api


def test_lifespan_stops_worker_even_on_exception(monkeypatch):
    stopped = asyncio.Event()

    async def worker():
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    monkeypatch.setattr(api, "youtube_queue_worker", worker)
    monkeypatch.setattr(api, "YOUTUBE_WORKER_TASK", None)

    async def run():
        try:
            async with api.app.router.lifespan_context(api.app):
                task = api.YOUTUBE_WORKER_TASK
                assert task is not None
                await asyncio.sleep(0)
                await api.start_youtube_worker()
                assert api.YOUTUBE_WORKER_TASK is task
                raise RuntimeError("shutdown after application failure")
        except RuntimeError:
            pass
        assert stopped.is_set()
        assert api.YOUTUBE_WORKER_TASK is None

    asyncio.run(run())


def test_permission_snapshot_calculated_once(monkeypatch):
    modes = {item["id"]: {"view": index % 2 == 0, "write": False}
             for index, item in enumerate(api.ADMIN_FEATURES)}
    calculate = Mock(return_value=modes)
    monkeypatch.setattr(api, "feature_permission_modes_for_actor", calculate)
    database = object()
    result = api.feature_permissions_for_actor(database, -100)
    assert result == {key: value["view"] for key, value in modes.items()}
    calculate.assert_called_once_with(database, -100)
