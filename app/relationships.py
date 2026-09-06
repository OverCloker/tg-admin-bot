"""Relationship progression; XP never grants currency or mining advantages."""
from datetime import datetime
from zoneinfo import ZoneInfo

LEVELS = (
    (0, "Симпатия"), (100, "Искра"), (300, "Сближение"),
    (650, "Доверие"), (1200, "Нежность"), (2000, "Крепкая связь"),
    (3200, "Родные души"), (5000, "Неразлучные"),
)
GIFT_XP = {"couple_flower": 10, "couple_crystal": 30, "couple_date": 25}


def relationship_day() -> str:
    return datetime.now(ZoneInfo("Europe/Kiev")).date().isoformat()


def relationship_level(xp: int) -> dict:
    xp = max(0, int(xp))
    index = max(i for i, (threshold, _) in enumerate(LEVELS) if xp >= threshold)
    start, title = LEVELS[index]
    target = LEVELS[index + 1][0] if index + 1 < len(LEVELS) else None
    return {"level": index + 1, "title": title, "xp": xp, "nextXp": target,
            "remaining": max(0, target - xp) if target else 0,
            "percent": min(100, int(100 * (xp - start) / (target - start))) if target else 100}
