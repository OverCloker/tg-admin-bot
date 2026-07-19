from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Any

from .db import DIG_GLOBAL_CHAT_ID, Database
from .premium import PremiumService, plan_public_dict


ACHIEVEMENT_NAMES = {
    "first_dig": "Первый спуск",
    "first_meter": "Первый метр",
    "five_meter_run": "Глубокий вдох",
    "ten_meter_run": "До ядра почти дошел",
    "total_25": "Шахтерская смена",
    "total_100": "Подземный барон",
    "coins_500": "Звенит сумка",
    "stone_zero": "Каменная встреча",
    "collapse_survive": "Не завалило",
    "first_purchase": "Покупатель",
    "level_5": "Опытный проходчик",
    "level_10": "Доступ в глубины",
    "streak_3": "На волне",
    "streak_5": "Стабильная смена",
    "streak_10": "Не остановить",
    "collector_3": "Археолог",
    "collector_all": "Коллекционер глубин",
    "low_luck": "На волоске",
    "route_master": "Картограф",
    "expedition": "Бригада",
    "coins_10000": "Крупный вклад",
}

ITEM_NAMES = {
    "helmet": "Каска",
    "shovel": "Лопата",
    "bucket": "Ведро",
    "insurance": "Страховка",
    "dynamite": "Динамит",
    "safe": "Сейф",
    "compass": "Компас",
    "scanner": "Сканер породы",
    "drill": "Бур",
    "medkit": "Аптечка",
    "map": "Карта тоннелей",
    "talisman": "Талисман",
    "camp": "Переносной лагерь",
    "repair_kit": "Ремонтный набор",
    "mystery_chest": "Таинственный сундук",
    "shovel_1": "Лопата I",
    "shovel_2": "Лопата II",
    "shovel_3": "Лопата III",
    "helmet_1": "Каска I",
    "helmet_2": "Каска II",
    "helmet_3": "Каска III",
    "flashlight_1": "Фонарь I",
    "flashlight_2": "Фонарь II",
    "flashlight_3": "Фонарь III",
    "cart_1": "Вагонетка I",
    "cart_2": "Вагонетка II",
    "cart_3": "Вагонетка III",
    "backpack_1": "Рюкзак I",
    "backpack_2": "Рюкзак II",
    "backpack_3": "Рюкзак III",
    "star_dig": "Оплаченная копка",
    "star_lucky_dig": "Копка со 100 удачей",
    "star_depth_10": "Прокопать 10 м",
}

RANKS = [
    ("rank_4", "Хозяин глубин"),
    ("rank_3", "Шахтерный барон"),
    ("rank_2", "Бригадир"),
    ("rank_1", "Проходчик"),
]

ROUTE_NAMES = {
    "old_mine": "Старая шахта",
    "deep_zone": "Глубинная зона",
    "crystal_cave": "Кристальная пещера",
    "forgotten_tunnel": "Забытый тоннель",
}


def _rank_name(items: dict[str, int]) -> str:
    for key, name in RANKS:
        if items.get(key, 0) > 0:
            return name
    return "Новичок"


def _rank_luck_regen_bonus(items: dict[str, int]) -> int:
    if items.get("rank_4", 0) > 0:
        return 3
    if items.get("rank_3", 0) > 0:
        return 2
    if items.get("rank_2", 0) > 0:
        return 1
    return 0


def _format_dt(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return value


def _active_premium(premium: PremiumService, user_id: int) -> dict[str, Any]:
    plan = premium.get_user_plan(user_id)
    subscription = premium.get_user_subscription(user_id)
    return {
        "active": plan is not None,
        "plan": plan_public_dict(plan) if plan else None,
        "subscription": dict(subscription) if subscription else None,
    }


def build_user_profile(
    db: Database,
    premium: PremiumService,
    user_id: int,
    username: str | None,
    full_name: str,
    chat_id: int | None = None,
    photo_url: str = "",
) -> dict[str, Any]:
    player = db.get_dig_player(DIG_GLOBAL_CHAT_ID, user_id)
    items = {item.item_key: item.quantity for item in db.list_dig_items(DIG_GLOBAL_CHAT_ID, user_id)}
    achievements = db.list_dig_achievements(DIG_GLOBAL_CHAT_ID, user_id)
    progress = db.get_dig_progress(user_id) if player else None
    premium_data = _active_premium(premium, user_id)
    now = datetime.now(timezone.utc)
    luck = 0
    if player:
        luck = int(player.luck)
        try:
            hours = max(0.0, (now - datetime.fromisoformat(player.last_luck_at)).total_seconds() / 3600)
            regen_multiplier = float(premium.get_mine_bonuses(user_id)["luck_regen_multiplier"])
            luck = min(100, luck + int(hours * (7 + _rank_luck_regen_bonus(items)) * regen_multiplier))
        except ValueError:
            pass

    chat_stats = None
    if chat_id is not None:
        chat_stats = {
            "messages": db.message_count_for_user(chat_id, user_id),
            "giveawayWins": db.giveaway_wins_for_user(chat_id, user_id),
            "rollMuteCount": db.roll_mute_count_for_user(chat_id, user_id),
        }

    active_items = [
        {
            "key": key,
            "name": ITEM_NAMES.get(key, key),
            "quantity": quantity,
        }
        for key, quantity in sorted(items.items())
        if quantity > 0 and not key.startswith("rank_")
    ]
    owned_achievements = [
        {
            "key": item.achievement_key,
            "name": ACHIEVEMENT_NAMES.get(item.achievement_key, item.achievement_key),
            "createdAt": item.created_at,
        }
        for item in achievements
    ]

    return {
        "user": {
            "id": user_id,
            "username": username or "",
            "fullName": full_name,
            "photoUrl": photo_url,
        },
        "premium": premium_data,
        "mine": {
            "registered": player is not None,
            "coins": player.coins if player else 0,
            "totalDepth": player.total_depth if player else 0,
            "bestSessionDepth": player.best_session_depth if player else 0,
            "luck": luck,
            "rank": _rank_name(items),
            "level": int(progress["level"]) if progress else 0,
            "xp": int(progress["xp"]) if progress else 0,
            "streak": int(progress["streak"]) if progress else 0,
            "route": ROUTE_NAMES.get(str(progress["selected_route"]), str(progress["selected_route"])) if progress else "",
            "lastDigAt": player.last_dig_at if player else None,
            "lastDigText": _format_dt(player.last_dig_at if player else None),
            "activeItems": active_items[:24],
            "activeItemsTotal": len(active_items),
            "achievements": owned_achievements[-8:],
            "achievementsTotal": len(owned_achievements),
            "achievementsKnown": len(ACHIEVEMENT_NAMES),
        },
        "chatStats": chat_stats,
    }


def profile_chat_text(profile: dict[str, Any], short: bool = True) -> str:
    user = profile["user"]
    premium = profile["premium"]
    mine = profile["mine"]
    chat_stats = profile.get("chatStats")
    name = escape(user["fullName"])
    username = f"@{escape(user['username'])}" if user.get("username") else "username не указан"
    premium_text = "активен"
    if premium.get("active") and premium.get("plan"):
        premium_text = premium["plan"].get("title", "Premium")
        subscription = premium.get("subscription") or {}
        expires = _format_dt(subscription.get("expires_at"))
        if expires:
            premium_text += f" до {escape(expires)}"
    elif not premium.get("active"):
        premium_text = "не активен"

    lines = [
        f"<b>Профиль {name}</b>",
        f"{username}",
        f"Premium: <b>{escape(premium_text)}</b>",
    ]
    if mine["registered"]:
        lines.extend(
            [
                "",
                "<b>Шахта</b>",
                f"Ранг: <b>{escape(mine['rank'])}</b> · Ур. <b>{mine['level']}</b> · Серия <b>{mine['streak']}</b>",
                f"Котоины: <b>{mine['coins']}</b> · Удача: <b>{mine['luck']}</b>/100",
                f"Глубина: <b>{mine['totalDepth']}</b> м · Рекорд: <b>{mine['bestSessionDepth']}</b> м",
            ]
        )
        if not short:
            lines.append(f"Маршрут: <b>{escape(mine['route'])}</b>")
            if mine.get("lastDigText"):
                lines.append(f"Последняя копка: <b>{escape(mine['lastDigText'])}</b>")
        achievements = mine.get("achievements") or []
        if achievements:
            names = ", ".join(escape(item["name"]) for item in achievements[-3:])
            lines.append(f"Достижения: <b>{mine['achievementsTotal']}/{mine['achievementsKnown']}</b> · {names}")
        else:
            lines.append(f"Достижения: <b>0/{mine['achievementsKnown']}</b>")
        if not short and mine.get("activeItems"):
            item_names = ", ".join(
                f"{escape(item['name'])} x{item['quantity']}" if item["quantity"] > 1 else escape(item["name"])
                for item in mine["activeItems"][:10]
            )
            lines.append(f"Инвентарь: {item_names}")
    else:
        lines.extend(["", "Шахта: еще не зарегистрирован. Напиши <code>копай</code> в группе."])

    if chat_stats:
        lines.extend(
            [
                "",
                "<b>В этом чате</b>",
                f"Сообщений: <b>{chat_stats['messages']}</b>",
                f"Побед в розыгрыше: <b>{chat_stats['giveawayWins']}</b>",
                f"Roll mute: <b>{chat_stats['rollMuteCount']}</b>",
            ]
        )
    return "\n".join(lines)
