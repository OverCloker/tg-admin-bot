"""Relationship progression; XP never grants currency or mining advantages."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

LEVELS = (
    (0, "Симпатия"), (100, "Искра"), (300, "Сближение"),
    (650, "Доверие"), (1200, "Нежность"), (2000, "Крепкая связь"),
    (3200, "Родные души"), (5000, "Неразлучные"),
)
GIFT_XP = {"couple_flower": 10, "couple_crystal": 30, "couple_date": 25}


def _relationship_timezone():
    for name in ("Europe/Kyiv", "Europe/Kiev"):
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError:
            continue
    # Last-resort fallback for an incomplete local Python installation. The
    # declared tzdata dependency remains the source of DST-aware production time.
    return timezone(timedelta(hours=3))


RELATIONSHIP_TIMEZONE = _relationship_timezone()


def relationship_day() -> str:
    return datetime.now(RELATIONSHIP_TIMEZONE).date().isoformat()


def relationship_level(xp: int) -> dict:
    xp = max(0, int(xp))
    index = max(i for i, (threshold, _) in enumerate(LEVELS) if xp >= threshold)
    start, title = LEVELS[index]
    target = LEVELS[index + 1][0] if index + 1 < len(LEVELS) else None
    return {"level": index + 1, "title": title, "xp": xp, "nextXp": target,
            "remaining": max(0, target - xp) if target else 0,
            "percent": min(100, int(100 * (xp - start) / (target - start))) if target else 100}
