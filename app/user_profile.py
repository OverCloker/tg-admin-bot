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
    "rank_digger": "Знак проходчика",
    "rank_artifacts": "Коллекция бригадира",
    "rank_depth": "Барон глубин",
    "rank_master": "Хозяин коллекции",
}

ACHIEVEMENT_RARITY = {
    "common": {"title": "Обычное", "score": 1},
    "rare": {"title": "Редкое", "score": 2},
    "epic": {"title": "Эпическое", "score": 3},
    "legendary": {"title": "Легендарное", "score": 4},
    "mythic": {"title": "Мифическое", "score": 5},
}

ACHIEVEMENT_RARITY_BY_KEY = {
    "first_dig": "common",
    "first_meter": "common",
    "stone_zero": "common",
    "streak_3": "common",
    "collapse_survive": "rare",
    "five_meter_run": "rare",
    "route_master": "rare",
    "total_25": "rare",
    "first_purchase": "rare",
    "expedition": "rare",
    "level_5": "epic",
    "streak_5": "epic",
    "coins_500": "epic",
    "rank_digger": "epic",
    "collector_3": "epic",
    "ten_meter_run": "legendary",
    "total_100": "legendary",
    "level_10": "legendary",
    "streak_10": "legendary",
    "rank_artifacts": "legendary",
    "low_luck": "legendary",
    "collector_all": "mythic",
    "coins_10000": "mythic",
    "rank_depth": "mythic",
    "rank_master": "mythic",
}

ITEM_NAMES = {
    "profile_frame_aurora": "Рамка: Северное сияние",
    "profile_bg_stars": "Фон: Звёздная пещера",
    "helmet": "Каска",
    "shovel": "Кирка",
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
    "shovel_1": "Кирка I",
    "shovel_2": "Кирка II",
    "shovel_3": "Кирка III",
    "helmet_1": "Каска I",
    "helmet_2": "Каска II",
    "helmet_3": "Каска III",
    "flashlight_1": "Фонарь I",
    "flashlight_2": "Фонарь II",
    "flashlight_3": "Фонарь III",
    "cart": "Вагонетка",
    "cart_1": "Вагонетка I",
    "cart_2": "Вагонетка II",
    "cart_3": "Вагонетка III",
    "backpack_1": "Рюкзак I",
    "backpack_2": "Рюкзак II",
    "backpack_3": "Рюкзак III",
    "star_dig": "Оплаченная копка",
    "star_lucky_dig": "Копка со 100 удачей",
    "star_depth_10": "Прокопать 10 м",
    "golden_ticket": "Золотой билет",
    "super_game_pass": "Супер-игра 9×9",
    "super_mute30": "Право на мут 30 минут",
    "super_tag": "Право выбрать тег",
    "artifact_coin": "Старая монета",
    "artifact_fossil": "Окаменелость",
    "artifact_crystal": "Подземный кристалл",
    "artifact_tool": "Ржавый шахтёрский инструмент",
    "artifact_gem": "Необработанный самоцвет",
    "artifact_badge": "Знак старой бригады",
    "artifact_set_reward": "Бонус полной коллекции",
    "profile_frame_copper": "Рамка профиля: Медная",
    "profile_frame_crystal": "Рамка профиля: Кристальная",
    "profile_bg_old_mine": "Фон профиля: Старая шахта",
    "profile_bg_lava": "Фон профиля: Лавовые тоннели",
    "profile_badge_pickaxe": "Значок профиля: ⛏️",
    "profile_badge_gem": "Значок профиля: 💎",
    "gift_tea_friend": "Подарок: Чай другу",
    "gift_yarn": "Подарок: Клубок котику",
    "gift_crystal": "Подарок: Маленький кристалл",
    "gift_anonymous": "Анонимный подарок",
    "gift_chest": "Сундук другу",
    "couple_flower": "Подарок паре: Цветок",
    "couple_crystal": "Подарок паре: Парный кристалл",
    "couple_frame": "Парная рамка профиля",
    "couple_date": "Свидание в шахте",
    "res_stone": "Каменная крошка",
    "res_coal": "Уголь",
    "res_iron": "Железная руда",
    "res_silver": "Серебряная жила",
    "res_crystal": "Осколок кристалла",
    "res_fossil": "Древний отпечаток",
    "res_ember": "Пламенная руда",
    "res_glow_moss": "Светящийся мох",
}

ITEM_GROUPS = {
    "profile_frame_aurora": "profile",
    "profile_bg_stars": "profile",
    "artifact_coin": "collection",
    "artifact_fossil": "collection",
    "artifact_crystal": "collection",
    "artifact_tool": "collection",
    "artifact_gem": "collection",
    "artifact_badge": "collection",
    "artifact_set_reward": "collection",
    "profile_frame_copper": "profile",
    "profile_frame_crystal": "profile",
    "profile_bg_old_mine": "profile",
    "profile_bg_lava": "profile",
    "profile_badge_pickaxe": "profile",
    "profile_badge_gem": "profile",
    "gift_tea_friend": "gifts",
    "gift_yarn": "gifts",
    "gift_crystal": "gifts",
    "gift_anonymous": "gifts",
    "gift_chest": "gifts",
    "couple_flower": "relationships",
    "couple_crystal": "relationships",
    "couple_frame": "relationships",
    "couple_date": "relationships",
    "shovel_1": "permanent",
    "shovel_2": "permanent",
    "shovel_3": "permanent",
    "helmet_1": "permanent",
    "helmet_2": "permanent",
    "helmet_3": "permanent",
    "flashlight_1": "permanent",
    "flashlight_2": "permanent",
    "flashlight_3": "permanent",
    "cart": "permanent",
    "cart_1": "permanent",
    "cart_2": "permanent",
    "cart_3": "permanent",
    "backpack_1": "permanent",
    "backpack_2": "permanent",
    "backpack_3": "permanent",
    "golden_ticket": "tickets",
    "super_game_pass": "paid",
    "super_mute30": "paid",
    "super_tag": "paid",
    "res_stone": "resources",
    "res_coal": "resources",
    "res_iron": "resources",
    "res_silver": "resources",
    "res_crystal": "resources",
    "res_fossil": "resources",
    "res_ember": "resources",
    "res_glow_moss": "resources",
    "star_dig": "paid",
    "star_lucky_dig": "paid",
    "star_depth_10": "paid",
}

ITEM_GROUP_TITLES = {
    "collection": "Коллекция",
    "permanent": "Улучшения",
    "profile": "Оформление профиля",
    "gifts": "Подарки",
    "relationships": "Отношения",
    "paid": "Оплаченные",
    "tickets": "Билеты",
    "consumable": "Припасы",
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


def _profile_cosmetics(items: dict[str, int], selection: dict | None = None) -> dict[str, Any]:
    frames = [
        ("profile_frame_aurora", "Северное сияние"),
        ("profile_frame_crystal", "Кристальная рамка"),
        ("profile_frame_copper", "Медная рамка"),
        ("couple_frame", "Парная рамка"),
    ]
    backgrounds = [
        ("profile_bg_stars", "Звёздная пещера"),
        ("profile_bg_lava", "Лавовые тоннели"),
        ("profile_bg_old_mine", "Старая шахта"),
    ]
    badges = [
        ("profile_badge_gem", "💎", "Кристальный значок"),
        ("profile_badge_pickaxe", "⛏️", "Значок шахтёра"),
    ]
    owned_badges = [
        {"key": key, "emoji": emoji, "title": title}
        for key, emoji, title in badges
        if items.get(key, 0) > 0
    ]
    frame = next(({"key": key, "title": title} for key, title in frames if items.get(key, 0) > 0), None)
    background = next(({"key": key, "title": title} for key, title in backgrounds if items.get(key, 0) > 0), None)
    if selection is not None:
        frame = next(({"key": key, "title": title} for key, title in frames if key == selection.get("frame") and items.get(key, 0) > 0), None)
        background = next(({"key": key, "title": title} for key, title in backgrounds if key == selection.get("background") and items.get(key, 0) > 0), None)
        owned_badges = [badge for badge in owned_badges if badge["key"] == selection.get("badge")]
    return {
        "frame": frame,
        "background": background,
        "badges": owned_badges,
        "ownedCount": sum(1 for key in items if ITEM_GROUPS.get(key) == "profile" and items.get(key, 0) > 0),
    }


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
    social = None
    if chat_id is not None:
        chat_stats = {
            "messages": db.message_count_for_user(chat_id, user_id),
            "giveawayWins": db.giveaway_wins_for_user(chat_id, user_id),
            "rollMuteCount": db.roll_mute_count_for_user(chat_id, user_id),
        }
        friends = db.list_chat_friends(chat_id, user_id, limit=5)
        partner = db.get_chat_partner(chat_id, user_id)
        couple = db.get_chat_couple(chat_id, user_id)
        social = {
            "friendsCount": db.count_chat_friends(chat_id, user_id),
            "friends": [
                {
                    "id": friend.user_id,
                    "username": friend.username or "",
                    "fullName": friend.full_name,
                }
                for friend in friends
            ],
            "partner": (
                {
                    "id": partner.user_id,
                    "username": partner.username or "",
                    "fullName": partner.full_name,
                    "since": _format_dt(couple.created_at if couple else None),
                }
                if partner
                else None
            ),
        }

    active_items = [
        {
            "key": key,
            "name": ITEM_NAMES.get(key, key),
            "quantity": quantity,
            "group": ITEM_GROUPS.get(key, "consumable"),
            "groupTitle": ITEM_GROUP_TITLES.get(ITEM_GROUPS.get(key, "consumable"), "Припасы"),
        }
        for key, quantity in sorted(items.items())
        if quantity > 0 and not key.startswith("rank_")
    ]
    owned_achievements = [
        {
            "key": item.achievement_key,
            "name": ACHIEVEMENT_NAMES.get(item.achievement_key, item.achievement_key),
            "rarity": ACHIEVEMENT_RARITY_BY_KEY.get(item.achievement_key, "common"),
            "rarityTitle": ACHIEVEMENT_RARITY[ACHIEVEMENT_RARITY_BY_KEY.get(item.achievement_key, "common")]["title"],
            "rarityScore": ACHIEVEMENT_RARITY[ACHIEVEMENT_RARITY_BY_KEY.get(item.achievement_key, "common")]["score"],
            "createdAt": item.created_at,
        }
        for item in achievements
    ]
    rare_achievements = sorted(
        owned_achievements,
        key=lambda item: (int(item["rarityScore"]), str(item["createdAt"])),
        reverse=True,
    )

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
            "cosmetics": _profile_cosmetics(items, db.get_profile_style(user_id)),
            "gifts": [
                {"id": gift["id"], "title": ITEM_NAMES.get(gift["item_key"], gift["item_key"]),
                 "sender": "Аноним" if gift["item_key"] == "gift_anonymous" else ("@" + gift["username"] if gift["username"] else gift["full_name"] or str(gift["sender_id"])),
                 "createdAt": gift["created_at"], "pinned": bool(gift["pinned"])}
                for gift in db.list_profile_gifts(user_id)
            ],
            "achievements": owned_achievements[-8:],
            "rareAchievements": rare_achievements[:6],
            "achievementsTotal": len(owned_achievements),
            "achievementsKnown": len(ACHIEVEMENT_NAMES),
        },
        "chatStats": chat_stats,
        "social": social,
    }


def profile_chat_text(profile: dict[str, Any], short: bool = True) -> str:
    user = profile["user"]
    premium = profile["premium"]
    mine = profile["mine"]
    chat_stats = profile.get("chatStats")
    social = profile.get("social")
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
    if social:
        lines.extend(["", "<b>Отношения в этом чате</b>"])
        partner = social.get("partner")
        if partner:
            since = f" · с {escape(partner['since'])}" if partner.get("since") else ""
            lines.append(f"Пара: <b>{escape(partner['fullName'])}</b>{since}")
        else:
            lines.append("Пара: <b>нет</b>")
        lines.append(f"Друзей: <b>{social['friendsCount']}</b>")
        if not short and social.get("friends"):
            names = ", ".join(escape(friend["fullName"]) for friend in social["friends"])
            lines.append(f"Близкие: {names}")
    return "\n".join(lines)
