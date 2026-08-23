import asyncio
import builtins
from types import SimpleNamespace

from app import bot as bot_module
from app import media_processor


def test_whisper_availability_does_not_import_runtime(monkeypatch):
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "faster_whisper" or name.startswith("faster_whisper."):
            raise AssertionError("availability check imported faster_whisper")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(media_processor.importlib.util, "find_spec", lambda name: object())

    assert media_processor.whisper_available() is True


def test_media_menu_opens_without_loading_whisper(monkeypatch):
    edits = []

    class FakeState:
        async def clear(self):
            return None

    async def fake_safe_edit(_callback, text, **kwargs):
        edits.append((text, kwargs))

    monkeypatch.setattr(
        bot_module,
        "premium_service",
        SimpleNamespace(has_active_premium=lambda _user_id: True),
    )
    monkeypatch.setattr(bot_module, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(bot_module, "whisper_available", lambda: True)
    monkeypatch.setattr(bot_module, "safe_edit", fake_safe_edit)

    callback = SimpleNamespace(from_user=SimpleNamespace(id=42))
    asyncio.run(bot_module.cb_media_menu(callback, FakeState()))

    assert len(edits) == 1
    assert "Медиа-инструменты" in edits[0][0]
    assert edits[0][1]["reply_markup"] is not None
