from types import SimpleNamespace

from app.bot import is_single_emoji_message, router


def test_edited_single_emoji_handler_is_registered() -> None:
    observer = router.observers["edited_message"]
    handler_names = {handler.callback.__name__ for handler in observer.handlers}

    assert "delete_edited_single_emoji_during_alarm" in handler_names


def test_single_emoji_detection_matches_edited_message_bypass() -> None:
    edited = SimpleNamespace(text="🚽", entities=None)
    original = SimpleNamespace(text="блять 🚽", entities=None)

    assert is_single_emoji_message(edited) is True
    assert is_single_emoji_message(original) is False
