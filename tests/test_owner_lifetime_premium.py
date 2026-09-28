import pytest

from app import bot
from app.premium import PremiumRequiredError, PremiumService
from app.user_profile import _active_premium


def test_explicit_owner_has_lifetime_extended_premium(monkeypatch, tmp_path):
    monkeypatch.setenv("OWNER_ID", "42")
    premium = PremiumService(tmp_path / "premium.sqlite3")
    try:
        assert premium.get_user_subscription(42) is None
        assert premium.has_lifetime_premium(42)
        assert premium.get_user_plan(42).key == "extended"
        assert premium.check_media_limits(42, file_size_bytes=1024).key == "extended"
        assert premium.get_mine_bonuses(42)["plan"] == "extended"
        assert _active_premium(premium, 42)["lifetime"] is True

        monkeypatch.setattr(bot, "premium_service", premium)
        text = bot.premium_status_text(42)
        assert "Расширенный премиум" in text
        assert "бессрочно" in text
        assert "Premium не активен" not in text

        assert not premium.has_lifetime_premium(43)
        with pytest.raises(PremiumRequiredError):
            premium.check_media_limits(43, file_size_bytes=1024)
    finally:
        premium.close()


def test_owner_premium_requires_explicit_owner_id(monkeypatch, tmp_path):
    monkeypatch.delenv("OWNER_ID", raising=False)
    monkeypatch.setenv("BOT_ADMIN_IDS", "42")
    premium = PremiumService(tmp_path / "premium.sqlite3")
    try:
        assert not premium.has_lifetime_premium(42)
        assert premium.get_user_plan(42) is None
    finally:
        premium.close()
