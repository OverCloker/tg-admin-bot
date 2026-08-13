import asyncio
import json
import logging
import math
import os
import random
import re
import secrets
import socket
import sys
import time
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from datetime import timedelta
from html import escape, unescape
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import aiohttp
from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatMemberStatus, ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNotFound, TelegramRetryAfter
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Chat, ChatMemberUpdated, ChatPermissions, FSInputFile, Gift, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo, InputRichBlockDetails, InputRichBlockParagraph, InputRichBlockTable, InputRichMessage, LabeledPrice, MenuButtonWebApp, Message, MessageReactionUpdated, PreCheckoutQuery, RichBlockTableCell, StarAmount, SuccessfulPayment, User, WebAppInfo

from .config import load_config
from .db import Database, RegisteredChat, normalize_trigger, normalize_username
from .dig_game import (
    INTERACTIVE_DIG_DURABILITY,
    INTERACTIVE_DIG_MAX_DEPTH,
    MINE_RESOURCE_CATALOG,
    MINE_RESOURCE_ORDER,
    cell_row_is_exhausted,
    cell_reward,
    collapse_payout,
    event_choice,
    final_cell_chance,
    final_depth_bonus,
    generate_dig_cells,
    generate_dig_stage,
    generate_event_stage,
    mined_resource_drops,
    mine_type_for_total_depth,
    replacement_cell_stage,
    resolve_cell,
    resource_stack_text,
    scale_interactive_reward,
)
from .premium import PLANS, PREMIUM_PERIOD_DAYS, PremiumLimitError, PremiumRequiredError, PremiumService
from .media_processor import TASK_TITLES, ffmpeg_available, probe_media_duration, process_media, whisper_available
from .media_tasks import MediaTaskService
from .youtube_media import (
    DOWNLOAD_TYPES,
    SUPPORTED_MEDIA_URL_RE,
    YoutubeMediaError,
    cleanup_youtube_file,
    download_youtube,
    extract_instagram_url,
    extract_supported_media_url,
    inspect_youtube,
    media_output_filename,
)
from .staff import StaffService
from .staff_handlers import configure_staff, staff_error_handler, staff_router
from .user_profile import build_user_profile, profile_chat_text
from .keyboards import (
    QUOTES_PAGE_SIZE,
    TOP_PAGE_SIZE,
    TRIGGERS_PAGE_SIZE,
    admin_back_menu,
    admin_menu,
    alarm_menu,
    back_to_chat_menu,
    blacklist_menu,
    chat_admin_menu,
    chat_select_menu,
    chat_top_page_menu,
    dig_bag_menu,
    dig_buy_confirm_menu,
    dig_register_menu,
    dig_routes_menu,
    dig_section_back_menu,
    dig_shift_contract_menu,
    dig_shop_categories_menu,
    dig_shop_items_menu,
    birthday_menu,
    feedback_reply_menu,
    giveaway_menu,
    instagram_download_menu,
    interactive_dig_menu,
    leave_confirm_menu,
    main_menu,
    media_cancel_menu,
    media_tools_menu,
    miniapp_deep_link,
    miniapp_private_menu,
    moderator_demote_menu,
    moderator_panel_menu,
    paid_chat_select_menu,
    participant_top_menu,
    premium_menu,
    quotes_menu,
    quiet_menu,
    restart_confirm_menu,
    social_couple_end_menu,
    social_profile_menu,
    social_request_menu,
    stars_menu,
    topic_select_menu,
    trigger_list_menu,
    user_bag_menu,
    user_shift_contract_menu,
    user_buy_confirm_menu,
    user_chat_select_menu,
    user_dig_mode_menu,
    user_mine_menu,
    user_menu,
    user_routes_menu,
    user_shop_categories_menu,
    user_shop_items_menu,
    youtube_download_menu,
)


MENTION_RE = re.compile(r"(?<![\w@])@([A-Za-z0-9_]{5,32})")
ADMIN_STATUSES = {ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR}
ADMIN_STATUS_TEXTS = {"creator", "administrator"}
ACTIVE_MEMBER_STATUS_TEXTS = {"creator", "administrator", "member", "restricted"}
SUPPORTED_CHAT_TYPES = {"group", "supergroup"}
MODERATOR_ROLE_SPECS = {
    "assistant": {"title": "Помощник модератора", "short": "Помощник", "max_mute_minutes": 10, "rank": 1},
    "moderator": {"title": "Модератор", "short": "Модератор", "max_mute_minutes": 30, "rank": 2},
    "senior": {"title": "Старший модератор", "short": "Старший", "max_mute_minutes": 60, "rank": 3},
}
MINIAPP_ADMIN_PROFILE_LABEL = "\u0410\u0434\u043c\u0438\u043d"
MODERATOR_ASSIGN_COMMANDS = {
    "+админ": "app_admin",
    "+помощник": "assistant",
    "+модератор": "moderator",
    "+стмодератор": "senior",
}
MODERATOR_REMOVE_COMMANDS = {
    "-помощник": "assistant",
    "-модератор": "moderator",
    "-стмодератор": "senior",
}
MODERATOR_MUTE_ALERT_THRESHOLD = 3
MODERATOR_MUTE_ALERT_WINDOW_HOURS = 24
DICTIONARY_HIT_MUTE_MINUTES = 1
DICTIONARY_HIT_PHOTO_PATH = Path(__file__).with_name("assets") / "dictionary_hit.jpg"
DAY_PICK_KEY = "day_pick"
DAY_QUERY_TEXT = "кто пидор"
DAY_REPLY_TEMPLATE = "Пидор дня: {user}"
WEATHER_RE = re.compile(r"^погода\s+(.+)$", re.IGNORECASE)
ALARM_STATUS_QUERY_RE = re.compile(r"^\s*тревога[?!.]?\s*$", re.IGNORECASE)
ALARM_CLEAR_QUERY_RE = re.compile(r"^\s*отбой[?!.]?\s*$", re.IGNORECASE)
ALARM_STATUS_COMMAND_RE = re.compile(r"^\s*состояние\s+тревоги[?!.]?\s*$", re.IGNORECASE)
ALARM_TOPIC_COMMAND_RE = re.compile(
    r"^\s*(?:[!/])?тревога\s+тема(?:\s+(основной|сброс|сбросить))?[?!.]?\s*$",
    re.IGNORECASE,
)
ALERTS_LOCATION_UID = "46"
ALERTS_LOCATION_TITLE = "Криворізький район"
ALERTS_POLL_INTERVAL_SECONDS = 60
SECRET_MESSAGE_ALERT_LIMIT = 190
GIVEAWAY_TOP_RE = re.compile(r"^топ\s+пидоров[?!.]?$", re.IGNORECASE)
SECRET_MESSAGE_RE = re.compile(
    r"^\s*(?:лс|личка)(?:\s+(@[A-Za-z0-9_]{5,32}))?(?:\s+(.+))?\s*$",
    re.IGNORECASE | re.DOTALL,
)
EMOJI_BASE_RE = (
    r"(?:[\u00a9\u00ae\u203c\u2049\u2122\u2139\u2194-\u21ff\u2300-\u23ff"
    r"\u24c2\u25aa-\u27bf\u2934\u2935\u2b00-\u2bff\u3030\u303d\u3297\u3299]"
    r"|[\U0001f000-\U0001faff])"
)
EMOJI_MODIFIER_RE = r"(?:\ufe0e|\ufe0f)?(?:[\U0001f3fb-\U0001f3ff])?"
EMOJI_ELEMENT_RE = rf"{EMOJI_BASE_RE}{EMOJI_MODIFIER_RE}"
SINGLE_EMOJI_RE = re.compile(
    rf"^(?:"
    rf"[\U0001f1e6-\U0001f1ff]{{2}}"
    rf"|[#*0-9]\ufe0f?\u20e3"
    rf"|{EMOJI_ELEMENT_RE}(?:\u200d{EMOJI_ELEMENT_RE})*(?:[\U000e0020-\U000e007e]*\U000e007f)?"
    rf")$"
)
DIG_COOLDOWN = timedelta(hours=3)
DIG_LUCK_COST = 35
DIG_LUCK_REGEN_PER_HOUR = 7
AUTO_DIG_REWARD_SCALE_PERCENT = 65
DIG_STAR_LUCK_PRICE = 3
DIG_STAR_COOLDOWN_PRICE = 1
DIG_STAR_ACTIONS = {
    "luck": ("Восстановить удачу", "Удача в раскопках станет 100/100.", DIG_STAR_LUCK_PRICE, None, 0),
    "cooldown": ("Сбросить ожидание копай", "Команду копай можно будет использовать сразу после оплаты.", DIG_STAR_COOLDOWN_PRICE, None, 0),
    "digs3": ("Копать 3 раза", "Три дополнительные раскопки без ожидания между попытками.", 3, "star_dig", 3),
    "lucky_digs3": ("Копать 3 раза со 100 удачей", "Три дополнительные раскопки без ожидания. В каждой действует 100 удачи.", 10, "star_lucky_dig", 3),
    "digs5": ("Копать 5 раз", "Пять дополнительных раскопок без ожидания между попытками.", 5, "star_dig", 5),
    "lucky_digs5": ("Копать 5 раз со 100 удачей", "Пять дополнительных раскопок без ожидания. В каждой действует 100 удачи.", 15, "star_lucky_dig", 5),
    "depth10": ("Прокопать 10 м", "Следующая раскопка гарантированно пройдет все 10 метров без ожидания.", 50, "star_depth_10", 1),
    "golden_ticket": ("Золотой билет", "Одна игра 3×3 с тремя призами: 10, 25 и 50 котоинов.", 2, "golden_ticket", 1),
    "super_game": ("Супер-игра 9×9", "Одна супер-игра: 10 попыток, 10 денежных призов, 5 призов по 5 котоинов и три сундука с особыми наградами.", 10, "super_game_pass", 1),
    "super_mute30": ("Право на мут 30 минут", "Покупка добавит в сумку одно право выдать мут на полчаса в чате. Используется так же, как награда из сундука.", 3, "super_mute30", 1),
}
DIG_SUCCESS_CHANCES = [90.0, 80.0, 70.0, 60.0, 50.0, 40.0, 30.0, 20.0, 10.0, 1.0]
DIG_REWARDS = {
    0: (1, 5),
    1: (5, 10),
    2: (10, 20),
    3: (20, 30),
    4: (30, 40),
    5: (40, 50),
    6: (50, 60),
    7: (60, 70),
    8: (70, 80),
    9: (80, 90),
    10: (90, 100),
}
DIG_ROUTES = {
    "old_mine": ("Старая шахта", 8, 0.85, 0.8, 0.7, 1),
    "gold_vein": ("Золотая жила", -5, 1.5, 1.0, 1.25, 3),
    "abandoned_tunnel": ("Заброшенный тоннель", 0, 1.0, 2.0, 1.0, 5),
    "deep_zone": ("Глубинная зона", -8, 2.0, 1.5, 1.5, 10),
}
DIG_STANDARD_CONTRACTS = {
    "depth": ("Прокопать 12 метров", 12),
    "coins": ("Заработать 120 котоинов", 120),
    "artifact": ("Найти артефакт", 1),
    "success": ("Три успешные раскопки", 3),
}
DIG_RANK_SHIFT_CONTRACTS = {
    "shift_depth_4": ("Смена: пройти 4 метра", "depth", 4, 80),
    "shift_coins_60": ("Смена: добыть 60 котоинов", "coins", 60, 100),
    "shift_artifact": ("Смена: найти артефакт", "artifact", 1, 140),
}
DIG_CONTRACTS = {
    **DIG_STANDARD_CONTRACTS,
    **{key: (name, target) for key, (name, _, target, _) in DIG_RANK_SHIFT_CONTRACTS.items()},
}
DIG_CONTRACT_REWARD_COINS = 60
DIG_CONTRACT_REWARD_XP = 40
DIG_EXPEDITION_TARGET = 50
DIG_EXPEDITION_REWARD = 75
DIG_GOLDEN_TICKET_MAX_CHANCE = 50
DIG_SHOP_ITEMS = {
    "helmet": ("Каска шахтера", 40, "Старый расходник: +5 удачи на следующую раскопку."),
    "shovel": ("Крепкая кирка", 70, "Старый расходник: снижает шанс обвала на 50% в следующей раскопке."),
    "flashlight": ("Фонарик", 90, "Старый расходник: +10% к шансам следующей раскопки."),
    "bucket": ("Премиум ведро", 100, "Старый расходник: +25% котоинов в следующей раскопке."),
    "prank": ("Подстава", 200, "Старая шуточная шахтерская проверка."),
    "shovel_1": ("Кирка I", 250, "Постоянно добавляет +2% к шансу пройти каждый метр."),
    "shovel_2": ("Кирка II", 700, "Улучшает постоянный бонус кирки до +4%. Требуется Кирка I."),
    "shovel_3": ("Кирка III", 1500, "Улучшает постоянный бонус кирки до +6%. Требуется Кирка II."),
    "cart": ("Вагонетка", 800, "Постоянно увеличивает награду каждой раскопки на 10%."),
    "helmet_1": ("Каска I", 300, "Постоянно снижает риск обвала на 10%."),
    "helmet_2": ("Каска II", 800, "Снижает риск обвала на 20%. Требуется Каска I."),
    "helmet_3": ("Каска III", 1700, "Снижает риск обвала на 30%. Требуется Каска II."),
    "flashlight_1": ("Фонарь I", 350, "Постоянно повышает шанс артефакта на 3%."),
    "flashlight_2": ("Фонарь II", 900, "Повышает шанс артефакта на 6%. Требуется Фонарь I."),
    "flashlight_3": ("Фонарь III", 1900, "Повышает шанс артефакта на 10%. Требуется Фонарь II."),
    "cart_2": ("Вагонетка II", 1600, "Улучшает постоянный бонус котоинов до 20%. Требуется Вагонетка."),
    "cart_3": ("Вагонетка III", 3500, "Улучшает постоянный бонус котоинов до 35%. Требуется Вагонетка II."),
    "backpack_1": ("Рюкзак I", 800, "Постоянно добавляет 5% к найденным котоинам."),
    "backpack_2": ("Рюкзак II", 1800, "Улучшает бонус добычи до 10%. Требуется Рюкзак I."),
    "backpack_3": ("Рюкзак III", 4000, "Улучшает бонус добычи до 15%. Требуется Рюкзак II."),
    "compass": ("Компас", 250, "Усиливает бонус выбранного маршрута в следующей раскопке."),
    "scanner": ("Сканер породы", 180, "Снижает риск следующего обвала на 30%."),
    "drill": ("Бур", 400, "Гарантированно пробивает один неудачный метр."),
    "medkit": ("Аптечка", 120, "Отменяет следующую потерю котоинов от случайного события."),
    "map": ("Карта тоннелей", 300, "Добавляет 15% к шансу артефакта в следующей раскопке."),
    "talisman": ("Талисман", 500, "Удваивает котоины следующей раскопки."),
    "camp": ("Переносной лагерь", 1200, "Один раз сокращает ожидание раскопки на 50%."),
    "repair_kit": ("Ремонтный набор", 200, "После раскопки возвращает один использованный расходник."),
    "mystery_chest": ("Таинственный сундук", 350, "В следующей раскопке даёт случайную награду или пустышку."),
    "dynamite": ("Динамит", 150, "Один раз за вылазку ослабляет сложные клетки. Риск 20%: взрыв в руках, -1 прочность и метр не пробит."),
    "insurance": ("Страховка", 60, "Если раскопка провалилась на первом метре, засчитает 1 метр."),
    "cursed_pick": ("Защита от сглаза", 60, "Одноразово защищает от roll mute."),
    "tea": ("Чай перед сменой", 40, "Кладется в сумку и вручную восстанавливает +35 удачи."),
    "safe": ("Сейф", 100, "Один раз защищает от потери глубины при обвале."),
    "rank_1": ("Ранг: Проходчик", 500, "Постоянно: +5% котоинов за раскопку."),
    "rank_2": ("Ранг: Бригадир", 1200, "Постоянно: +10% котоинов и +1 удача/ч. Требуется Проходчик."),
    "rank_3": ("Ранг: Шахтерный барон", 2500, "Постоянно: +15% котоинов, +1% к шансу метров и +2 удачи/ч. Требуется Бригадир."),
    "rank_4": ("Ранг: Хозяин глубин", 5000, "Постоянно: +20% котоинов, +2% к шансу метров и +3 удачи/ч. Требуется Шахтерный барон."),
    "star_dig": ("Дополнительная раскопка", 0, "Позволяет копать без ожидания между попытками."),
    "star_lucky_dig": ("Раскопка со 100 удачей", 0, "Позволяет копать без ожидания и защищает от обвала за счет 100 удачи."),
    "star_depth_10": ("Гарантированная раскопка 10 м", 0, "Следующая раскопка гарантированно пройдет 10 метров без ожидания."),
    "profile_frame_copper": ("Рамка профиля: Медная", 500, "Постоянное оформление профиля. Показывает, что ты не просто копал, а уже вложился в стиль."),
    "profile_frame_crystal": ("Рамка профиля: Кристальная", 2500, "Редкая рамка профиля с кристальным оттенком для витрины игрока."),
    "profile_bg_old_mine": ("Фон профиля: Старая шахта", 700, "Постоянный фон карточки профиля в стиле старой шахты."),
    "profile_bg_lava": ("Фон профиля: Лавовые тоннели", 3000, "Дорогой фон профиля для тех, кто дошёл до горячих глубин."),
    "profile_badge_pickaxe": ("Значок профиля: ⛏️", 400, "Постоянный значок шахтёра рядом с оформлением профиля."),
    "profile_badge_gem": ("Значок профиля: 💎", 1500, "Постоянный кристальный значок для профиля."),
    "gift_tea_friend": ("Подарок: Чай другу", 50, "Маленький подарок для будущей отправки другу. Хороший способ потратить мелочь с теплом."),
    "gift_yarn": ("Подарок: Клубок котику", 100, "Милый подарок другу в коллекцию подарков."),
    "gift_crystal": ("Подарок: Маленький кристалл", 300, "Редкий сувенир, который можно будет подарить другу."),
    "gift_anonymous": ("Анонимный подарок", 500, "Подарок без подписи. Для случаев, когда хочется быть загадочным котом."),
    "gift_chest": ("Сундук другу", 750, "Подарочный сундук для будущей отправки другу."),
    "couple_flower": ("Подарок паре: Цветок", 150, "Небольшой знак внимания для пары."),
    "couple_crystal": ("Подарок паре: Парный кристалл", 1000, "Дорогой сувенир для отношений."),
    "couple_frame": ("Парная рамка профиля", 3500, "Постоянная косметика для будущего оформления пары."),
    "couple_date": ("Свидание в шахте", 800, "Расходник для будущего парного события."),
}
DIG_SHOP_ITEMS["golden_ticket"] = (
    "Золотой билет",
    1500,
    "Один билет для игры 3×3 в шахте Mini App.",
)
DYNAMITE_MISHAP_CHANCE = 20
DYNAMITE_MISHAP_MESSAGE = "Из-за неосторожного обращения динамит взорвался в руках. Метр не пробит."
DIG_ITEM_ORDER = [
    "tea", "insurance", "dynamite", "safe", "compass", "scanner", "drill", "medkit", "map", "talisman", "camp", "repair_kit", "mystery_chest",
    "shovel_1", "shovel_2", "shovel_3", "helmet_1", "helmet_2", "helmet_3",
    "flashlight_1", "flashlight_2", "flashlight_3", "cart", "cart_2", "cart_3", "backpack_1", "backpack_2", "backpack_3",
    "cursed_pick",
    "rank_1", "rank_2", "rank_3", "rank_4",
    "profile_frame_copper", "profile_frame_crystal", "profile_bg_old_mine", "profile_bg_lava", "profile_badge_pickaxe", "profile_badge_gem",
    "gift_tea_friend", "gift_yarn", "gift_crystal", "gift_anonymous", "gift_chest",
    "couple_flower", "couple_crystal", "couple_frame", "couple_date",
]
DIG_SHOP_PAGE_SIZE = 6
DIG_SHOP_CATEGORIES = {
    "consumables": (
        "Расходники",
        ["tea", "insurance", "dynamite", "medkit", "repair_kit", "cursed_pick"],
    ),
    "gear": (
        "Снаряжение",
        ["safe", "compass", "scanner", "drill", "map", "talisman", "camp", "mystery_chest", "prank"],
    ),
    "upgrades": (
        "Улучшения",
        [
            "shovel_1", "shovel_2", "shovel_3",
            "helmet_1", "helmet_2", "helmet_3",
            "flashlight_1", "flashlight_2", "flashlight_3",
            "cart", "cart_2", "cart_3",
            "backpack_1", "backpack_2", "backpack_3",
        ],
    ),
    "ranks": (
        "Ранги",
        ["rank_1", "rank_2", "rank_3", "rank_4"],
    ),
    "games": (
        "Игры",
        ["golden_ticket"],
    ),
    "profile": (
        "Профиль",
        ["profile_frame_copper", "profile_frame_crystal", "profile_bg_old_mine", "profile_bg_lava", "profile_badge_pickaxe", "profile_badge_gem"],
    ),
    "gifts": (
        "Подарки",
        ["gift_tea_friend", "gift_yarn", "gift_crystal", "gift_anonymous", "gift_chest"],
    ),
    "relationships": (
        "Отношения",
        ["couple_flower", "couple_crystal", "couple_frame", "couple_date"],
    ),
}
DIG_SHOP_CATEGORY_ORDER = ["consumables", "gear", "upgrades", "ranks", "games", "profile", "gifts", "relationships"]
DIG_SHOP_UPGRADE_CHAINS = [
    ["shovel_1", "shovel_2", "shovel_3"],
    ["helmet_1", "helmet_2", "helmet_3"],
    ["flashlight_1", "flashlight_2", "flashlight_3"],
    ["cart", "cart_2", "cart_3"],
    ["backpack_1", "backpack_2", "backpack_3"],
    ["rank_1", "rank_2", "rank_3", "rank_4"],
]
DIG_SHOP_ITEM_CATEGORY = {
    item_key: category_key
    for category_key, (_, item_keys) in DIG_SHOP_CATEGORIES.items()
    for item_key in item_keys
}
DIG_PERMANENT_ITEMS = {
    "shovel_1", "shovel_2", "shovel_3", "helmet_1", "helmet_2", "helmet_3",
    "flashlight_1", "flashlight_2", "flashlight_3", "cart", "cart_2", "cart_3",
    "backpack_1", "backpack_2", "backpack_3", "rank_1", "rank_2", "rank_3", "rank_4",
    "profile_frame_copper", "profile_frame_crystal", "profile_bg_old_mine", "profile_bg_lava",
    "profile_badge_pickaxe", "profile_badge_gem", "couple_frame",
}
DIG_PROFILE_ITEMS = {
    "profile_frame_copper", "profile_frame_crystal", "profile_bg_old_mine", "profile_bg_lava",
    "profile_badge_pickaxe", "profile_badge_gem",
}
DIG_GIFT_ITEMS = {"gift_tea_friend", "gift_yarn", "gift_crystal", "gift_anonymous", "gift_chest"}
DIG_RELATIONSHIP_ITEMS = {"couple_flower", "couple_crystal", "couple_frame", "couple_date"}
DIG_ITEM_REQUIREMENTS = {
    "shovel_2": "shovel_1",
    "shovel_3": "shovel_2",
    "helmet_2": "helmet_1",
    "helmet_3": "helmet_2",
    "flashlight_2": "flashlight_1",
    "flashlight_3": "flashlight_2",
    "cart_2": "cart",
    "cart_3": "cart_2",
    "backpack_2": "backpack_1",
    "backpack_3": "backpack_2",
    "rank_2": "rank_1",
    "rank_3": "rank_2",
    "rank_4": "rank_3",
}
DIG_ARTIFACTS = {
    "artifact_coin": "Старая монета",
    "artifact_fossil": "Окаменелость",
    "artifact_crystal": "Подземный кристалл",
    "artifact_tool": "Ржавый шахтёрский инструмент",
    "artifact_gem": "Необработанный самоцвет",
    "artifact_badge": "Знак старой бригады",
}
DIG_RANKS = [
    ("rank_4", "Хозяин глубин"),
    ("rank_3", "Шахтерный барон"),
    ("rank_2", "Бригадир"),
    ("rank_1", "Проходчик"),
]
DIG_RANK_BONUSES = {
    "rank_1": {"coins": 5, "chance": 0, "luck_regen": 0},
    "rank_2": {"coins": 10, "chance": 0, "luck_regen": 1},
    "rank_3": {"coins": 15, "chance": 1, "luck_regen": 2},
    "rank_4": {"coins": 20, "chance": 2, "luck_regen": 3},
}
DIG_RANK_DISCOUNTS = {
    "rank_1": 5,
    "rank_2": 10,
    "rank_3": 15,
    "rank_4": 20,
}
ADMIN_FEATURES = [
    ("addReply", "Добавить @ответ"),
    ("deleteReply", "Удалить @ответ"),
    ("triggers", "Список триггеров"),
    ("participants", "Топ участников"),
    ("checkAccess", "Проверить доступ"),
    ("giveaway", "Настроить розыгрыш"),
    ("restart", "Перезагрузка"),
    ("alarm", "Режим тревоги"),
    ("rollMute", "Roll mute"),
    ("quiet", "Затихни"),
    ("blacklist", "Черный список слов"),
    ("quotes", "Цитаты"),
    ("send", "Написать в чат"),
    ("feedback", "Обратная связь"),
    ("ads", "Реклама"),
    ("stars", "Звезды"),
    ("mine", "Шахта"),
    ("logs", "Логи"),
]
ADMIN_FEATURE_IDS = {feature_id for feature_id, _ in ADMIN_FEATURES}
ADMIN_SUBFEATURES = {
    "triggers": [("triggers.add", "Добавить слово"), ("triggers.delete", "Удалить слово")],
    "blacklist": [("blacklist.add", "Добавить слово"), ("blacklist.delete", "Удалить слово")],
    "quotes": [("quotes.add", "Добавить цитату"), ("quotes.delete", "Удалить цитату")],
    "send": [("send.text", "Отправить текст"), ("send.media", "Отправить медиа"), ("send.voice", "Отправить голосовое")],
    "giveaway": [("giveaway.settings", "Настройки розыгрыша"), ("giveaway.birthdays", "Дни рождения")],
    "alarm": [
        ("alarm.toggle", "Включить/выключить"),
        ("alarm.api", "Автотревога Alerts.in.ua"),
        ("alarm.restrictions", "Ограничения медиа и реакций"),
        ("alarm.text", "Тексты тревоги"),
    ],
    "rollMute": [("rollMute.settings", "Настройки строк")],
    "quiet": [
        ("quiet.manual", "Замутить"),
        ("quiet.text", "Текст ответа"),
        ("quiet.mediaSave", "Сохранить медиа"),
        ("quiet.mediaDelete", "Удалить медиа"),
    ],
    "mine": [("mine.grant", "Начислить/забрать ресурсы")],
    "feedback": [("feedback.send", "Отправить сообщение")],
    "ads": [
        ("ads.add", "Добавить рекламу"),
        ("ads.edit", "Редактировать рекламу"),
        ("ads.delete", "Удалить рекламу"),
        ("ads.settings", "Настройки рекламы"),
    ],
}
ADMIN_PERMISSION_IDS = ADMIN_FEATURE_IDS | {item_id for items in ADMIN_SUBFEATURES.values() for item_id, _ in items}
ACTION_FEATURES = {
    "set_reply": "addReply",
    "del_reply": "deleteReply",
    "set_trigger": "triggers",
    "del_trigger": "triggers",
    "list": "triggers",
    "participants": "participants",
    "giveaway": "giveaway",
    "alarm": "alarm",
    "roll_mute": "rollMute",
    "quiet": "quiet",
    "blacklist": "blacklist",
    "quotes": "quotes",
    "send_message": "send",
    "check": "checkAccess",
    "logs": "logs",
}
STATE_FEATURES = {
    "set_reply": "addReply",
    "set_reply_media": "addReply",
    "del_reply": "deleteReply",
    "set_trigger": "triggers.add",
    "set_trigger_media": "triggers.add",
    "del_trigger": "triggers.delete",
    "send_message": "send.text",
    "set_giveaway": "giveaway.settings",
    "add_birthday": "giveaway.birthdays",
    "set_alarm_text": "alarm.text",
    "set_clear_text": "alarm.text",
    "set_roll_mute": "rollMute.settings",
    "set_quiet_text": "quiet.text",
    "set_quiet_media": "quiet.mediaSave",
    "set_quiet_manual": "quiet.manual",
    "add_blacklist_word": "blacklist.add",
    "delete_blacklist_word": "blacklist.delete",
    "delete_quote": "quotes.delete",
}
DIG_ACHIEVEMENTS = {
    "first_dig": ("Первый спуск", "Сделать первую раскопку.", 10, None),
    "first_meter": ("Первый метр", "Прокопать хотя бы 1 метр за вылазку.", 15, None),
    "five_meter_run": ("Глубокий вдох", "Прокопать 5 метров за одну вылазку.", 50, "helmet"),
    "ten_meter_run": ("До ядра почти дошел", "Прокопать 10 метров за одну вылазку.", 100, "bucket"),
    "total_25": ("Шахтерская смена", "Прокопать 25 метров всего.", 80, None),
    "total_100": ("Подземный барон", "Прокопать 100 метров всего.", 200, "safe"),
    "coins_500": ("Звенит сумка", "Накопить 500 котоинов.", 100, None),
    "stone_zero": ("Каменная встреча", "Упереться в камень на нулевой глубине.", 20, None),
    "collapse_survive": ("Не завалило", "Пережить обвал и продолжить.", 40, "shovel"),
    "first_purchase": ("Покупатель", "Купить первый предмет в магазине.", 30, None),
    "level_5": ("Опытный проходчик", "Достичь 5 уровня шахтёра.", 100, None),
    "level_10": ("Доступ в глубины", "Достичь 10 уровня шахтёра.", 200, "map"),
    "streak_3": ("На волне", "Сделать 3 успешные раскопки подряд.", 40, None),
    "streak_5": ("Стабильная смена", "Сделать 5 успешных раскопок подряд.", 80, "mystery_chest"),
    "streak_10": ("Не остановить", "Сделать 10 успешных раскопок подряд.", 180, "artifact_gem"),
    "collector_3": ("Археолог", "Найти 3 разных артефакта.", 120, None),
    "collector_all": ("Коллекционер глубин", "Собрать всю коллекцию артефактов.", 300, "talisman"),
    "low_luck": ("На волоске", "Завершить раскопку с удачей ниже 10.", 70, None),
    "route_master": ("Картограф", "Побывать на особом маршруте.", 50, None),
    "expedition": ("Бригада", "Завершить групповую экспедицию.", 100, None),
    "coins_10000": ("Крупный вклад", "Накопить 10000 котоинов.", 500, None),
    "rank_digger": ("Знак проходчика", "Иметь ранг и прокопать 25 метров всего.", 100, "tea"),
    "rank_artifacts": ("Коллекция бригадира", "С рангом найти 3 разных артефакта.", 180, "map"),
    "rank_depth": ("Барон глубин", "С рангом прокопать 150 метров всего.", 300, "mystery_chest"),
    "rank_master": ("Хозяин коллекции", "Хозяином глубин собрать все артефакты.", 600, "talisman"),
}

router = Router()
db: Database
BOT_ADMIN_IDS: set[int] = set()
ALERTS_API_TOKEN: str | None = None
staff_service: StaffService | None = None
premium_service: PremiumService | None = None
BOT_STARTED_AT = datetime.now(timezone.utc)
DIG_PURCHASE_GUARD: dict[tuple[int, int, str, int], datetime] = {}
SENDER_CACHE_SECONDS = 300
ACTIVITY_CACHE_SECONDS = 30
RUNTIME_CACHE_SECONDS = 10
ALARM_RUNTIME_CACHE_SECONDS = 3
REMEMBERED_CHATS: dict[int, float] = {}
REMEMBERED_USERS: dict[tuple[int, int, str | None, str, bool], float] = {}
PARTICIPANT_ACTIVITY_TOUCHES: dict[tuple[int, int], float] = {}
KNOWN_TOPICS: set[tuple[int, int]] = set()
TRIGGER_CACHE: dict[int, tuple[float, list]] = {}
REPLY_CACHE: dict[int, tuple[float, dict[str, object]]] = {}
BLACKLIST_CACHE: dict[int, tuple[float, list]] = {}
AUTO_TRIGGER_SENT_CACHE_SECONDS = 120
AUTO_TRIGGER_SENT_MESSAGES: dict[tuple[int, int], float] = {}
GIFT_FLOW_TTL_SECONDS = 10 * 60
GIFT_PAGE_SIZE = 6
GIFT_SELECTIONS: dict[str, "GiftFlow"] = {}
GIFT_CONFIRM_IN_PROGRESS: set[str] = set()
GIFT_COMPLETED: dict[str, float] = {}


@dataclass
class GiftSummary:
    gift_id: str
    star_count: int
    emoji: str
    title: str
    sticker_file_id: str | None = None
    remaining_count: int | None = None
    total_count: int | None = None
    upgrade_star_count: int | None = None
    is_premium: bool = False


@dataclass
class GiftFlow:
    token: str
    admin_id: int
    created_at: float
    gifts: list[GiftSummary]
    selected_gift_id: str | None = None
    recipient_id: int | None = None
    recipient_label: str | None = None
    confirmed: bool = False


def get_premium_service() -> PremiumService:
    """Return the shared Premium service for both bot and API processes."""
    global premium_service
    if premium_service is None:
        premium_service = PremiumService(load_config().db_path)
    return premium_service
ALARM_RUNTIME_CACHE: dict[int, tuple[float, object]] = {}
CHAT_LOCK_CACHE: dict[int, tuple[float, dict | None]] = {}
BIRTHDAY_CHECK_CACHE: dict[tuple[int, str], float] = {}


async def notify_staff_autoreply_change(bot: Bot, description: str) -> None:
    if staff_service:
        await staff_service.auto_reply_changed(bot, description)


async def notify_staff_moderation(bot: Bot, text: str) -> None:
    if not staff_service:
        return
    sent = await staff_service.send(bot, "moderation", text)
    if not sent:
        await staff_service.send(bot, "logs", text)


def message_content_label(message: Message) -> str:
    content_type = str(getattr(message, "content_type", "") or "")
    if message.text:
        return "текст/ссылка"
    if message.sticker:
        return "стикер"
    if message.animation:
        return "gif/анимация"
    if message.voice:
        return "голосовое"
    if message.audio:
        return "аудио"
    if message.video:
        return "видео"
    if message.video_note:
        return "видеокружок"
    if message.photo:
        return "фото"
    if message.document:
        return "документ"
    return content_type or "сообщение"


async def copy_deleted_message_to_staff(bot: Bot, source: Message, header: str) -> None:
    if not staff_service:
        return
    chat_id = staff_service.chat_id
    topic = "moderation" if staff_service.topic_id("moderation") else "logs"
    thread_id = staff_service.topic_id(topic)
    if chat_id is None or thread_id is None:
        await notify_staff_moderation(bot, header)
        return
    try:
        await bot.send_message(chat_id, header, message_thread_id=thread_id)
        await bot.copy_message(
            chat_id=chat_id,
            from_chat_id=source.chat.id,
            message_id=source.message_id,
            message_thread_id=thread_id,
        )
    except (TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter) as exc:
        await notify_staff_moderation(bot, f"{header}\nНе удалось скопировать сообщение: <code>{escape(str(exc))}</code>")


def invalidate_chat_runtime_cache(chat_id: int) -> None:
    TRIGGER_CACHE.pop(chat_id, None)
    REPLY_CACHE.pop(chat_id, None)
    BLACKLIST_CACHE.pop(chat_id, None)
    ALARM_RUNTIME_CACHE.pop(chat_id, None)


def cached_triggers(chat_id: int):
    now = time.monotonic()
    cached = TRIGGER_CACHE.get(chat_id)
    if cached and now - cached[0] < RUNTIME_CACHE_SECONDS:
        return cached[1]
    items = db.list_trigger_answer_options(chat_id)
    TRIGGER_CACHE[chat_id] = (now, items)
    return items


def cached_replies_map(chat_id: int) -> dict[str, object]:
    now = time.monotonic()
    cached = REPLY_CACHE.get(chat_id)
    if cached and now - cached[0] < RUNTIME_CACHE_SECONDS:
        return cached[1]
    items = {item.username: item for item in db.list_replies(chat_id)}
    REPLY_CACHE[chat_id] = (now, items)
    return items


def cached_blacklist_words(chat_id: int):
    now = time.monotonic()
    cached = BLACKLIST_CACHE.get(chat_id)
    if cached and now - cached[0] < RUNTIME_CACHE_SECONDS:
        return cached[1]
    items = db.list_blacklist_words(chat_id)
    BLACKLIST_CACHE[chat_id] = (now, items)
    return items


def cached_alarm_runtime(chat_id: int) -> tuple[bool, bool, str | None, bool]:
    now = time.monotonic()
    cached = ALARM_RUNTIME_CACHE.get(chat_id)
    if cached and now - cached[0] < ALARM_RUNTIME_CACHE_SECONDS:
        return cached[1]
    settings = db.get_alarm_settings(chat_id)
    state = (
        db.alarm_restrictions_enabled(chat_id),
        db.alarm_api_enabled(chat_id),
        db.alarm_api_last_status(chat_id),
        bool(settings.permissions_json),
    )
    ALARM_RUNTIME_CACHE[chat_id] = (now, state)
    return state


def cached_chat_lock(chat_id: int) -> dict | None:
    now = time.monotonic()
    cached = CHAT_LOCK_CACHE.get(chat_id)
    if cached and now - cached[0] < ALARM_RUNTIME_CACHE_SECONDS:
        return cached[1]
    lock = db.get_chat_lock(chat_id, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    CHAT_LOCK_CACHE[chat_id] = (now, lock)
    return lock


def invalidate_chat_lock_cache(chat_id: int) -> None:
    CHAT_LOCK_CACHE.pop(chat_id, None)


class DropStaleMessagesMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, Message) and event.date < BOT_STARTED_AT:
            return None
        return await handler(event, data)


class StaffTopicMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, Message) and staff_service:
            staff_service.observe_message(event)
        return await handler(event, data)


class BlacklistMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if (
            isinstance(event, Message)
            and event.chat.type in SUPPORTED_CHAT_TYPES
            and (event.text or event.caption)
            and await handle_blacklist(event)
        ):
            return None
        return await handler(event, data)


class QuietAdminMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if (
            isinstance(event, Message)
            and event.chat.type in SUPPORTED_CHAT_TYPES
            and event.from_user
            and db.get_active_quiet_admin(
                event.chat.id,
                event.from_user.id,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
        ):
            await delete_message_now_or_later(event)
            return None
        return await handler(event, data)


class ChatLockMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if not (
            isinstance(event, Message)
            and event.chat.type in SUPPORTED_CHAT_TYPES
            and event.from_user
            and not event.from_user.is_bot
            and cached_chat_lock(event.chat.id)
        ):
            return await handler(event, data)

        if await actor_moderation_role(event.bot, event.chat.id, event.from_user.id) is not None:
            return await handler(event, data)

        await delete_message_now_or_later(event)
        return None


class AlarmRestrictedMessageMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if (
            isinstance(event, Message)
            and event.chat.type in SUPPORTED_CHAT_TYPES
            and is_alarm_restricted_message(event)
            and await delete_alarm_restricted_message(event)
        ):
            return None
        return await handler(event, data)


class StaleCallbackQueryMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        try:
            return await handler(event, data)
        except TelegramBadRequest as exc:
            if isinstance(event, CallbackQuery) and callback_query_is_stale(exc):
                return None
            raise


class AuditCallbackMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        result = await handler(event, data)
        if not isinstance(event, CallbackQuery) or not event.from_user or not event.data:
            return result
        prefixes = (
            "act:", "alarm:", "quiet:", "giveaway:", "blacklist:", "quotes:",
            "access:", "leave:", "restart:",
        )
        if not event.data.startswith(prefixes) or event.data.startswith("act:logs:"):
            return result
        chat_match = re.search(r":(-100\d+)", event.data)
        chat_id = int(chat_match.group(1)) if chat_match else None
        db.add_audit_log(
            "Telegram-бот",
            "Нажал административную кнопку",
            chat_id=chat_id,
            actor_id=event.from_user.id,
            actor_username=event.from_user.username,
            actor_name=event.from_user.full_name,
            details=event.data,
        )
        return result


class AuditAdminStateMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        state = data.get("state")
        state_name = await state.get_state() if state and isinstance(event, Message) and event.chat.type == "private" else None
        state_data = await state.get_data() if state_name else {}
        result = await handler(event, data)
        if state_name and event.from_user:
            db.add_audit_log(
                "Telegram-бот",
                "Завершил административное действие",
                chat_id=state_data.get("chat_id"),
                actor_id=event.from_user.id,
                actor_username=event.from_user.username,
                actor_name=event.from_user.full_name,
                details=state_name,
            )
        return result


class AdminInput(StatesGroup):
    set_reply = State()
    set_reply_media = State()
    del_reply = State()
    set_trigger = State()
    set_trigger_media = State()
    del_trigger = State()
    send_message = State()
    set_giveaway = State()
    add_birthday = State()
    set_alarm_text = State()
    set_clear_text = State()
    paid_message = State()
    feedback = State()
    set_roll_mute = State()
    set_quiet_text = State()
    set_quiet_media = State()
    set_quiet_manual = State()
    feedback_reply = State()
    add_blacklist_word = State()
    delete_blacklist_word = State()
    delete_quote = State()
    set_access_user = State()
    set_moderator_user = State()
    remove_moderator_user = State()
    gift_recipient = State()


class MediaInput(StatesGroup):
    waiting_file = State()


def chat_title(chat: Chat) -> str:
    return chat.title or chat.full_name or chat.username or str(chat.id)


def extract_mentions(text: str | None) -> set[str]:
    if not text:
        return set()
    return {normalize_username(match.group(1)) for match in MENTION_RE.finditer(text)}


def has_trigger(text: str, trigger: str) -> bool:
    normalized_text = normalize_trigger(text)
    normalized_trigger = normalize_trigger(trigger)
    return has_normalized_trigger(normalized_text, normalized_trigger)


def has_normalized_trigger(normalized_text: str, normalized_trigger: str) -> bool:
    if not normalized_text or not normalized_trigger:
        return False

    pattern = rf"(?<!\w){re.escape(normalized_trigger)}(?!\w)"
    return re.search(pattern, normalized_text, flags=re.IGNORECASE) is not None


def trigger_item_matches(normalized_text: str, item) -> bool:
    candidates = [getattr(item, "trigger", "")]
    candidates.extend(getattr(item, "aliases", ()) or ())
    return any(has_normalized_trigger(normalized_text, normalize_trigger(candidate)) for candidate in candidates)


def auto_trigger_message_key(message: Message) -> tuple[int, int] | None:
    message_id = getattr(message, "message_id", None)
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)
    if message_id is None or chat_id is None:
        return None
    return int(chat_id), int(message_id)


def auto_trigger_was_sent(message: Message) -> bool:
    key = auto_trigger_message_key(message)
    if key is None:
        return False
    now = time.monotonic()
    stale_keys = [
        cached_key
        for cached_key, created_at in AUTO_TRIGGER_SENT_MESSAGES.items()
        if now - created_at > AUTO_TRIGGER_SENT_CACHE_SECONDS
    ]
    for stale_key in stale_keys:
        AUTO_TRIGGER_SENT_MESSAGES.pop(stale_key, None)
    return key in AUTO_TRIGGER_SENT_MESSAGES


def mark_auto_trigger_sent(message: Message) -> None:
    key = auto_trigger_message_key(message)
    if key is not None:
        AUTO_TRIGGER_SENT_MESSAGES[key] = time.monotonic()


def matching_trigger_answer(message: Message):
    text = message.text or message.caption
    if not text:
        return None
    normalized_text = normalize_trigger(text)
    trigger_answers = [
        item
        for item in cached_triggers(message.chat.id)
        if trigger_item_matches(normalized_text, item)
    ]
    return random.choice(trigger_answers) if trigger_answers else None


async def send_matching_trigger_after_command(message: Message) -> bool:
    if message.chat.type not in SUPPORTED_CHAT_TYPES or auto_trigger_was_sent(message):
        return False
    item = matching_trigger_answer(message)
    if not item:
        return False
    await send_auto_reply_item(message, item)
    mark_auto_trigger_sent(message)
    return True


def split_command_payload(text: str | None) -> str:
    if not text:
        return ""
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def cleanup_gift_flows(now: float | None = None) -> None:
    moment = time.monotonic() if now is None else now
    stale_tokens = [
        token
        for token, flow in GIFT_SELECTIONS.items()
        if moment - flow.created_at > GIFT_FLOW_TTL_SECONDS
    ]
    for token in stale_tokens:
        GIFT_SELECTIONS.pop(token, None)
        GIFT_CONFIRM_IN_PROGRESS.discard(token)
        GIFT_COMPLETED.pop(token, None)
    stale_completed = [
        token
        for token, completed_at in GIFT_COMPLETED.items()
        if moment - completed_at > GIFT_FLOW_TTL_SECONDS
    ]
    for token in stale_completed:
        GIFT_COMPLETED.pop(token, None)


def star_amount_text(balance: StarAmount | None) -> str:
    if balance is None:
        return "не удалось получить"
    amount = int(getattr(balance, "amount", 0) or 0)
    nanostar_amount = getattr(balance, "nanostar_amount", None)
    extra = f" + {nanostar_amount} nanostars" if nanostar_amount else ""
    return f"{amount} ⭐{extra}"


async def bot_star_balance(bot: Bot) -> StarAmount | None:
    try:
        return await bot.get_my_star_balance()
    except (TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter):
        return None


def gift_summary(gift: Gift) -> GiftSummary:
    emoji = getattr(getattr(gift, "sticker", None), "emoji", None) or "🎁"
    sticker_file_id = getattr(getattr(gift, "sticker", None), "file_id", None)
    title_parts = [emoji, f"{gift.star_count} ⭐"]
    if gift.remaining_count is not None:
        title_parts.append(f"ост. {gift.remaining_count}")
    if gift.is_premium:
        title_parts.append("Premium")
    return GiftSummary(
        gift_id=gift.id,
        star_count=int(gift.star_count),
        emoji=emoji,
        title=" · ".join(title_parts),
        sticker_file_id=sticker_file_id,
        remaining_count=gift.remaining_count,
        total_count=gift.total_count,
        upgrade_star_count=gift.upgrade_star_count,
        is_premium=bool(gift.is_premium),
    )


def gift_by_id(flow: GiftFlow, gift_id: str | None = None) -> GiftSummary | None:
    selected = gift_id or flow.selected_gift_id
    if not selected:
        return None
    return next((gift for gift in flow.gifts if gift.gift_id == selected), None)


def gift_recipient_label(user_id: int, username: str | None = None, full_name: str | None = None) -> str:
    if username:
        return f"@{username} / {user_id}"
    if full_name:
        return f"{full_name} / {user_id}"
    return str(user_id)


def gift_flow_expired(flow: GiftFlow) -> bool:
    return time.monotonic() - flow.created_at > GIFT_FLOW_TTL_SECONDS


def gift_flow_markup(flow: GiftFlow, page: int = 0) -> InlineKeyboardMarkup:
    total_pages = max(1, math.ceil(len(flow.gifts) / GIFT_PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))
    offset = page * GIFT_PAGE_SIZE
    rows: list[list[InlineKeyboardButton]] = []
    for index, gift in enumerate(flow.gifts[offset : offset + GIFT_PAGE_SIZE], start=offset):
        rows.append([
            InlineKeyboardButton(
                text=gift.title,
                callback_data=f"gift:pick:{flow.token}:{index}",
            )
        ])
    if total_pages > 1:
        rows.append([
            InlineKeyboardButton(text="←", callback_data=f"gift:list:{flow.token}:{max(0, page - 1)}"),
            InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data=f"gift:list:{flow.token}:{page}"),
            InlineKeyboardButton(text="→", callback_data=f"gift:list:{flow.token}:{min(total_pages - 1, page + 1)}"),
        ])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data=f"gift:cancel:{flow.token}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def gift_confirm_markup(flow: GiftFlow) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Отправить", callback_data=f"gift:send:{flow.token}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data=f"gift:cancel:{flow.token}"),
            ],
        ]
    )


def gift_list_text(flow: GiftFlow, balance: StarAmount | None = None) -> str:
    lines = [
        "<b>Telegram Gifts за Stars</b>",
        f"Баланс бота: <b>{escape(star_amount_text(balance))}</b>",
        "",
        "Выбери подарок. Цена указана в Stars.",
    ]
    if flow.recipient_label:
        lines.append(f"Получатель уже выбран: <b>{escape(flow.recipient_label)}</b>")
    lines.append("")
    lines.extend(
        f"• {escape(gift.title)} · <code>{escape(gift.gift_id)}</code>"
        for gift in flow.gifts[:10]
    )
    if len(flow.gifts) > 10:
        lines.append(f"…и ещё {len(flow.gifts) - 10}")
    return "\n".join(lines)


def gift_confirm_text(flow: GiftFlow, balance: StarAmount | None = None) -> str:
    gift = gift_by_id(flow)
    if gift is None:
        return "Подарок не найден. Начни заново: /gift"
    return "\n".join(
        [
            "<b>Подтверждение Telegram Gift</b>",
            "",
            f"🎁 Подарок: <b>{escape(gift.emoji)}</b> <code>{escape(gift.gift_id)}</code>",
            f"⭐ Стоимость: <b>{gift.star_count}</b>",
            f"👤 Получатель: <b>{escape(flow.recipient_label or str(flow.recipient_id or 'не выбран'))}</b>",
            f"💰 Баланс бота: <b>{escape(star_amount_text(balance))}</b>",
            "",
            "Stars будут списаны с баланса Telegram-бота только после нажатия «Отправить».",
        ]
    )


def gift_done_text(flow: GiftFlow, balance: StarAmount | None = None) -> str:
    gift = gift_by_id(flow)
    gift_title = f"{gift.emoji} <code>{escape(gift.gift_id)}</code>" if gift else "подарок"
    return "\n".join(
        [
            "<b>Подарок отправлен</b>",
            "",
            f"🎁 Подарок: {gift_title}",
            f"👤 Получатель: <b>{escape(flow.recipient_label or str(flow.recipient_id or '-'))}</b>",
            f"💰 Баланс после операции: <b>{escape(star_amount_text(balance))}</b>",
        ]
    )


async def get_gift_flow_from_callback(callback: CallbackQuery, token: str) -> GiftFlow | None:
    cleanup_gift_flows()
    flow = GIFT_SELECTIONS.get(token)
    if flow is None:
        await callback.answer("Операция устарела. Запусти /gift заново.", show_alert=True)
        return None
    if gift_flow_expired(flow):
        GIFT_SELECTIONS.pop(token, None)
        GIFT_CONFIRM_IN_PROGRESS.discard(token)
        GIFT_COMPLETED.pop(token, None)
        await callback.answer("Операция устарела. Запусти /gift заново.", show_alert=True)
        return None
    if flow.admin_id != callback.from_user.id:
        await callback.answer("Эта операция принадлежит другому администратору.", show_alert=True)
        return None
    if not is_bot_admin(callback.from_user.id):
        await callback.answer("Подарки доступны только администраторам бота.", show_alert=True)
        return None
    return flow


async def resolve_gift_recipient_from_message(message: Message, payload: str = "") -> tuple[int | None, str | None, str | None]:
    target = payload.strip()
    if target:
        if not target.isdigit():
            return None, None, "Укажи numeric Telegram user_id. Также можно вызвать /gift ответом на сообщение пользователя."
        user_id = int(target)
        return user_id, gift_recipient_label(user_id), None
    if message.reply_to_message and message.reply_to_message.from_user:
        user = message.reply_to_message.from_user
        return user.id, gift_recipient_label(user.id, user.username, user.full_name), None
    return None, None, None


async def start_gift_flow(message: Message, state: FSMContext, payload: str = "", actor: User | None = None) -> None:
    admin = actor or message.from_user
    if not admin or not is_bot_admin(admin.id):
        await message.answer("Команда /gift доступна только администраторам бота.")
        return
    await state.clear()
    cleanup_gift_flows()
    recipient_id, recipient_label, recipient_error = await resolve_gift_recipient_from_message(message, payload)
    if recipient_error:
        await message.answer(recipient_error)
        return
    try:
        available = await message.bot.get_available_gifts()
    except (TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter) as exc:
        await message.answer(f"Не получилось получить список Telegram Gifts.\n<code>{escape(str(exc))}</code>")
        return
    gifts = [gift_summary(gift) for gift in getattr(available, "gifts", [])]
    gifts = [gift for gift in gifts if gift.remaining_count is None or gift.remaining_count > 0]
    gifts.sort(key=lambda item: (item.star_count, item.gift_id))
    if not gifts:
        await message.answer("Сейчас нет доступных Telegram Gifts.")
        return
    token = secrets.token_urlsafe(8)
    flow = GiftFlow(
        token=token,
        admin_id=admin.id,
        created_at=time.monotonic(),
        gifts=gifts,
        recipient_id=recipient_id,
        recipient_label=recipient_label,
    )
    GIFT_SELECTIONS[token] = flow
    balance = await bot_star_balance(message.bot)
    await message.answer(gift_list_text(flow, balance), reply_markup=gift_flow_markup(flow))


def message_html_text(message: Message) -> str:
    return (message.html_text or message.text or "").strip()


def message_html_content(message: Message) -> str:
    return (message.html_text or getattr(message, "html_caption", None) or message.text or message.caption or "").strip()


def strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value)


def callback_query_is_stale(exc: TelegramBadRequest) -> bool:
    message = str(exc).casefold()
    return "query is too old" in message or "response timeout expired" in message or "query id is invalid" in message


def message_edit_target_is_missing(exc: TelegramBadRequest) -> bool:
    message = str(exc).casefold()
    return (
        "message to edit not found" in message
        or "message can't be edited" in message
        or "message identifier is not specified" in message
    )


def preview_html(value: str, limit: int = 140) -> str:
    preview = value.replace("\n", " ").strip()
    if len(preview) <= limit:
        return preview

    plain = unescape(strip_html(preview))
    if len(plain) > limit:
        plain = plain[: limit - 3] + "..."
    return escape(plain)


def split_text_command(text: str | None) -> tuple[str, str]:
    if not text:
        return "", ""
    parts = text.strip().split(maxsplit=1)
    command = parts[0].casefold()
    payload = parts[1].strip() if len(parts) > 1 else ""
    return command, payload


def donate_start_payload(chat_id: int) -> str:
    return f"donate_{'n' if chat_id < 0 else 'p'}{abs(chat_id)}"


def parse_donate_start_payload(text: str | None) -> int | None:
    if not text:
        return None
    parts = text.strip().split(maxsplit=1)
    if len(parts) != 2:
        return None
    match = re.fullmatch(r"donate_([np])(\d+)", parts[1])
    if not match:
        return None
    chat_id = int(match.group(2))
    return -chat_id if match.group(1) == "n" else chat_id


def parse_app_login_start_payload(text: str | None) -> str | None:
    if not text:
        return None
    parts = text.strip().split(maxsplit=1)
    if len(parts) != 2:
        return None
    match = re.fullmatch(r"app_([A-Za-z0-9_-]+)", parts[1])
    return match.group(1) if match else None


def parse_user_subscription_payload(payload: str) -> int | None:
    match = re.fullmatch(r"user_subscription:(\d+):[0-9a-f]+", payload)
    return int(match.group(1)) if match else None


def premium_payment_payload(plan: str, user_id: int) -> str:
    return f"premium_plan:{plan}:{user_id}:{secrets.token_hex(8)}"


def parse_premium_payment_payload(payload: str) -> tuple[str, int] | None:
    match = re.fullmatch(r"premium_plan:(basic|extended):(\d+):[0-9a-f]+", payload)
    return (match.group(1), int(match.group(2))) if match else None


def user_subscription_stars() -> int:
    try:
        return max(1, int(os.getenv("USER_SUBSCRIPTION_STARS", "100")))
    except ValueError:
        return 100


def split_trigger_payload(payload: str) -> tuple[str, str]:
    match = re.match(r"^\s*(.+?)\s+(?:-|–|—)\s*(.*?)\s*$", payload, flags=re.DOTALL)
    if match:
        return match.group(1).strip(), match.group(2).strip()

    parts = re.split(r"\s*[–—]\s*", payload, maxsplit=1)
    if len(parts) == 1 and payload.count("-") == 1:
        parts = payload.split("-", maxsplit=1)
    if len(parts) != 2:
        return "", ""
    return parts[0].strip(), parts[1].strip()


def split_reply_payload(payload: str) -> tuple[str, str]:
    username, reply_text = split_trigger_payload(payload)
    if username:
        return username, reply_text

    username, sep, reply_text = payload.partition(" ")
    if not sep:
        return "", ""
    return username.strip(), reply_text.strip()


def split_giveaway_payload(payload: str) -> tuple[str, int, str]:
    parts = [part.strip() for part in payload.split(" - ", maxsplit=2)]
    if len(parts) != 3:
        return "", 0, ""

    trigger, count_text, title = parts
    if not trigger or not title:
        return "", 0, ""

    try:
        count = int(count_text)
    except ValueError:
        return "", 0, ""

    return trigger, max(1, min(20, count)), title


def is_day_query(text: str | None) -> bool:
    if not text:
        return False
    return normalize_trigger(text).strip(" ?!.") == DAY_QUERY_TEXT


def parse_weather_request(text: str | None) -> tuple[str, str] | None:
    if not text:
        return None
    match = WEATHER_RE.match(text.strip())
    if not match:
        return None
    payload = " ".join(match.group(1).split())
    normalized = payload.casefold()
    period = "now"

    suffixes = [
        (" на завтра", "tomorrow"),
        (" завтра", "tomorrow"),
        (" на неделю", "week"),
        (" неделю", "week"),
        (" на 7 дней", "week"),
        (" 7 дней", "week"),
    ]
    for suffix, value in suffixes:
        if normalized.endswith(suffix):
            city = payload[: -len(suffix)].strip()
            return (city, value) if city else None

    return (payload, period) if payload else None


def parse_birthday_payload(text: str | None) -> tuple[int, int, str] | None:
    payload = split_command_payload(text).strip()
    match = re.match(r"^(\d{1,2})[./-](\d{1,2})\s+(.+)$", payload)
    if not match:
        return None
    day = int(match.group(1))
    month = int(match.group(2))
    label = match.group(3).strip()
    if not 1 <= day <= 31 or not 1 <= month <= 12 or not label:
        return None
    return day, month, label


def parse_poll_payload(text: str | None) -> tuple[str, list[str]] | None:
    payload = split_command_payload(text).strip()
    parts = [part.strip() for part in payload.split("|") if part.strip()]
    if len(parts) < 3:
        return None
    question = parts[0]
    options = parts[1:11]
    if not question or any(len(option) > 100 for option in options):
        return None
    return question, options


def parse_roll_mute_payload(text: str | None) -> tuple[int, int] | None:
    if not text:
        return None
    parts = text.strip().split()
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        return None
    mute_minutes = int(parts[0])
    cooldown_minutes = int(parts[1])
    if mute_minutes < 1 or cooldown_minutes < 0:
        return None
    return mute_minutes, cooldown_minutes


def parse_super_mute_payload(text: str | None) -> tuple[str | None, str] | None:
    if not text:
        return None
    parts = text.strip().split(maxsplit=2)
    if not parts:
        return None
    command = parts[0].casefold().lstrip("/")
    if command == "супермут":
        username = None
        rest = parts[1] if len(parts) > 1 else ""
        if rest.startswith("@"):
            username = normalize_username(rest)
            rest = parts[2] if len(parts) > 2 else ""
        return username, rest.strip().lstrip("-").strip()
    if parts[0].startswith("@") and len(parts) >= 2 and parts[1].casefold().lstrip("/") == "супермут":
        return normalize_username(parts[0]), (parts[2] if len(parts) > 2 else "").strip().lstrip("-").strip()
    return None


def normalize_dig_tag(text: str | None) -> str:
    tag = re.sub(r"\s+", " ", (text or "").strip())
    if len(tag) > 16:
        tag = tag[:16].rstrip()
    return tag


def parse_quiet_payload(text: str | None) -> tuple[str | None, int | None, str]:
    if not text:
        return None, None, ""
    parts = text.strip().split(maxsplit=2)
    username = None
    if parts and parts[0].startswith("@"):
        if len(parts) < 3:
            return normalize_username(parts[0]), None, ""
        username = normalize_username(parts[0])
        command = parts[1]
        rest = parts[2]
    else:
        command = parts[0] if parts else ""
        rest = parts[1] if len(parts) > 1 else ""

    if command.casefold() != "затихни":
        return username, None, ""

    minutes_text, _, reason = rest.partition(" - ")
    if not minutes_text.strip().isdigit():
        return username, None, reason.strip()
    return username, int(minutes_text.strip()), reason.strip()


def parse_dictionary_hit_payload(text: str | None) -> str | None:
    if not text:
        return ""
    match = re.fullmatch(
        r"(?:(@[A-Za-z0-9_]{5,32})\s+)?ударить\s+словар[её]м",
        text.strip(),
        re.IGNORECASE,
    )
    if not match:
        return ""
    return normalize_username(match.group(1)) if match.group(1) else None


def parse_unquiet_payload(text: str | None) -> str | None:
    if not text:
        return None
    parts = text.strip().split()
    if len(parts) == 1 and parts[0].casefold() == "трещи":
        return None
    if len(parts) == 2 and parts[0].startswith("@") and parts[1].casefold() == "трещи":
        return normalize_username(parts[0])
    return ""


def parse_quiet_admin_payload(text: str | None) -> tuple[str | None, int, str] | None:
    if not text:
        return None
    match = re.fullmatch(
        r"(?:(@[A-Za-z0-9_]{5,32})\s+)?затихни\s+админ(?:\s+(\d+))?(?:\s+-\s*(.*))?",
        text.strip(),
        re.IGNORECASE,
    )
    if not match:
        return None
    username = normalize_username(match.group(1)) if match.group(1) else None
    minutes = int(match.group(2)) if match.group(2) else 60
    reason = (match.group(3) or "").strip()
    return username, max(1, min(10080, minutes)), reason


def moderator_role_title(role: str | None, *, short: bool = False) -> str:
    spec = MODERATOR_ROLE_SPECS.get(role or "")
    if not spec:
        return "Без должности"
    key = "short" if short else "title"
    return str(spec[key])


def moderator_role_rank(role: str | None) -> int:
    if role == "admin":
        return 99
    spec = MODERATOR_ROLE_SPECS.get(role or "")
    return int(spec["rank"]) if spec else 0


def moderator_max_mute_minutes(role: str | None) -> int:
    spec = MODERATOR_ROLE_SPECS.get(role or "")
    return int(spec["max_mute_minutes"]) if spec else 0


def moderator_can_delete_messages(role: str | None) -> bool:
    return moderator_role_rank(role) >= moderator_role_rank("moderator")


def moderator_chat_lock_limit_seconds(role: str | None) -> int | None:
    if role == "admin":
        return None
    if role == "moderator":
        return 10 * 60
    if role == "senior":
        return 30 * 60
    return 0


def moderator_can_stop_chat(role: str | None, seconds: int | None) -> bool:
    limit = moderator_chat_lock_limit_seconds(role)
    if limit is None:
        return True
    if limit <= 0:
        return False
    return seconds is not None and 1 <= seconds <= limit


def moderator_can_unmute(actor_role: str | None, actor_id: int, active_mute: dict | None) -> bool:
    if actor_role == "admin" or moderator_role_rank(actor_role) >= moderator_role_rank("senior"):
        return True
    if not active_mute:
        return False
    return int(active_mute["moderator_id"]) == actor_id


def is_miniapp_admin_user(user_id: int | None) -> bool:
    if user_id is None:
        return False
    role = db.get_miniapp_profile_role(int(user_id))
    return bool(role and role.label == MINIAPP_ADMIN_PROFILE_LABEL)


def parse_moderator_duration(payload: str) -> tuple[str, str | None]:
    text = payload.strip()
    if not text:
        return "", None

    parts = text.split()
    if len(parts) >= 1:
        compact_unit = parts[-1].casefold().rstrip(".")
        unit_days = {
            "день": 1,
            "сутки": 1,
            "неделя": 7,
            "месяц": 30,
        }
        if compact_unit in unit_days:
            name = " ".join(parts[:-1]).strip()
            expires_at = datetime.now(timezone.utc) + timedelta(days=unit_days[compact_unit])
            return name, expires_at.isoformat(timespec="seconds")
    if len(parts) < 2:
        return text, None

    amount_text = parts[-2]
    unit = parts[-1].casefold().rstrip(".")
    if not amount_text.isdigit():
        compact = parts[-1].casefold()
        match = re.fullmatch(r"(\d+)([дd]|дн|день|дня|дней|н|нед|неделя|недели|мес|месяц|месяца|месяцев)", compact)
        if not match:
            return text, None
        amount = int(match.group(1))
        unit = match.group(2)
        name = " ".join(parts[:-1]).strip()
    else:
        amount = int(amount_text)
        name = " ".join(parts[:-2]).strip()

    if amount < 1:
        return text, None
    if unit in {"д", "d", "дн", "день", "дня", "дней"}:
        expires_at = datetime.now(timezone.utc) + timedelta(days=amount)
    elif unit in {"н", "нед", "неделя", "недели"}:
        expires_at = datetime.now(timezone.utc) + timedelta(weeks=amount)
    elif unit in {"мес", "месяц", "месяца", "месяцев"}:
        expires_at = datetime.now(timezone.utc) + timedelta(days=30 * amount)
    else:
        return text, None
    return name.strip(), expires_at.isoformat(timespec="seconds")


def parse_moderator_role_payload(text: str | None, commands: dict[str, str]) -> tuple[str | None, str | None, str]:
    command, payload = split_text_command(text)
    role = commands.get(command)
    if not role:
        return None, None, ""
    username = None
    if payload.startswith("@"):
        first, _, rest = payload.partition(" ")
        username = normalize_username(first)
        payload = rest.strip()
    return role, username, payload


def parse_private_moderator_role_payload(text: str | None, commands: dict[str, str]) -> tuple[str | None, str | None, int | None, str]:
    role, username, payload = parse_moderator_role_payload(text, commands)
    if not role:
        return None, None, None, ""

    chat_id = None
    kept_parts: list[str] = []
    for part in payload.split():
        if chat_id is None and re.fullmatch(r"-?\d{5,}", part):
            chat_id = int(part)
            continue
        if username is None and part.startswith("@"):
            username = normalize_username(part)
            continue
        kept_parts.append(part)
    return role, username, chat_id, " ".join(kept_parts).strip()


def parse_warn_payload(text: str | None) -> tuple[str | None, str] | None:
    command, payload = split_text_command(text)
    if command != "косяк":
        return None
    username = None
    if payload.startswith("@"):
        first, _, rest = payload.partition(" ")
        username = normalize_username(first)
        payload = rest.strip()
    return username, payload


def parse_moderator_vote_payload(text: str | None) -> str | None:
    command, payload = split_text_command(text)
    if command != "голос" or not payload.startswith("@"):
        return None
    return normalize_username(payload.split(maxsplit=1)[0])


def parse_duration_seconds_token(token: str) -> int | None:
    value = token.strip().casefold().rstrip(".")
    match = re.fullmatch(r"(\d+)\s*(с|s|сек|секунд|м|m|мин|минут|ч|h|час|часов)", value)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    if amount < 0:
        return None
    if unit in {"с", "s", "сек", "секунд"}:
        return amount
    if unit in {"м", "m", "мин", "минут"}:
        return amount * 60
    return amount * 3600


def parse_chat_stop_payload(text: str | None) -> tuple[int | None, str] | None:
    command, payload = split_text_command(text)
    if command != "чат" or not payload.casefold().startswith("стоп"):
        return None
    rest = payload[4:].strip()
    if not rest:
        return None, ""
    first, _, tail = rest.partition(" ")
    seconds = parse_duration_seconds_token(first)
    if seconds is None:
        return None, rest
    return max(1, seconds), tail.strip()


def parse_slow_mode_payload(text: str | None) -> int | None:
    command, payload = split_text_command(text)
    if command != "медленно":
        return None
    value = payload.strip().casefold()
    if value in {"выкл", "выключить", "off", "0", "0с"}:
        return 0
    seconds = parse_duration_seconds_token(value)
    if seconds is None:
        return None
    return max(0, min(3600, seconds))


def parse_quiet_manual_payload(text: str | None) -> tuple[str | None, int | None, str]:
    if not text:
        return None, None, ""
    parts = text.strip().split(maxsplit=2)
    if len(parts) < 2 or not parts[1].isdigit():
        return None, None, ""
    reason = ""
    if len(parts) == 3:
        reason = parts[2].strip()
        if reason.startswith("-"):
            reason = reason[1:].strip()
    return parts[0].strip(), int(parts[1]), reason


def refreshed_dig_luck(user_id: int, luck: int, last_luck_at: str, now: datetime) -> int:
    try:
        last = datetime.fromisoformat(last_luck_at)
    except ValueError:
        return max(0, min(100, luck))
    elapsed = max(0, (now - last).total_seconds())
    items = dig_items_map(0, user_id)
    multiplier = float(get_premium_service().get_mine_bonuses(user_id)["luck_regen_multiplier"])
    hourly_regen = DIG_LUCK_REGEN_PER_HOUR + dig_rank_bonuses(items)["luck_regen"]
    restored = int((elapsed / 3600) * hourly_regen * multiplier)
    return max(0, min(100, luck + restored))


def dig_coin_reward(depth: int) -> int:
    low, high = DIG_REWARDS.get(max(0, min(10, depth)), (1, 5))
    return low + secrets.randbelow(high - low + 1)


def scale_auto_dig_reward(coins: int) -> int:
    return max(1, (max(0, int(coins)) * AUTO_DIG_REWARD_SCALE_PERCENT + 99) // 100)


def dig_random_event(depth: int, coins: int) -> tuple[int, str | None]:
    if secrets.randbelow(100) >= 55:
        return coins, None

    depth = max(0, min(10, depth))
    event = secrets.randbelow(100)
    if event < 4:
        return coins, "Событие: копал, нашёл в пещере бутылку, пошёл за ней — нашёл Богдана в говно."
    if event < 25:
        bonus = 4 + depth * 2 + secrets.randbelow(7)
        return coins + bonus, f"Событие: нашлась старая монета. Коллекционер купил ее за <b>{bonus}</b> котоинов."
    if event < 42:
        bonus = 2 + depth + secrets.randbelow(5)
        return coins + bonus, f"Событие: в земле блеснул забытый кошелек. Внутри было <b>{bonus}</b> котоинов."
    if event < 62:
        loss = min(coins, 1 + secrets.randbelow(max(1, 3 + depth)))
        return coins - loss, f"Событие: камень упал на ногу. На перевязку ушло <b>{loss}</b> котоинов."
    if event < 78:
        loss = min(coins, 1 + secrets.randbelow(max(1, 2 + depth)))
        return coins - loss, f"Событие: погнулась ручка кирки. Мелкий ремонт обошелся в <b>{loss}</b> котоинов."
    if event < 90:
        return coins, "Событие: за стеной послышался глухой стук. Ты решил не проверять."
    return coins, "Событие: попалась старая табличка с надписью «Не копать». Разумеется, ты копнул рядом."


def find_golden_ticket(depth: int) -> bool:
    """The deeper the completed run, the better the chance to find one ticket."""
    depth = max(0, min(10, int(depth)))
    chance = min(DIG_GOLDEN_TICKET_MAX_CHANCE, depth * 5)
    return depth > 0 and secrets.randbelow(100) < chance


def dig_player_name(username: str | None, full_name: str) -> str:
    return f"@{username}" if username else full_name


def profile_link(user_id: int, username: str | None, full_name: str, suffix: str = "") -> str:
    label = f"@{username}" if username else full_name
    href = f"tg://openmessage?user_id={user_id}"
    return f'<a href="{href}">{escape(label)}</a>{escape(suffix)}'


async def current_profile_link(
    bot: Bot,
    chat_id: int,
    user_id: int,
    username: str | None,
    full_name: str,
    suffix: str = "",
) -> str:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        return profile_link(user_id, username, full_name, suffix)
    return profile_link(user_id, member.user.username, member.user.full_name, suffix)


async def get_active_chat_member(bot: Bot, chat_id: int, user_id: int):
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        return None
    status = member_status_text(member.status)
    if status not in ACTIVE_MEMBER_STATUS_TEXTS:
        return None
    if status == "restricted" and getattr(member, "is_member", True) is False:
        return None
    if member.user.is_bot:
        return None
    return member


def is_deleted_or_empty_user(user: User) -> bool:
    if getattr(user, "is_deleted", False):
        return True
    first_name = (getattr(user, "first_name", None) or "").strip()
    last_name = (getattr(user, "last_name", None) or "").strip()
    full_name = (getattr(user, "full_name", None) or "").strip()
    username = (getattr(user, "username", None) or "").strip()
    normalized_name = " ".join(part for part in (first_name, last_name) if part).casefold()
    normalized_full = full_name.casefold()
    deleted_names = {"deleted account", "удаленный аккаунт", "удалённый аккаунт"}
    if normalized_name in deleted_names or normalized_full in deleted_names:
        return True
    return not username and not first_name and not last_name


def active_mute_remaining_text(member, now: datetime | None = None) -> str | None:
    if getattr(member, "can_send_messages", True) is not False:
        return None
    until_date = getattr(member, "until_date", None)
    if not until_date:
        return "бессрочно"
    if isinstance(until_date, datetime):
        until = until_date
    else:
        try:
            until = datetime.fromtimestamp(int(until_date), timezone.utc)
        except (TypeError, ValueError, OSError):
            return None
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    if until <= now:
        return None
    minutes = max(1, math.ceil((until - now).total_seconds() / 60))
    days, rem = divmod(minutes, 60 * 24)
    hours, mins = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days} д")
    if hours:
        parts.append(f"{hours} ч")
    if mins or not parts:
        parts.append(f"{mins} мин")
    return " ".join(parts[:2])


async def is_valid_giveaway_user(bot: Bot, chat_id: int, user_id: int) -> bool:
    member = await get_active_chat_member(bot, chat_id, user_id)
    if member is None:
        return False
    if is_deleted_or_empty_user(member.user):
        return False
    return True


async def is_valid_roll_mute_target(bot: Bot, chat_id: int, user_id: int) -> bool:
    member = await get_active_chat_member(bot, chat_id, user_id)
    if member is None:
        return False
    if is_deleted_or_empty_user(member.user):
        return False
    status = member_status_text(member.status)
    return member.status not in ADMIN_STATUSES and status not in ADMIN_STATUS_TEXTS


async def current_roll_mute_target_member(bot: Bot, chat_id: int, user_id: int):
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        return None

    user = member.user
    status = member_status_text(member.status)
    inactive = status not in ACTIVE_MEMBER_STATUS_TEXTS or (status == "restricted" and getattr(member, "is_member", True) is False)
    if inactive or user.is_bot or is_deleted_or_empty_user(user):
        db.upsert_seen_user(
            chat_id=chat_id,
            user_id=user.id,
            username=None,
            full_name=user.full_name or str(user.id),
            is_bot=user.is_bot,
        )
        return None

    db.upsert_seen_user(
        chat_id=chat_id,
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        is_bot=user.is_bot,
    )
    if member.status in ADMIN_STATUSES or status in ADMIN_STATUS_TEXTS:
        return None
    return member


def dig_items_map(chat_id: int, user_id: int) -> dict[str, int]:
    return {item.item_key: item.quantity for item in db.list_dig_items(chat_id, user_id)}


def remember_repair_candidate(snapshot: dict, item_key: str) -> None:
    if not item_key or item_key == "repair_kit":
        return
    candidates = list(snapshot.get("repair_candidates") or [])
    candidates.append(item_key)
    snapshot["repair_candidates"] = candidates


def repair_candidates_from_snapshot(snapshot: dict) -> list[str]:
    candidates = [str(item) for item in (snapshot.get("repair_candidates") or []) if item and item != "repair_kit"]
    if candidates:
        return candidates
    legacy = list(snapshot.get("used_tools") or [])
    for key in ("bucket", "flashlight", "map", "compass", "scanner", "talisman", "mystery_chest", "helmet", "shovel"):
        if snapshot.get(key) or snapshot.get(f"{key}_used"):
            legacy.append(key)
    if snapshot.get("chest") or snapshot.get("chest_used"):
        legacy.append("mystery_chest")
    return [str(item) for item in legacy if item and item != "repair_kit"]


def apply_interactive_repair_kit(chat_id: int, user_id: int, snapshot: dict, used_effects: list[str]) -> bool:
    candidates = repair_candidates_from_snapshot(snapshot)
    if not candidates:
        return False
    restored = candidates[-1]
    if not snapshot.pop("repair_used", False) and not db.consume_dig_item(chat_id, user_id, "repair_kit"):
        return False
    db.add_dig_item(chat_id, user_id, restored, 1)
    used_effects.append(f"Ремонтный набор восстановил: {DIG_SHOP_ITEMS.get(restored, (restored,))[0]}")
    return True


def use_interactive_medkit(
    chat_id: int,
    user_id: int,
    snapshot: dict,
    used_effects: list[str],
    text: str,
) -> bool:
    if not db.consume_dig_item(chat_id, user_id, "medkit"):
        return False
    remember_repair_candidate(snapshot, "medkit")
    used_effects.append(text)
    return True


def dig_rank_name(items: dict[str, int]) -> str:
    for key, name in DIG_RANKS:
        if items.get(key, 0) > 0:
            return name
    return "Новичок"


def dig_rank_bonuses(items: dict[str, int]) -> dict[str, int]:
    """Returns only the highest owned rank's bonuses; ranks never stack."""
    for key, _ in DIG_RANKS:
        if items.get(key, 0) > 0:
            return DIG_RANK_BONUSES[key].copy()
    return {"coins": 0, "chance": 0, "luck_regen": 0}


def dig_rank_discount(items: dict[str, int]) -> int:
    for key, _ in DIG_RANKS:
        if items.get(key, 0) > 0:
            return DIG_RANK_DISCOUNTS[key]
    return 0


def dig_discountable_item_keys() -> set[str]:
    """Ranks discount consumables only, never permanent upgrades or tickets."""
    return (
        set(DIG_SHOP_CATEGORIES["consumables"][1])
        | (set(DIG_SHOP_CATEGORIES["gear"][1]) - {"prank"})
    )


def dig_shop_price(item_key: str, items: dict[str, int]) -> int:
    base_price = int(DIG_SHOP_ITEMS[item_key][1])
    if item_key not in dig_discountable_item_keys():
        return base_price
    discount = dig_rank_discount(items)
    return max(1, (base_price * (100 - discount) + 99) // 100)


def apply_dig_rank_coin_bonus(items: dict[str, int], coins: int, used_effects: list[str]) -> int:
    bonus = dig_rank_bonuses(items)["coins"]
    if not bonus:
        return coins
    used_effects.append(f"Ранг: +{bonus}% котоинов")
    return max(1, (coins * (100 + bonus) + 99) // 100)


def dig_week_start(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    return (current.date() - timedelta(days=current.weekday())).isoformat()


def dig_weekly_rank_top_text() -> str:
    rows = db.list_dig_weekly_rankings(dig_week_start(), limit=50)
    if not rows:
        return "<b>Недельный топ рангов</b>\n\nПока нет раскопок владельцев рангов на этой неделе."
    rank_names = {1: "Проходчик", 2: "Бригадир", 3: "Шахтерный барон", 4: "Хозяин глубин"}
    lines = [f"<b>Недельный топ рангов</b>\nНеделя с {dig_week_start()}"]
    for index, row in enumerate(rows, start=1):
        user = escape(dig_player_name(row["username"], row["full_name"]))
        lines.append(f"{index}. {user} — <b>{row['depth']} м</b> · {rank_names[int(row['rank_level'])]}")
    return "\n".join(lines)


def dig_permanent_shovel_bonus(items: dict[str, int]) -> int:
    if items.get("shovel_3", 0) > 0:
        return 6
    if items.get("shovel_2", 0) > 0:
        return 4
    if items.get("shovel_1", 0) > 0:
        return 2
    return 0


def dig_equipment_level(items: dict[str, int], keys: tuple[str, ...]) -> int:
    for level, key in reversed(list(enumerate(keys, start=1))):
        if items.get(key, 0) > 0:
            return level
    return 0


def dig_helmet_reduction(items: dict[str, int]) -> int:
    return (0, 10, 20, 30)[dig_equipment_level(items, ("helmet_1", "helmet_2", "helmet_3"))]


def dig_flashlight_artifact_bonus(items: dict[str, int]) -> int:
    return (0, 3, 6, 10)[dig_equipment_level(items, ("flashlight_1", "flashlight_2", "flashlight_3"))]


def dig_cart_bonus(items: dict[str, int]) -> int:
    if items.get("cart_3", 0) > 0:
        return 35
    if items.get("cart_2", 0) > 0:
        return 20
    return 10 if items.get("cart", 0) > 0 else 0


def dig_backpack_bonus(items: dict[str, int]) -> int:
    return (0, 5, 10, 15)[dig_equipment_level(items, ("backpack_1", "backpack_2", "backpack_3"))]


def dig_route(user_id: int) -> tuple[str, tuple[str, int, float, float, float, int]]:
    progress = db.get_dig_progress(user_id)
    key = str(progress.get("selected_route") or "old_mine")
    return (key, DIG_ROUTES[key]) if key in DIG_ROUTES else ("old_mine", DIG_ROUTES["old_mine"])


def ensure_daily_dig_contracts(user_id: int) -> tuple[str, list[dict]]:
    today = datetime.now(timezone.utc).date().isoformat()
    existing = db.list_dig_contracts(user_id, today)
    if not existing:
        rng = random.Random(f"{today}:{user_id}:contracts")
        keys = rng.sample(list(DIG_STANDARD_CONTRACTS), 3)
        db.ensure_dig_contracts(user_id, today, [(key, DIG_STANDARD_CONTRACTS[key][1]) for key in keys])
    return today, db.list_dig_contracts(user_id, today)


def dig_rank_shift_contract(user_id: int) -> dict | None:
    today, contracts = ensure_daily_dig_contracts(user_id)
    return next((item for item in contracts if item["contract_key"] in DIG_RANK_SHIFT_CONTRACTS), None)


def dig_rank_shift_text(user_id: int) -> str:
    items = dig_items_map(0, user_id)
    rank = dig_rank_name(items)
    if rank == "Новичок":
        return "<b>Сменное задание</b>\n\nОткрывается после покупки ранга в магазине шахты."
    selected = dig_rank_shift_contract(user_id)
    if selected:
        key = selected["contract_key"]
        name, _, target, reward = DIG_RANK_SHIFT_CONTRACTS[key]
        state = "выполнено" if selected["claimed"] else f"{selected['progress']}/{target}"
        return (
            f"<b>Сменное задание [{escape(rank)}]</b>\n\n"
            f"{escape(name)}\nПрогресс: <b>{state}</b>\nНаграда: <b>{reward}</b> котоинов."
        )
    lines = [f"<b>Сменное задание [{escape(rank)}]</b>", "Выбери одну цель на сегодня:"]
    for key, (name, _, _, reward) in DIG_RANK_SHIFT_CONTRACTS.items():
        lines.append(f"• {escape(name)} — <b>+{reward}</b> котоинов")
    return "\n".join(lines)


def select_dig_rank_shift_contract(user_id: int, contract_key: str) -> str | None:
    if contract_key not in DIG_RANK_SHIFT_CONTRACTS:
        return "Такого сменного задания нет."
    if dig_rank_name(dig_items_map(0, user_id)) == "Новичок":
        return "Сменные задания доступны после покупки ранга."
    if dig_rank_shift_contract(user_id):
        return "Сменное задание на сегодня уже выбрано."
    today = datetime.now(timezone.utc).date().isoformat()
    _, _, target, _ = DIG_RANK_SHIFT_CONTRACTS[contract_key]
    db.ensure_dig_contracts(user_id, today, [(contract_key, target)])
    return None


def dig_contracts_text(user_id: int) -> str:
    today, contracts = ensure_daily_dig_contracts(user_id)
    lines = [f"<b>Контракты на {today}</b>", f"Награда: <b>{DIG_CONTRACT_REWARD_COINS}</b> котоинов и <b>{DIG_CONTRACT_REWARD_XP}</b> XP за каждый.", ""]
    for item in contracts:
        name = DIG_CONTRACTS[item["contract_key"]][0]
        mark = "★" if item["contract_key"] in DIG_RANK_SHIFT_CONTRACTS else ("✓" if item["claimed"] else "•")
        lines.append(f"{mark} {escape(name)}: <b>{item['progress']}/{item['target']}</b>")
    return "\n".join(lines)


def update_dig_contracts(user_id: int, dug: int, coins: int, artifact_found: bool) -> list[str]:
    today, _ = ensure_daily_dig_contracts(user_id)
    values = {
        "depth": dug, "coins": coins, "artifact": 1 if artifact_found else 0, "success": 1 if dug > 0 else 0,
    }
    for key, (_, progress_key, _, _) in DIG_RANK_SHIFT_CONTRACTS.items():
        values[key] = values[progress_key]
    db.add_dig_contract_progress(user_id, today, values)
    claimed = db.claim_ready_dig_contracts(user_id, today)
    rewards = []
    for key in claimed:
        if key in DIG_RANK_SHIFT_CONTRACTS:
            reward = DIG_RANK_SHIFT_CONTRACTS[key][3]
            db.add_dig_coins(0, user_id, reward)
            rewards.append(f"Сменное задание «{DIG_CONTRACTS[key][0]}» выполнено: +{reward} котоинов")
        else:
            db.add_dig_coins(0, user_id, DIG_CONTRACT_REWARD_COINS)
            rewards.append(f"Контракт «{DIG_CONTRACTS[key][0]}» выполнен: +{DIG_CONTRACT_REWARD_COINS} котоинов, +{DIG_CONTRACT_REWARD_XP} XP")
    return rewards


def dig_contract_xp_reward(updates: list[str]) -> int:
    return sum(
        DIG_CONTRACT_REWARD_XP
        for text in updates
        if not text.startswith("Сменное задание")
    )


def dig_routes_text(user_id: int) -> str:
    progress = db.get_dig_progress(user_id)
    lines = ["<b>Маршруты шахты</b>", f"Уровень шахтёра: <b>{progress['level']}</b>", ""]
    for key, (name, chance, coins, artifacts, collapse, required_level) in DIG_ROUTES.items():
        mark = "✓" if key == progress["selected_route"] else "•"
        lock = f" (с {required_level} уровня)" if progress["level"] < required_level else ""
        lines.append(f"{mark} <b>{name}</b>{lock}: метр {chance:+d}%, награда x{coins:g}, артефакты x{artifacts:g}, риск x{collapse:g}.")
    return "\n".join(lines)


def dig_expedition_text(chat_id: int) -> str:
    today = datetime.now(timezone.utc).date().isoformat()
    expedition = db.get_dig_expedition(chat_id, today)
    lines = ["<b>Групповая экспедиция</b>", f"Прогресс: <b>{expedition['progress']}/{expedition['target']}</b> м.", f"Награда каждому участнику: <b>{DIG_EXPEDITION_REWARD}</b> котоинов."]
    lines.append("Экспедиция завершена." if expedition["completed"] else f"Участников: <b>{len(expedition['contributors'])}</b>.")
    return "\n".join(lines)


def dig_artifact_text(items: dict[str, int]) -> str:
    found = [name for key, name in DIG_ARTIFACTS.items() if items.get(key, 0) > 0]
    return ", ".join(found) if found else "пока нет"


def dig_resource_names() -> dict[str, str]:
    return {key: str(value["title"]) for key, value in MINE_RESOURCE_CATALOG.items()}


def snapshot_resources(snapshot: dict) -> dict[str, int]:
    resources = snapshot.get("resources")
    if isinstance(resources, dict):
        return {
            str(key): int(value)
            for key, value in resources.items()
            if key in MINE_RESOURCE_CATALOG and int(value) > 0
        }
    ore_units = int(snapshot.get("ore_units", 0) or 0)
    return {"res_iron": ore_units} if ore_units > 0 else {}


def add_snapshot_resources(snapshot: dict, drops: dict[str, int]) -> None:
    resources = snapshot_resources(snapshot)
    for key, quantity in drops.items():
        if key in MINE_RESOURCE_CATALOG and int(quantity) > 0:
            resources[key] = resources.get(key, 0) + int(quantity)
    snapshot["resources"] = resources
    snapshot["ore_units"] = sum(resources.values())


def grant_snapshot_resources(chat_id: int, user_id: int, snapshot: dict, used_effects: list[str]) -> dict[str, int]:
    resources = snapshot_resources(snapshot)
    if not resources:
        return {}
    for key, quantity in resources.items():
        db.add_dig_item(chat_id, user_id, key, quantity)
    used_effects.append(f"Добыча сложена в сумку: {resource_stack_text(resources)}")
    snapshot["resources"] = {}
    snapshot["ore_units"] = 0
    return resources


def find_dig_artifact(
    chat_id: int,
    user_id: int,
    depth: int,
    items: dict[str, int],
    chance_bonus: int = 0,
) -> tuple[int, str | None]:
    if depth <= 0 or secrets.randbelow(100) >= min(60, 5 + depth + chance_bonus):
        return 0, None
    key = list(DIG_ARTIFACTS)[secrets.randbelow(len(DIG_ARTIFACTS))]
    name = DIG_ARTIFACTS[key]
    if items.get(key, 0) > 0:
        bonus = 20 + depth * 3
        return bonus, f"Артефакт: снова найден «{name}». Дубликат продан за <b>{bonus}</b> котоинов."

    db.add_dig_item(chat_id, user_id, key, 1)
    items[key] = 1
    text = f"Артефакт: найден «{name}» и добавлен в коллекцию."
    if all(items.get(artifact_key, 0) > 0 for artifact_key in DIG_ARTIFACTS) and items.get("artifact_set_reward", 0) <= 0:
        db.add_dig_item(chat_id, user_id, "artifact_set_reward", 1)
        items["artifact_set_reward"] = 1
        return 250, text + " Коллекция собрана: <b>+250</b> котоинов и постоянный бонус +5% к наградам."
    return 0, text


def dig_display_name(chat_id: int, user_id: int, username: str | None, full_name: str) -> str:
    name = dig_player_name(username, full_name)
    items = dig_items_map(chat_id, user_id)
    tag = db.get_dig_player_tag(user_id)
    tag_suffix = f" «{tag}»" if tag else ""
    return f"{name}{tag_suffix}{dig_title_suffix(items)}"


def dig_title_suffix(items: dict[str, int]) -> str:
    rank = dig_rank_name(items)
    if rank != "Новичок":
        return f" [{rank}]"
    return ""


def dig_effects_text(items: dict[str, int]) -> str:
    hidden_keys = set(DIG_ARTIFACTS) | {"artifact_set_reward"}
    best_chain_keys: set[str] = set()
    chain_keys = {key for chain in DIG_SHOP_UPGRADE_CHAINS for key in chain}
    for chain in DIG_SHOP_UPGRADE_CHAINS:
        owned = [key for key in chain if items.get(key, 0) > 0]
        if owned:
            best_chain_keys.add(owned[-1])

    groups = {
        "Постоянные": [],
        "Расходники": [],
        "Добыча": [],
        "Оплаченные": [],
        "Прочее": [],
    }
    paid_keys = {"star_dig", "star_lucky_dig", "star_depth_10", "super_game_pass", "super_mute30", "super_tag"}
    special_names = {
        "super_game_pass": "Супер-игра 9×9",
        "super_mute30": "Право на мут 30 минут",
        "super_tag": "Право выбрать тег",
    }
    special_names.update(dig_resource_names())

    ordered_keys = list(dict.fromkeys(DIG_ITEM_ORDER + MINE_RESOURCE_ORDER + sorted(paid_keys) + list(special_names)))
    for key in ordered_keys:
        count = items.get(key, 0)
        if count <= 0 or key in hidden_keys:
            continue
        if key in chain_keys and key not in best_chain_keys:
            continue

        name = special_names.get(key, DIG_SHOP_ITEMS.get(key, (key, 0, ""))[0])
        if key in paid_keys:
            groups["Оплаченные"].append(f"{name} x{count}")
        elif key in MINE_RESOURCE_CATALOG:
            groups["Добыча"].append(f"{name} x{count}")
        elif key in DIG_PROFILE_ITEMS or key in DIG_GIFT_ITEMS or key in DIG_RELATIONSHIP_ITEMS:
            groups["Прочее"].append(name if key in DIG_PERMANENT_ITEMS and count == 1 else f"{name} x{count}")
        elif key in DIG_PERMANENT_ITEMS:
            groups["Постоянные"].append(name if count == 1 else f"{name} x{count}")
        elif key in DIG_SHOP_CATEGORIES["consumables"][1] or key in DIG_SHOP_CATEGORIES["gear"][1]:
            groups["Расходники"].append(f"{name} x{count}")
        else:
            groups["Прочее"].append(f"{name} x{count}")

    lines = []
    for title, values in groups.items():
        if values:
            lines.append(f"{title}: {', '.join(values)}")
    return "\n".join(lines) if lines else "Нет активных эффектов."


def user_dig_cooldown(user_id: int) -> timedelta:
    multiplier = float(get_premium_service().get_mine_bonuses(user_id)["cooldown_multiplier"])
    return timedelta(seconds=DIG_COOLDOWN.total_seconds() * multiplier)


def apply_premium_coin_bonus(user_id: int, coins: int, used_effects: list[str]) -> int:
    multiplier = float(get_premium_service().get_mine_bonuses(user_id)["coins_multiplier"])
    if multiplier <= 1:
        return coins
    used_effects.append(f"Premium: +{round((multiplier - 1) * 100)}% котоинов")
    return max(1, int(coins * multiplier + 0.9999))


@dataclass
class DigReply:
    text: str
    rich_message: InputRichMessage | None = None


@dataclass
class InteractiveDigReply:
    text: str
    session: dict | None = None


def rich_cell(text: str, *, header: bool = False, align: str = "left") -> RichBlockTableCell:
    return RichBlockTableCell(
        align=align,
        valign="middle",
        text=text,
        is_header=header,
    )


def paragraph(text: str) -> InputRichBlockParagraph:
    return InputRichBlockParagraph(text=text)


def rich_plain_text(text: str) -> str:
    cleaned = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"</(?:p|div|li|tr|h[1-6])\s*>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    cleaned = unescape(cleaned)
    return re.sub(r"[ \t]+", " ", cleaned).strip()


def rich_sentence_paragraphs(text: str) -> list[str]:
    return [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+(?=[A-ZА-ЯЁ0-9@«])", text.strip())
        if part.strip()
    ]


def rich_detail_paragraphs(text: str) -> list[str]:
    cleaned = rich_plain_text(text)
    if not cleaned:
        return []
    lines: list[str] = []
    for raw_line in re.split(r"\n+", cleaned):
        line = raw_line.strip()
        if not line:
            continue
        if ";" in line:
            head, _, tail = line.partition(":")
            if tail:
                lines.append(f"{head.strip()}:")
                for part in tail.split(";"):
                    lines.extend(rich_sentence_paragraphs(part))
                continue
            for part in line.split(";"):
                lines.extend(rich_sentence_paragraphs(part))
            continue
        lines.extend(rich_sentence_paragraphs(line))
    return lines


def build_dig_rich_message(
    *,
    player_name: str,
    summary: str,
    dug: int,
    coins: int,
    total_depth: int,
    luck_text: str,
    route_name: str,
    level: int,
    xp: int,
    streak: int,
    expedition_progress: int,
    expedition_target: int,
    details: list[str],
) -> InputRichMessage:
    detail_blocks = [
        paragraph(line)
        for line in rich_detail_paragraphs(
            f"Маршрут: {route_name}. Уровень {level}, XP {xp}, серия {streak}.\n"
            f"Экспедиция группы: {expedition_progress}/{expedition_target} м."
        )
    ]
    for item in details:
        detail_blocks.extend(paragraph(line) for line in rich_detail_paragraphs(item))
    return InputRichMessage(
        blocks=[
            paragraph(f"⛏ {player_name}"),
            paragraph(summary),
            InputRichBlockTable(
                cells=[
                    [
                        rich_cell("Глубина", header=True),
                        rich_cell("Котоины", header=True),
                        rich_cell("Удача", header=True),
                    ],
                    [
                        rich_cell(f"+{dug} м", align="center"),
                        rich_cell(f"+{coins}", align="center"),
                        rich_cell(luck_text, align="center"),
                    ],
                    [
                        rich_cell("Всего", header=True),
                        rich_cell("Серия", header=True),
                        rich_cell("Экспед.", header=True),
                    ],
                    [
                        rich_cell(f"{total_depth} м", align="center"),
                        rich_cell(str(streak), align="center"),
                        rich_cell(f"{expedition_progress}/{expedition_target} м", align="center"),
                    ],
                ],
                is_bordered=True,
                is_striped=False,
            ),
            InputRichBlockDetails(
                summary="Подробнее ниже",
                blocks=detail_blocks,
                is_open=False,
            ),
        ]
    )


def dig_bag_text(chat_id: int, user_id: int) -> str | None:
    player = db.get_dig_player(chat_id, user_id)
    if player is None:
        return None

    now = datetime.now(timezone.utc)
    luck = refreshed_dig_luck(user_id, player.luck, player.last_luck_at, now)
    items = dig_items_map(chat_id, user_id)
    progress = db.get_dig_progress(user_id)
    _, route_data = dig_route(user_id)
    cooldown = "можно копать"
    star_digs = items.get("star_dig", 0) + items.get("star_lucky_dig", 0) + items.get("star_depth_10", 0)
    if star_digs:
        cooldown = f"можно копать, оплаченных попыток: {star_digs}"
    elif player.last_dig_at:
        next_dig = datetime.fromisoformat(player.last_dig_at) + user_dig_cooldown(user_id)
        if now < next_dig:
            remaining = int((next_dig - now).total_seconds() // 60) + 1
            cooldown = f"через {remaining // 60} ч {remaining % 60} мин"

    return (
        "<b>Сумка шахтера</b>\n"
        f"{escape(dig_display_name(player.chat_id, player.user_id, player.username, player.full_name))}\n\n"
        f"Котоины: <b>{player.coins}</b> | Удача: <b>{luck}</b>/100\n"
        f"Глубина: <b>{player.total_depth}</b> м | Рекорд: <b>{player.best_session_depth}</b> м\n"
        f"Ур. <b>{progress['level']}</b> | XP <b>{progress['xp']}</b> | Серия <b>{progress['streak']}</b>\n"
        f"Маршрут: <b>{escape(route_data[0])}</b>\n"
        f"Копать: <b>{escape(cooldown)}</b>\n"
        f"Артефакты: <b>{escape(dig_artifact_text(items))}</b>\n\n"
        f"Золотые билеты: <b>{items.get('golden_ticket', 0)}</b>\n"
        f"Супер-игры: <b>{items.get('super_game_pass', 0)}</b>\n"
        f"<b>Эффекты:</b>\n{escape(dig_effects_text(items))}"
    )


def consume_star_dig(chat_id: int, user_id: int, items: dict[str, int]) -> tuple[bool, bool, bool]:
    if items.get("star_depth_10", 0) > 0 and db.consume_dig_item(chat_id, user_id, "star_depth_10"):
        return True, True, True
    if items.get("star_lucky_dig", 0) > 0 and db.consume_dig_item(chat_id, user_id, "star_lucky_dig"):
        return True, True, False
    if items.get("star_dig", 0) > 0 and db.consume_dig_item(chat_id, user_id, "star_dig"):
        return True, False, False
    return False, False, False


def run_private_dig(chat_id: int, user: User) -> DigReply:
    player = db.get_dig_player(chat_id, user.id)
    if player is None:
        return DigReply("Ты еще не зарегистрирован в раскопках. Сначала напиши <code>копай</code> внутри выбранной группы и нажми кнопку регистрации.")
    if db.get_dig_session(user.id):
        return DigReply("У тебя уже идет пошаговая вылазка в шахте Mini App. Продолжи ее там или заверши текущую вылазку.")
    if db.get_active_interactive_dig_session(user.id):
        return DigReply("У тебя уже идет ручная вылазка в Mini App. Заверши ее перед автоматической раскопкой.")

    now = datetime.now(timezone.utc)
    items = dig_items_map(chat_id, user.id)
    camp_used = False
    star_dig_used, forced_luck, forced_depth = consume_star_dig(chat_id, user.id, items)
    if player.last_dig_at and not star_dig_used:
        last_dig = datetime.fromisoformat(player.last_dig_at)
        cooldown = user_dig_cooldown(user.id)
        next_dig = last_dig + cooldown
        if now < next_dig and items.get("camp", 0) > 0 and now >= last_dig + cooldown / 2:
            camp_used = db.consume_dig_item(chat_id, user.id, "camp")
            if camp_used:
                next_dig = now
        if now < next_dig:
            remaining = int((next_dig - now).total_seconds() // 60) + 1
            return DigReply(f"Кирка отдыхает. До следующей раскопки: <b>{remaining // 60} ч {remaining % 60} мин</b>.")

    route_key, route_data = dig_route(user.id)
    route_name, route_chance, route_coins, route_artifacts, route_collapse, _ = route_data
    luck_before = refreshed_dig_luck(user.id, player.luck, player.last_luck_at, now)
    luck_after = luck_before if forced_luck else max(0, luck_before - DIG_LUCK_COST)
    used_effects: list[str] = []
    if star_dig_used:
        if forced_depth:
            used_effects.append("Оплаченная раскопка: гарантированно пройдено 10 м")
        elif forced_luck:
            used_effects.append("Оплаченная раскопка: ожидание пропущено, действует 100 удачи")
        else:
            used_effects.append("Оплаченная раскопка: ожидание пропущено")
    helmet_used = not forced_luck and items.get("helmet", 0) > 0 and db.consume_dig_item(chat_id, user.id, "helmet")
    shovel_used = not forced_luck and items.get("shovel", 0) > 0 and db.consume_dig_item(chat_id, user.id, "shovel")
    flashlight_used = not forced_depth and items.get("flashlight", 0) > 0 and db.consume_dig_item(chat_id, user.id, "flashlight")
    bucket_used = items.get("bucket", 0) > 0 and db.consume_dig_item(chat_id, user.id, "bucket")
    compass_used = items.get("compass", 0) > 0 and db.consume_dig_item(chat_id, user.id, "compass")
    scanner_used = items.get("scanner", 0) > 0 and db.consume_dig_item(chat_id, user.id, "scanner")
    drill_used = items.get("drill", 0) > 0
    map_used = items.get("map", 0) > 0 and db.consume_dig_item(chat_id, user.id, "map")
    talisman_used = items.get("talisman", 0) > 0 and db.consume_dig_item(chat_id, user.id, "talisman")
    repair_available = items.get("repair_kit", 0) > 0
    chest_used = items.get("mystery_chest", 0) > 0 and db.consume_dig_item(chat_id, user.id, "mystery_chest")
    shovel_bonus = dig_permanent_shovel_bonus(items)
    cart_bonus = dig_cart_bonus(items)
    backpack_bonus = dig_backpack_bonus(items)
    helmet_reduction = dig_helmet_reduction(items)
    rank_bonuses = dig_rank_bonuses(items)
    collection_bonus = items.get("artifact_set_reward", 0) > 0
    effective_luck = 100 if forced_luck else min(100, luck_before + (5 if helmet_used else 0))
    if helmet_used:
        used_effects.append("Каска шахтера: +5 удачи")
    if shovel_used:
        used_effects.append("Крепкая кирка: риск обвала снижен")
    if flashlight_used:
        used_effects.append("Фонарик: +10% к шансам раскопки")
    if bucket_used:
        used_effects.append("Премиум ведро: +25% котоинов")
    if shovel_bonus:
        used_effects.append(f"Постоянная кирка: +{shovel_bonus}% к шансам раскопки")
    if cart_bonus:
        used_effects.append(f"Вагонетка: +{cart_bonus}% котоинов")
    if backpack_bonus:
        used_effects.append(f"Рюкзак: +{backpack_bonus}% котоинов")
    if rank_bonuses["chance"]:
        used_effects.append(f"Ранг: +{rank_bonuses['chance']}% к шансам метров")
    if compass_used:
        route_chance = round(route_chance * 1.25)
        route_coins *= 1.15
        used_effects.append("Компас: маршрут усилен")
    if collection_bonus:
        used_effects.append("Коллекция артефактов: +5% котоинов")

    dug = 10 if forced_depth else 0
    stopped_by_stone = False
    if not forced_depth:
        for meter, chance in enumerate(DIG_SUCCESS_CHANCES, start=1):
            actual_chance = min(95.0, chance + route_chance + (10 if flashlight_used else 0) + shovel_bonus + rank_bonuses["chance"])
            if secrets.randbelow(10000) < int(actual_chance * 100):
                dug = meter
                continue
            if drill_used and db.consume_dig_item(chat_id, user.id, "drill"):
                drill_used = False
                dug = meter
                used_effects.append(f"Бур: пробит {meter}-й метр")
                continue
            if items.get("dynamite", 0) > 0 and db.consume_dig_item(chat_id, user.id, "dynamite"):
                items["dynamite"] -= 1
                dug = meter
                used_effects.append(f"Динамит: пробит {meter}-й метр")
                continue
            stopped_by_stone = True
            break

    collapse_depth = 0
    insurance_used = False
    if stopped_by_stone and dug == 0 and items.get("insurance", 0) > 0 and db.consume_dig_item(chat_id, user.id, "insurance"):
        insurance_used = True
        dug = 1
        used_effects.append("Страховка: первый метр засчитан")

    collapse_chance = max(0, int(max(0, 100 - effective_luck) * route_collapse) - helmet_reduction)
    if scanner_used:
        collapse_chance = collapse_chance * 70 // 100
    if shovel_used:
        collapse_chance //= 2
    if dug > 0 and collapse_chance and secrets.randbelow(100) < collapse_chance:
        if items.get("safe", 0) > 0 and db.consume_dig_item(chat_id, user.id, "safe"):
            used_effects.append("Сейф: обвал остановлен")
        else:
            collapse_depth = 1 + secrets.randbelow(dug)
            dug = max(0, dug - collapse_depth)

    coins = max(1, int(dig_coin_reward(dug) * route_coins + 0.9999))
    if bucket_used:
        coins = (coins * 125 + 99) // 100
    if cart_bonus:
        coins = (coins * (100 + cart_bonus) + 99) // 100
    if backpack_bonus:
        coins = (coins * (100 + backpack_bonus) + 99) // 100
    if collection_bonus:
        coins = (coins * 105 + 99) // 100
    coins = scale_auto_dig_reward(coins)
    event_text = None
    used_effects.append("Автоматический режим: добыча снижена, ручных событий и руды нет")
    artifact_bonus, artifact_text = find_dig_artifact(
        chat_id, user.id, dug, items,
        max(0, int((route_artifacts - 1) * 10)) + dig_flashlight_artifact_bonus(items) + (15 if map_used else 0),
    )
    coins += artifact_bonus
    if talisman_used:
        coins *= 2
        used_effects.append("Талисман: котоины удвоены")
    if chest_used:
        chest_roll = secrets.randbelow(3)
        if chest_roll == 0:
            used_effects.append("Таинственный сундук оказался пуст")
        elif chest_roll == 1:
            bonus = 25 + secrets.randbelow(51)
            coins += bonus
            used_effects.append(f"Таинственный сундук: +{bonus} котоинов")
        else:
            db.add_dig_item(chat_id, user.id, "insurance", 1)
            used_effects.append("Таинственный сундук: найдена страховка")
    coins = apply_dig_rank_coin_bonus(items, coins, used_effects)
    if repair_available:
        restored = (
            "bucket" if bucket_used else
            "flashlight" if flashlight_used else
            "map" if map_used else
            "compass" if compass_used else
            "scanner" if scanner_used else
            "talisman" if talisman_used else
            "mystery_chest" if chest_used else
            "helmet" if helmet_used else
            "shovel" if shovel_used else
            None
        )
        if restored and db.consume_dig_item(chat_id, user.id, "repair_kit"):
            db.add_dig_item(chat_id, user.id, restored, 1)
            used_effects.append(f"Ремонтный набор восстановил: {DIG_SHOP_ITEMS[restored][0]}")
    coins = apply_premium_coin_bonus(user.id, coins, used_effects)
    golden_ticket_found = find_golden_ticket(dug)
    if golden_ticket_found:
        db.add_dig_item(chat_id, user.id, "golden_ticket", 1)
        used_effects.append("Золотой билет: доступна игра в Mini App")
    db.update_dig_player_after_dig(
        chat_id=chat_id,
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        coins_delta=coins,
        depth_delta=dug,
        best_session_depth=dug,
        luck=luck_after,
        last_luck_at=now.isoformat(timespec="seconds"),
        last_dig_at=now.isoformat(timespec="seconds"),
    )
    db.add_dig_weekly_depth(user.id, dig_week_start(now), dug)

    contract_updates = update_dig_contracts(user.id, dug, coins, artifact_text is not None)
    progress = db.update_dig_progress(
        user.id,
        xp_delta=5 + dug * 10 + dig_contract_xp_reward(contract_updates),
        success=dug > 0,
        route=route_key,
    )
    streak_rewards: list[str] = []
    if progress["streak"] == 3:
        db.add_dig_coins(chat_id, user.id, 10)
        streak_rewards.append("Серия 3: +10 котоинов")
    elif progress["streak"] == 5:
        db.add_dig_item(chat_id, user.id, "mystery_chest", 1)
        streak_rewards.append("Серия 5: таинственный сундук")
    elif progress["streak"] == 10:
        db.add_dig_item(chat_id, user.id, "artifact_gem", 1)
        streak_rewards.append("Серия 10: редкий самоцвет")

    today = now.date().isoformat()
    expedition = db.add_dig_expedition_progress(
        chat_id,
        user.id,
        today,
        dug,
        DIG_EXPEDITION_TARGET,
    )
    expedition_rewarded = db.reward_dig_expedition(chat_id, today, DIG_EXPEDITION_REWARD) if expedition["completed"] else []

    achievements = check_dig_achievements(chat_id, user.id, player, dug, coins, collapse_depth, stopped_by_stone)
    display_name = dig_display_name(chat_id, user.id, user.username, user.full_name)
    lines = [f"<b>{escape(display_name)} копает...</b>"]
    if stopped_by_stone and dug == 0 and collapse_depth == 0 and not insurance_used:
        summary = "Ты наткнулся на большой камень, попробуй в следующий раз."
        lines.append("Ты наткнулся на большой камень, попробуй в следующий раз.")
    elif stopped_by_stone:
        summary = f"Камень остановил раскопку. Удалось пройти {dug} м."
        lines.append(f"Камень остановил раскопку. Удалось пройти <b>{dug}</b> м.")
    else:
        summary = f"Редкая удача: пройдено {dug} м за вылазку."
        lines.append(f"Редкая удача: ты прошел все <b>{dug}</b> м за вылазку.")
    details = []
    if collapse_depth:
        details.append(f"Обвал срезал {collapse_depth} м прогресса этой раскопки.")
        lines.append(f"Обвал срезал <b>{collapse_depth}</b> м прогресса этой раскопки.")
    if event_text:
        details.append(event_text)
        lines.append(event_text)
    if artifact_text:
        details.append(artifact_text)
        lines.append(artifact_text)
    lines.append(f"Маршрут: <b>{escape(route_name)}</b>. Уровень: <b>{progress['level']}</b>, XP: <b>{progress['xp']}</b>, серия: <b>{progress['streak']}</b>.")
    lines.append(f"Экспедиция группы: <b>{expedition['progress']}/{expedition['target']}</b> м.")
    if contract_updates:
        lines.append("\n<b>Контракты:</b>")
        lines.extend(escape(item) for item in contract_updates)
        details.append("Контракты: " + "; ".join(contract_updates))
    if streak_rewards:
        lines.append("\n<b>Награды серии:</b>")
        lines.extend(escape(item) for item in streak_rewards)
        details.append("Награды серии: " + "; ".join(streak_rewards))
    if used_effects:
        lines.append("\n<b>Сработали эффекты:</b>")
        lines.extend(escape(effect) for effect in used_effects)
        details.append("Сработали эффекты: " + "; ".join(used_effects))
    luck_text = (
        f"100/100; обычная {luck_before}/100"
        if forced_luck
        else f"{luck_before} → {luck_after}"
    )
    lines.extend(
        [
            f"Получено: <b>{coins}</b> котоинов.",
            f"Общая глубина: <b>{player.total_depth + dug}</b> м.",
            (
                f"Удача в раскопке: <b>100</b>/100. Обычная удача сохранена: <b>{luck_before}</b>/100."
                if forced_luck
                else f"Удача: <b>{luck_before}</b> → <b>{luck_after}</b>."
            ),
        ]
    )
    if achievements:
        lines.append("\n<b>Новые достижения:</b>")
        lines.extend(escape(item) for item in achievements)
        details.append("Новые достижения: " + "; ".join(achievements))
    rich_message = build_dig_rich_message(
        player_name=display_name,
        summary=summary,
        dug=dug,
        coins=coins,
        total_depth=player.total_depth + dug,
        luck_text=luck_text,
        route_name=route_name,
        level=int(progress["level"]),
        xp=int(progress["xp"]),
        streak=int(progress["streak"]),
        expedition_progress=int(expedition["progress"]),
        expedition_target=int(expedition["target"]),
        details=details,
    )
    return DigReply("\n".join(lines), rich_message)


def interactive_dig_cells(session: dict) -> tuple[list[dict], list[int], dict]:
    cells = json.loads(session.get("cells_json") or "[]")
    used_cells = [int(item) for item in json.loads(session.get("used_cells_json") or "[]")]
    snapshot = json.loads(session.get("equipment_snapshot") or "{}")
    return cells, used_cells, snapshot


def interactive_dig_tools(snapshot: dict, stage: list[dict] | dict) -> list[str]:
    if not isinstance(stage, dict) or stage.get("type") == "cells":
        tools = []
        used_tools = set(snapshot.get("used_tools") or [])
        for key in ("flashlight", "map", "dynamite", "miner_hearing", "magnet", "cat_companion"):
            if int(snapshot.get(f"{key}_count", 0)) > 0 and key not in used_tools:
                tools.append(key)
        return tools
    return []


def interactive_dig_view(session: dict, prefix: str | None = None) -> InteractiveDigReply:
    cells, used_cells, snapshot = interactive_dig_cells(session)
    depth = int(session["depth"])
    durability = int(session["durability"])
    temporary_coins = int(session["temporary_coins"])
    route_name = str(snapshot.get("route_name") or "Старая шахта")
    mine_title = str(snapshot.get("mine_title") or route_name)
    mine_emoji = str(snapshot.get("mine_emoji") or "⛏")
    luck = int(session["luck_snapshot"])
    resources = snapshot_resources(snapshot)
    resource_total = sum(resources.values())
    lines = []
    if prefix:
        lines.append(prefix)
        lines.append("")
    lines.extend(
        [
            f"🐱 <b>Шахтёрский кот в забое</b> · {escape(mine_emoji)} <b>{escape(mine_title)}</b>",
            f"Глубина: <b>{depth}/{INTERACTIVE_DIG_MAX_DEPTH}</b> м",
            f"Маршрут: <b>{escape(route_name)}</b>",
            f"Удача: <b>{luck}</b>/100 | Прочность: <b>{durability}</b>/{INTERACTIVE_DIG_DURABILITY}",
            f"Временная добыча: <b>{temporary_coins}</b> котоинов | Ресурсы: <b>{resource_total}</b> ед.",
        ]
    )
    if isinstance(cells, dict) and cells.get("type") in {"event", "final"}:
        label = "Финальная комната" if cells.get("type") == "final" else "Событие"
        lines.extend(
            [
                "",
                f"{escape(str(cells.get('emoji') or '❔'))} <b>{escape(str(cells.get('title') or label))}</b>",
                escape(str(cells.get("text") or "Выбери действие.")),
            ]
        )
        if resources:
            lines.append(f"В сумке вылазки: {escape(resource_stack_text(resources))}.")
    else:
        lines.extend(
            [
                "",
                "Выбери слой грунта:",
                "🟫 обычный · ✨ руда · 🪨 порода · 🌿 странность · ❓ неизвестно",
            ]
        )
        if isinstance(cells, dict) and cells.get("preview"):
            lines.append(f"🗺 Следующий ряд: {escape(str(cells.get('preview')))}")
    return InteractiveDigReply("\n".join(lines), session=session)


def start_interactive_dig(chat_id: int, user: User) -> InteractiveDigReply:
    player = db.get_dig_player(chat_id, user.id)
    if player is None:
        return InteractiveDigReply("Ты еще не зарегистрирован в раскопках. Сначала напиши <code>копай</code> внутри группы и нажми регистрацию.")
    if db.get_dig_session(user.id):
        return InteractiveDigReply("У тебя уже идет пошаговая вылазка в шахте Mini App. Продолжи ее там или заверши текущую вылазку.")

    active = db.get_active_interactive_dig_session(user.id)
    if active:
        return interactive_dig_view(active, "Продолжаем активную вылазку.")

    now = datetime.now(timezone.utc)
    items = dig_items_map(chat_id, user.id)
    if items.get("star_depth_10", 0) > 0:
        old_result = run_private_dig(chat_id, user)
        return InteractiveDigReply(old_result.text)

    camp_used = False
    star_dig_used, forced_luck, _ = consume_star_dig(chat_id, user.id, items)
    if player.last_dig_at and not star_dig_used:
        last_dig = datetime.fromisoformat(player.last_dig_at)
        cooldown = user_dig_cooldown(user.id)
        next_dig = last_dig + cooldown
        if now < next_dig and items.get("camp", 0) > 0 and now >= last_dig + cooldown / 2:
            camp_used = db.consume_dig_item(chat_id, user.id, "camp")
            if camp_used:
                next_dig = now
        if now < next_dig:
            remaining = int((next_dig - now).total_seconds() // 60) + 1
            return InteractiveDigReply(f"Кирка отдыхает. До следующей раскопки: <b>{remaining // 60} ч {remaining % 60} мин</b>.")

    route_key, route_data = dig_route(user.id)
    route_name, route_chance, route_coins, route_artifacts, _route_collapse, _unlock_level = route_data
    mine = mine_type_for_total_depth(player.total_depth)
    luck_before = refreshed_dig_luck(user.id, player.luck, player.last_luck_at, now)
    luck_after = luck_before if forced_luck else max(0, luck_before - DIG_LUCK_COST)
    used_effects: list[str] = []
    if star_dig_used:
        used_effects.append("Оплаченная раскопка: ожидание пропущено" + (" и действует 100 удачи" if forced_luck else ""))
    if camp_used:
        used_effects.append("Лагерь: ожидание сокращено")

    helmet_used = not forced_luck and items.get("helmet", 0) > 0 and db.consume_dig_item(chat_id, user.id, "helmet")
    shovel_used = not forced_luck and items.get("shovel", 0) > 0 and db.consume_dig_item(chat_id, user.id, "shovel")
    flashlight_used = False
    bucket_used = items.get("bucket", 0) > 0 and db.consume_dig_item(chat_id, user.id, "bucket")
    compass_used = items.get("compass", 0) > 0 and db.consume_dig_item(chat_id, user.id, "compass")
    scanner_used = items.get("scanner", 0) > 0 and db.consume_dig_item(chat_id, user.id, "scanner")
    map_used = False
    talisman_used = items.get("talisman", 0) > 0 and db.consume_dig_item(chat_id, user.id, "talisman")
    chest_used = items.get("mystery_chest", 0) > 0 and db.consume_dig_item(chat_id, user.id, "mystery_chest")
    repair_candidates = [
        key
        for key, used in (
            ("helmet", helmet_used),
            ("shovel", shovel_used),
            ("bucket", bucket_used),
            ("compass", compass_used),
            ("scanner", scanner_used),
            ("talisman", talisman_used),
            ("mystery_chest", chest_used),
        )
        if used
    ]

    if compass_used:
        route_chance = round(route_chance * 1.25)
        route_coins *= 1.15
    shovel_bonus = dig_permanent_shovel_bonus(items)
    cart_bonus = dig_cart_bonus(items)
    backpack_bonus = dig_backpack_bonus(items)
    helmet_reduction = dig_helmet_reduction(items)
    rank_bonuses = dig_rank_bonuses(items)
    collection_bonus = items.get("artifact_set_reward", 0) > 0
    premium_multiplier = float(get_premium_service().get_mine_bonuses(user.id)["coins_multiplier"])
    premium_bonus = max(0, round((premium_multiplier - 1) * 100))
    coin_bonus_percent = (25 if bucket_used else 0) + cart_bonus + backpack_bonus + (5 if collection_bonus else 0) + rank_bonuses["coins"] + premium_bonus
    route_coins *= (100 + int(mine.get("reward_bonus", 0))) / 100
    chance_bonus = route_chance + float(mine.get("chance_bonus", 0.0)) + (10 if flashlight_used else 0) + shovel_bonus + rank_bonuses["chance"]
    loss_protection = (15 if shovel_used else 0) + (5 if scanner_used else 0) + helmet_reduction // 3
    if helmet_used:
        used_effects.append("Каска шахтера: +5 удачи")
    if shovel_used:
        used_effects.append("Крепкая кирка: меньше потерь при обвале")
    if flashlight_used:
        used_effects.append("Фонарик: +10% к шансам")
    if bucket_used:
        used_effects.append("Премиум ведро: +25% котоинов")
    if compass_used:
        used_effects.append("Компас: маршрут усилен")
    if scanner_used:
        used_effects.append("Сканер: меньше потерь при обвале")
    if shovel_bonus:
        used_effects.append(f"Постоянная кирка: +{shovel_bonus}% к шансам")
    if cart_bonus:
        used_effects.append(f"Вагонетка: +{cart_bonus}% котоинов")
    if backpack_bonus:
        used_effects.append(f"Рюкзак: +{backpack_bonus}% котоинов")
    if rank_bonuses["chance"]:
        used_effects.append(f"Ранг: +{rank_bonuses['chance']}% к шансам")
    if rank_bonuses["coins"]:
        used_effects.append(f"Ранг: +{rank_bonuses['coins']}% котоинов")
    if premium_bonus:
        used_effects.append(f"Premium: +{premium_bonus}% котоинов")

    snapshot = {
        "route_name": route_name,
        "mine_key": mine["key"],
        "mine_title": mine["title"],
        "mine_emoji": mine["emoji"],
        "mine_description": mine["description"],
        "route_chance": route_chance,
        "route_coins": route_coins,
        "route_artifacts": route_artifacts,
        "luck_before": luck_before,
        "luck_after": luck_after,
        "forced_luck": forced_luck,
        "chance_bonus": chance_bonus,
        "coin_bonus_percent": coin_bonus_percent,
        "loss_protection": loss_protection,
        "map_used": map_used,
        "flashlight_count": int(items.get("flashlight", 0)),
        "map_count": int(items.get("map", 0)),
        "dynamite_count": int(items.get("dynamite", 0)),
        "insurance_count": int(items.get("insurance", 0)),
        "miner_hearing_count": int(items.get("miner_hearing", 0)),
        "magnet_count": int(items.get("magnet", 0)),
        "cat_companion_count": int(items.get("cat_companion", 0)),
        "used_tools": [],
        "talisman_used": talisman_used,
        "chest_used": chest_used,
        "repair_candidates": repair_candidates,
        "used_effects": used_effects,
        "ore_units": 0,
        "resources": {},
    }
    session = db.create_interactive_dig_session(
        session_id=uuid4().hex[:16],
        user_id=user.id,
        chat_id=chat_id,
        route_key=route_key,
        depth=0,
        durability=INTERACTIVE_DIG_DURABILITY,
        temporary_coins=0,
        luck_snapshot=100 if forced_luck else luck_before,
        equipment_snapshot=json.dumps(snapshot, ensure_ascii=False),
        cells_json=json.dumps(generate_dig_stage(1, str(mine["key"])), ensure_ascii=False),
    )
    return interactive_dig_view(session, "Вылазка началась.")


def settle_interactive_dig(session: dict, user: User, *, collapsed: bool) -> DigReply:
    cells, used_cells, snapshot = interactive_dig_cells(session)
    chat_id = int(session["chat_id"])
    depth = int(session["depth"])
    temporary_coins = int(session["temporary_coins"])
    player = db.get_dig_player(chat_id, user.id)
    if player is None:
        db.finish_interactive_dig_session(session["id"], "cancelled")
        return DigReply("Игрок не найден, вылазка закрыта без награды.")

    if collapsed:
        payout, lost = collapse_payout(temporary_coins, int(snapshot.get("loss_protection", 0)))
    else:
        payout, lost = temporary_coins, 0
    event_text = None
    artifact_text = None
    artifact_bonus = 0
    final_bonus_text = ""
    used_effects = list(snapshot.get("used_effects") or [])
    items = dig_items_map(chat_id, user.id)
    now = datetime.now(timezone.utc)
    if depth > 0 and not collapsed:
        before_event = payout
        payout, event_text = dig_random_event(depth, payout)
        if payout < before_event and items.get("medkit", 0) > 0 and db.consume_dig_item(chat_id, user.id, "medkit"):
            payout = before_event
            remember_repair_candidate(snapshot, "medkit")
            used_effects.append("Аптечка: потеря котоинов отменена")
        artifact_bonus, artifact_text = find_dig_artifact(
            chat_id,
            user.id,
            depth,
            items,
            max(0, int((float(snapshot.get("route_artifacts", 1.0)) - 1) * 10))
            + dig_flashlight_artifact_bonus(items)
            + (15 if snapshot.get("map_used") else 0),
        )
        payout += artifact_bonus
        if snapshot.get("talisman_used"):
            payout *= 2
            used_effects.append("Талисман: финальные котоины удвоены")
        if snapshot.get("chest_used"):
            chest_roll = secrets.randbelow(3)
            if chest_roll == 0:
                used_effects.append("Таинственный сундук оказался пуст")
            elif chest_roll == 1:
                bonus = 25 + secrets.randbelow(51)
                payout += bonus
                used_effects.append(f"Таинственный сундук: +{bonus} котоинов")
            else:
                db.add_dig_item(chat_id, user.id, "insurance", 1)
                used_effects.append("Таинственный сундук: найдена страховка")
    if depth >= INTERACTIVE_DIG_MAX_DEPTH and not collapsed:
        final_bonus, final_bonus_text = final_depth_bonus(depth, str(snapshot.get("mine_key") or "old_mine"))
        payout += final_bonus

    if depth > 0:
        grant_snapshot_resources(chat_id, user.id, snapshot, used_effects)

    apply_interactive_repair_kit(chat_id, user.id, snapshot, used_effects)

    db.update_dig_player_after_dig(
        chat_id=chat_id,
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        coins_delta=payout,
        depth_delta=depth,
        best_session_depth=depth,
        luck=int(snapshot.get("luck_after", player.luck)),
        last_luck_at=now.isoformat(timespec="seconds"),
        last_dig_at=now.isoformat(timespec="seconds"),
    )
    db.add_dig_weekly_depth(user.id, dig_week_start(now), depth)
    contract_updates = update_dig_contracts(user.id, depth, payout, artifact_text is not None)
    progress = db.update_dig_progress(
        user.id,
        xp_delta=5 + depth * 10 + dig_contract_xp_reward(contract_updates),
        success=depth > 0,
        route=str(session["route_key"]),
    )
    today = now.date().isoformat()
    expedition = db.add_dig_expedition_progress(chat_id, user.id, today, depth, DIG_EXPEDITION_TARGET)
    if expedition["completed"]:
        db.reward_dig_expedition(chat_id, today, DIG_EXPEDITION_REWARD)
    if depth > 0 and find_golden_ticket(depth):
        db.add_dig_item(chat_id, user.id, "golden_ticket", 1)
        used_effects.append("Золотой билет: доступна игра в Mini App")
    achievements = check_dig_achievements(chat_id, user.id, player, depth, payout, lost, collapsed)
    db.finish_interactive_dig_session(session["id"], "collapsed" if collapsed else "finished")

    display_name = dig_display_name(chat_id, user.id, user.username, user.full_name)
    title = "Обвал!" if collapsed else ("Глубина 10 м взята!" if depth >= INTERACTIVE_DIG_MAX_DEPTH else "Добыча забрана.")
    lines = [
        f"⛏ <b>{escape(display_name)}</b>",
        f"<b>{escape(title)}</b>",
        f"Глубина: <b>{depth}</b> м",
        f"Получено: <b>{payout}</b> котоинов.",
    ]
    if lost:
        lines.append(f"Обвал унёс: <b>{lost}</b> котоинов.")
    lines.append(f"Общая глубина: <b>{player.total_depth + depth}</b> м.")
    lines.append(f"Удача: <b>{snapshot.get('luck_before', player.luck)}</b> → <b>{snapshot.get('luck_after', player.luck)}</b>.")
    if event_text:
        lines.append(event_text)
    if artifact_text:
        lines.append(artifact_text)
    if final_bonus_text:
        lines.append(escape(final_bonus_text))
    if contract_updates:
        lines.append("\n<b>Контракты:</b>")
        lines.extend(escape(item) for item in contract_updates)
    lines.append(f"Уровень: <b>{progress['level']}</b>, XP: <b>{progress['xp']}</b>, серия: <b>{progress['streak']}</b>.")
    lines.append(f"Экспедиция группы: <b>{expedition['progress']}/{expedition['target']}</b> м.")
    if achievements:
        lines.append("\n<b>Новые достижения:</b>")
        lines.extend(escape(item) for item in achievements)
    if used_effects:
        lines.append("\n<b>Сработали эффекты:</b>")
        lines.extend(escape(str(item)) for item in used_effects)
    return DigReply("\n".join(lines))


def dig_star_payload(action: str, user_id: int, chat_id: int) -> str:
    return f"dig_star:{action}:{user_id}:{chat_id}:{uuid4().hex}"


def parse_dig_star_payload(payload: str) -> tuple[str, int, int] | None:
    parts = payload.split(":", 4)
    if len(parts) != 5 or parts[0] != "dig_star" or parts[1] not in DIG_STAR_ACTIONS:
        return None
    try:
        return parts[1], int(parts[2]), int(parts[3])
    except ValueError:
        return None


def dig_star_price(action: str) -> int:
    return DIG_STAR_ACTIONS[action][2]


def dig_star_invoice(action: str) -> tuple[str, str, int]:
    title, description, price, _, _ = DIG_STAR_ACTIONS[action]
    return title, description, price


def dig_shop_items_for_keyboard() -> list[tuple[str, str, int]]:
    return [(key, DIG_SHOP_ITEMS[key][0], DIG_SHOP_ITEMS[key][1]) for key in DIG_ITEM_ORDER]


def dig_shop_categories_for_keyboard() -> list[tuple[str, str]]:
    return [(key, DIG_SHOP_CATEGORIES[key][0]) for key in DIG_SHOP_CATEGORY_ORDER]


def dig_shop_category_title(category: str) -> str:
    return DIG_SHOP_CATEGORIES.get(category, DIG_SHOP_CATEGORIES["consumables"])[0]


def dig_shop_category_items(category: str, items: dict[str, int]) -> list[tuple[str, str, int]]:
    if category not in DIG_SHOP_CATEGORIES:
        category = "consumables"

    item_keys = DIG_SHOP_CATEGORIES[category][1]
    visible_keys: list[str] = []
    handled_keys: set[str] = set()

    for chain in DIG_SHOP_UPGRADE_CHAINS:
        chain_in_category = [key for key in chain if key in item_keys]
        if not chain_in_category:
            continue
        handled_keys.update(chain_in_category)
        for key in chain_in_category:
            if items.get(key, 0) <= 0:
                visible_keys.append(key)
                break

    for key in item_keys:
        if key in handled_keys:
            continue
        if key in DIG_PERMANENT_ITEMS and items.get(key, 0) > 0:
            continue
        visible_keys.append(key)

    return [
        (key, DIG_SHOP_ITEMS[key][0], dig_shop_price(key, items))
        for key in visible_keys
        if key in DIG_SHOP_ITEMS
    ]


def dig_shop_page_items(category: str, items: dict[str, int], page: int) -> tuple[list[tuple[str, str, int]], int, int]:
    category_items = dig_shop_category_items(category, items)
    total_pages = max(1, math.ceil(len(category_items) / DIG_SHOP_PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))
    start = page * DIG_SHOP_PAGE_SIZE
    return category_items[start:start + DIG_SHOP_PAGE_SIZE], page, total_pages


def dig_shop_category_for_item(item_key: str) -> str:
    return DIG_SHOP_ITEM_CATEGORY.get(item_key, "consumables")


def dig_shop_overview_text(coins: int, items: dict[str, int]) -> str:
    return (
        "<b>Магазин раскопок</b>\n"
        f"Котоины: <b>{coins}</b>\n\n"
        f"<b>Активные эффекты:</b>\n{escape(dig_effects_text(items))}\n\n"
        "Выбери раздел магазина."
    )


def dig_shop_category_text(coins: int, category: str, page: int, total_pages: int) -> str:
    page_text = f"\nСтраница: <b>{page + 1}/{total_pages}</b>" if total_pages > 1 else ""
    return (
        f"<b>{escape(dig_shop_category_title(category))}</b>\n"
        f"Котоины: <b>{coins}</b>{page_text}\n\n"
        "Нажми на товар, чтобы открыть описание и покупку."
    )


def dig_purchase_error(items: dict[str, int], item_key: str) -> str | None:
    if item_key in DIG_PERMANENT_ITEMS and items.get(item_key, 0) > 0:
        return "Этот постоянный товар уже куплен."
    required = DIG_ITEM_REQUIREMENTS.get(item_key)
    if required and items.get(required, 0) <= 0:
        return f"Сначала купи: {DIG_SHOP_ITEMS[required][0]}."
    return None


def dig_purchase_is_duplicate(chat_id: int, user_id: int, item_key: str, message_id: int) -> bool:
    now = datetime.now(timezone.utc)
    expired = [
        key
        for key, created_at in DIG_PURCHASE_GUARD.items()
        if (now - created_at).total_seconds() > 10
    ]
    for key in expired:
        DIG_PURCHASE_GUARD.pop(key, None)

    key = (chat_id, user_id, item_key, message_id)
    if key in DIG_PURCHASE_GUARD:
        return True
    DIG_PURCHASE_GUARD[key] = now
    return False


def blacklist_text(chat_id: int) -> str:
    words = db.list_blacklist_words(chat_id)
    if not words:
        return "<b>Черный список слов</b>\n\nСписок пока пуст."
    lines = ["<b>Черный список слов</b>"]
    lines.extend(f"{index}. {escape(item.word)}" for index, item in enumerate(words, start=1))
    return "\n".join(lines)


def award_dig_achievement(chat_id: int, user_id: int, achievement_key: str) -> str | None:
    achievement = DIG_ACHIEVEMENTS.get(achievement_key)
    if achievement is None:
        return None
    if not db.add_dig_achievement(chat_id, user_id, achievement_key):
        return None

    name, _, coins, item_key = achievement
    if coins:
        db.add_dig_coins(chat_id, user_id, coins)
    item_text = ""
    if item_key:
        db.add_dig_item(chat_id, user_id, item_key, 1)
        item_name = DIG_SHOP_ITEMS.get(item_key, (item_key, 0, ""))[0]
        item_text = f", предмет: {item_name}"
    return f"{name}: +{coins} котоинов{item_text}"


def check_dig_achievements(
    chat_id: int,
    user_id: int,
    player,
    dug: int,
    coins_before_reward: int,
    collapse_depth: int,
    stopped_by_stone: bool,
) -> list[str]:
    total_depth = player.total_depth + dug
    total_coins = player.coins + coins_before_reward
    checks = ["first_dig"]
    if dug >= 1:
        checks.append("first_meter")
    if dug >= 5:
        checks.append("five_meter_run")
    if dug >= 10:
        checks.append("ten_meter_run")
    if total_depth >= 25:
        checks.append("total_25")
    if total_depth >= 100:
        checks.append("total_100")
    if total_coins >= 500:
        checks.append("coins_500")
    if stopped_by_stone and dug == 0:
        checks.append("stone_zero")
    if collapse_depth:
        checks.append("collapse_survive")
    items = dig_items_map(chat_id, user_id)
    artifact_count = sum(1 for key in DIG_ARTIFACTS if items.get(key, 0) > 0)
    rank = dig_rank_name(items)
    if rank != "Новичок" and total_depth >= 25:
        checks.append("rank_digger")
    if rank != "Новичок" and artifact_count >= 3:
        checks.append("rank_artifacts")
    if rank != "Новичок" and total_depth >= 150:
        checks.append("rank_depth")
    if items.get("rank_4", 0) > 0 and artifact_count == len(DIG_ARTIFACTS):
        checks.append("rank_master")

    awarded = []
    for key in checks:
        text = award_dig_achievement(chat_id, user_id, key)
        if text:
            awarded.append(text)
    return awarded


def dig_achievements_text(chat_id: int, user_id: int) -> str:
    owned = {item.achievement_key for item in db.list_dig_achievements(chat_id, user_id)}
    lines = [f"<b>Достижения:</b> {len(owned)}/{len(DIG_ACHIEVEMENTS)}"]
    for key, (name, description, coins, item_key) in DIG_ACHIEVEMENTS.items():
        mark = "✓" if key in owned else "•"
        reward = f"+{coins} котоинов"
        if item_key:
            reward += f", {DIG_SHOP_ITEMS.get(item_key, (item_key, 0, ''))[0]}"
        lines.append(f"{mark} <b>{escape(name)}</b> — {escape(description)} Награда: {escape(reward)}")
    return "\n".join(lines)


def backfill_dig_achievements() -> int:
    awarded_count = 0
    for player in db.list_all_dig_players():
        checks = []
        if player.last_dig_at:
            checks.append("first_dig")
        if player.total_depth >= 1 or player.best_session_depth >= 1:
            checks.append("first_meter")
        if player.best_session_depth >= 5:
            checks.append("five_meter_run")
        if player.best_session_depth >= 10:
            checks.append("ten_meter_run")
        if player.total_depth >= 25:
            checks.append("total_25")
        if player.total_depth >= 100:
            checks.append("total_100")
        if player.coins >= 500:
            checks.append("coins_500")
        items = {item.item_key: item.quantity for item in db.list_dig_items(player.chat_id, player.user_id)}
        if items:
            checks.append("first_purchase")
        progress = db.get_dig_progress(player.user_id)
        if progress["level"] >= 5:
            checks.append("level_5")
        if progress["level"] >= 10:
            checks.append("level_10")
        artifact_count = sum(1 for key in DIG_ARTIFACTS if items.get(key, 0) > 0)
        if artifact_count >= 3:
            checks.append("collector_3")
        if artifact_count == len(DIG_ARTIFACTS):
            checks.append("collector_all")
        if player.coins >= 10000:
            checks.append("coins_10000")

        for key in checks:
            if award_dig_achievement(player.chat_id, player.user_id, key):
                awarded_count += 1
    return awarded_count


async def require_dig_button_owner(callback: CallbackQuery, owner_id: int) -> bool:
    if callback.from_user.id != owner_id:
        await callback.answer("Эта кнопка принадлежит другому пользователю.", show_alert=True)
        return False
    return True


async def resolve_dig_button_owner(callback: CallbackQuery, owner_raw: str | None) -> int | None:
    if owner_raw and owner_raw.isdigit():
        owner_id = int(owner_raw)
    elif callback.message and callback.message.chat.type == "private":
        owner_id = callback.from_user.id
    else:
        await callback.answer("Эта старая кнопка больше не действует. Вызови команду заново.", show_alert=True)
        return None
    return owner_id if await require_dig_button_owner(callback, owner_id) else None


WEATHER_CODES = {
    0: "Ясно",
    1: "Преимущественно ясно",
    2: "Переменная облачность",
    3: "Пасмурно",
    45: "Туман",
    48: "Изморозь и туман",
    51: "Слабая морось",
    53: "Морось",
    55: "Сильная морось",
    61: "Небольшой дождь",
    63: "Дождь",
    65: "Сильный дождь",
    66: "Ледяной дождь",
    67: "Сильный ледяной дождь",
    71: "Небольшой снег",
    73: "Снег",
    75: "Сильный снег",
    77: "Снежные зерна",
    80: "Небольшой ливень",
    81: "Ливень",
    82: "Сильный ливень",
    85: "Небольшой снегопад",
    86: "Сильный снегопад",
    95: "Гроза",
    96: "Гроза с градом",
    99: "Сильная гроза с градом",
}


@dataclass(frozen=True)
class WeatherPlace:
    latitude: float
    longitude: float
    label: str
    source: str
    score: int


WEATHER_UA_HINT_RE = re.compile(
    r"\b(укра[иї]на|украине|україні|область|обл\.?|район|р-н|крив|киев|київ|днепр|дніпр|одесс|одес|харьк|харків|льв[іо]в)\b",
    re.IGNORECASE,
)
WEATHER_STOP_WORDS = {
    "село",
    "села",
    "поселок",
    "посёлок",
    "смт",
    "пгт",
    "город",
    "місто",
    "район",
    "область",
    "обл",
    "украина",
    "україна",
}
WEATHER_KRYVYI_RIH_FALLBACKS = {
    "авангард": WeatherPlace(
        latitude=47.9105,
        longitude=33.3918,
        label="Авангард, Кривий Ріг, Дніпропетровська область, Україна",
        source="local",
        score=1000,
    ),
    "марьяновка": WeatherPlace(
        latitude=47.9105,
        longitude=33.3918,
        label="Марьяновка, Криворожский район, Днепропетровская область, Украина",
        source="local",
        score=1000,
    ),
    "мар'янівка": WeatherPlace(
        latitude=47.9105,
        longitude=33.3918,
        label="Мар'янівка, Криворізький район, Дніпропетровська область, Україна",
        source="local",
        score=1000,
    ),
    "марянівка": WeatherPlace(
        latitude=47.9105,
        longitude=33.3918,
        label="Мар'янівка, Криворізький район, Дніпропетровська область, Україна",
        source="local",
        score=1000,
    ),
}


def weather_description(code: int | None) -> str:
    if code is None:
        return "Нет данных"
    return WEATHER_CODES.get(code, f"Код погоды {code}")


def weather_query_tokens(query: str) -> list[str]:
    normalized = re.sub(r"[^\wа-яА-ЯіїєґІЇЄҐ]+", " ", query.casefold())
    return [
        token
        for token in normalized.split()
        if len(token) > 2 and token not in WEATHER_STOP_WORDS
    ]


def weather_place_score(query: str, label: str, country_code: str | None = None) -> int:
    tokens = weather_query_tokens(query)
    normalized_label = label.casefold()
    score = 0
    if country_code and country_code.casefold() == "ua":
        score += 30 if WEATHER_UA_HINT_RE.search(query) else 12
    for token in tokens:
        if token in normalized_label:
            score += 12
        elif token.startswith("крив") and ("крив" in normalized_label or "kryv" in normalized_label):
            score += 20
        elif token.startswith("дніпр") and ("дніпр" in normalized_label or "днепр" in normalized_label or "dnipr" in normalized_label):
            score += 16
        else:
            score -= 2
    if tokens and normalized_label.startswith(tokens[0]):
        score += 10
    return score


def format_open_meteo_place(place: dict, fallback: str) -> str:
    parts = [str(place.get("name") or fallback)]
    for key in ("admin3", "admin2", "admin1", "country"):
        value = place.get(key)
        if value and str(value) not in parts:
            parts.append(str(value))
    return ", ".join(parts)


async def geocode_open_meteo(session: aiohttp.ClientSession, query: str) -> list[WeatherPlace]:
    geocode_url = (
        "https://geocoding-api.open-meteo.com/v1/search"
        f"?name={quote(query)}&count=10&language=ru&format=json"
    )
    async with session.get(geocode_url, headers={"User-Agent": "telegram-autoreply-bot"}) as response:
        if response.status != 200:
            raise RuntimeError(f"geocoding service returned {response.status}")
        data = await response.json(content_type=None)

    places: list[WeatherPlace] = []
    for item in data.get("results") or []:
        label = format_open_meteo_place(item, query)
        places.append(
            WeatherPlace(
                latitude=float(item["latitude"]),
                longitude=float(item["longitude"]),
                label=label,
                source="open-meteo",
                score=weather_place_score(query, label, item.get("country_code")),
            )
        )
    return places


async def geocode_nominatim(session: aiohttp.ClientSession, query: str) -> list[WeatherPlace]:
    url = (
        "https://nominatim.openstreetmap.org/search"
        f"?q={quote(query)}&format=jsonv2&addressdetails=1&limit=8&accept-language=ru,uk,en"
    )
    async with session.get(url, headers={"User-Agent": "telegram-autoreply-bot/1.0"}) as response:
        if response.status != 200:
            return []
        data = await response.json(content_type=None)

    places: list[WeatherPlace] = []
    for item in data if isinstance(data, list) else []:
        display = str(item.get("display_name") or item.get("name") or query)
        country_code = str(item.get("address", {}).get("country_code", ""))
        places.append(
            WeatherPlace(
                latitude=float(item["lat"]),
                longitude=float(item["lon"]),
                label=display,
                source="osm",
                score=weather_place_score(query, display, country_code) + 8,
            )
        )
    return places


async def resolve_weather_place(session: aiohttp.ClientSession, query: str) -> WeatherPlace:
    candidates: list[WeatherPlace] = []
    candidates.extend(await geocode_nominatim(session, query))
    candidates.extend(await geocode_open_meteo(session, query))

    if not candidates:
        raise RuntimeError("city not found")

    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates[0]


async def fetch_weather(city: str, period: str) -> str:
    timeout = aiohttp.ClientTimeout(total=12)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        place = await resolve_weather_place(session, city)
        latitude = place.latitude
        longitude = place.longitude
        location = place.label

        forecast_url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={latitude}&longitude={longitude}"
            "&current=temperature_2m,apparent_temperature,relative_humidity_2m,pressure_msl,wind_speed_10m,weather_code"
            "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max"
            "&timezone=auto&forecast_days=7"
        )
        async with session.get(forecast_url, headers={"User-Agent": "telegram-autoreply-bot"}) as response:
            if response.status != 200:
                raise RuntimeError(f"forecast service returned {response.status}")
            forecast = await response.json(content_type=None)

    if period == "now":
        current = forecast["current"]
        return (
            f"<b>Погода сейчас: {escape(location)}</b>\n"
            f"{escape(weather_description(current.get('weather_code')))}\n"
            f"Температура: <b>{current.get('temperature_2m', '?')}°C</b>, "
            f"ощущается как <b>{current.get('apparent_temperature', '?')}°C</b>\n"
            f"Ветер: <b>{current.get('wind_speed_10m', '?')} км/ч</b>\n"
            f"Влажность: <b>{current.get('relative_humidity_2m', '?')}%</b>\n"
            f"Давление: <b>{current.get('pressure_msl', '?')} гПа</b>"
        )

    daily = forecast["daily"]
    days_count = 1 if period == "tomorrow" else 7
    start_index = 1 if period == "tomorrow" else 0
    title = "Погода на завтра" if period == "tomorrow" else "Погода на 7 дней"
    lines = [f"<b>{title}: {escape(location)}</b>"]

    for index in range(start_index, min(start_index + days_count, len(daily["time"]))):
        lines.append(
            f"{escape(daily['time'][index])}: "
            f"{escape(weather_description(daily['weather_code'][index]))}, "
            f"{daily['temperature_2m_min'][index]}..{daily['temperature_2m_max'][index]}°C, "
            f"осадки {daily['precipitation_sum'][index]} мм, "
            f"ветер до {daily['wind_speed_10m_max'][index]} км/ч"
        )

    return "\n".join(lines)


def mention_chat(chat: RegisteredChat) -> str:
    username = f" @{chat.username}" if chat.username else ""
    return f"{escape(chat.title)}{escape(username)}"


def chat_link_url(chat: RegisteredChat) -> str | None:
    if chat.username:
        return f"https://t.me/{quote(chat.username.lstrip('@'))}"
    chat_id_text = str(chat.chat_id)
    if chat_id_text.startswith("-100"):
        return f"https://t.me/c/{chat_id_text[4:]}"
    return None


def mention_chat_link(chat: RegisteredChat) -> str:
    title = mention_chat(chat)
    url = chat_link_url(chat)
    if not url:
        return title
    return f'<a href="{escape(url, quote=True)}">{title}</a>'


def member_status_text(status: object) -> str:
    return str(getattr(status, "value", status))


def permissions_to_dict(permissions: ChatPermissions | None) -> dict:
    if permissions is None:
        return {}
    return permissions.model_dump(exclude_none=True)


def media_locked_permissions() -> ChatPermissions:
    return ChatPermissions(
        can_send_messages=True,
        can_send_audios=False,
        can_send_documents=False,
        can_send_photos=False,
        can_send_videos=False,
        can_send_video_notes=False,
        can_send_voice_notes=False,
        can_send_polls=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False,
        can_react_to_messages=False,
    )


def default_open_permissions() -> ChatPermissions:
    return ChatPermissions(
        can_send_messages=True,
        can_send_audios=True,
        can_send_documents=True,
        can_send_photos=True,
        can_send_videos=True,
        can_send_video_notes=True,
        can_send_voice_notes=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_react_to_messages=True,
    )


def render_quiet_reply(template: str | None, target_name: str, minutes: int, reason: str) -> str:
    text = template or "{user} затих на <b>{minutes}</b> мин.{reason_line}"
    reason_line = f"\nПричина: {escape(reason)}" if reason else ""
    return (
        text.replace("{user}", escape(target_name))
        .replace("{minutes}", str(minutes))
        .replace("{reason}", escape(reason))
        .replace("{reason_line}", reason_line)
    )


def quiet_media_from_message(message: Message) -> tuple[str, str] | None:
    if message.animation:
        return "animation", message.animation.file_id
    if message.voice:
        return "voice", message.voice.file_id
    if message.audio:
        return "audio", message.audio.file_id
    return None


def reply_media_from_message(message: Message) -> tuple[str, str] | None:
    if message.animation:
        return "animation", message.animation.file_id
    if message.voice:
        return "voice", message.voice.file_id
    if message.audio:
        return "audio", message.audio.file_id
    if message.video:
        return "video", message.video.file_id
    if message.video_note:
        return "video_note", message.video_note.file_id
    if message.document:
        mime_type = (message.document.mime_type or "").casefold()
        file_name = (message.document.file_name or "").casefold()
        supported_extensions = (".ogg", ".oga", ".opus", ".mp3", ".wav", ".m4a", ".aac", ".mp4", ".mov", ".webm", ".gif")
        if (
            mime_type.startswith(("audio/", "video/"))
            or mime_type in {"image/gif", "application/ogg", "application/octet-stream"}
            or file_name.endswith(supported_extensions)
        ):
            return "document", message.document.file_id
    return None


async def send_quiet_media(message: Message, media_type: str | None, file_id: str | None) -> None:
    if not media_type or not file_id:
        return
    try:
        if media_type == "animation":
            await message.bot.send_animation(message.chat.id, file_id, reply_to_message_id=message.message_id)
        elif media_type == "voice":
            await message.bot.send_voice(message.chat.id, file_id, reply_to_message_id=message.message_id)
        elif media_type == "audio":
            await message.bot.send_audio(message.chat.id, file_id, reply_to_message_id=message.message_id)
    except (TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter):
        return


async def send_quiet_media_to_chat(
    bot: Bot,
    chat_id: int,
    media_type: str | None,
    file_id: str | None,
    reply_to_message_id: int | None = None,
) -> None:
    if not media_type or not file_id:
        return
    try:
        if media_type == "animation":
            await bot.send_animation(chat_id, file_id, reply_to_message_id=reply_to_message_id)
        elif media_type == "voice":
            await bot.send_voice(chat_id, file_id, reply_to_message_id=reply_to_message_id)
        elif media_type == "audio":
            await bot.send_audio(chat_id, file_id, reply_to_message_id=reply_to_message_id)
    except (TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter):
        return


async def telegram_api_call(bot: Bot, method: str, payload: dict) -> dict:
    url = f"https://api.telegram.org/bot{bot.token}/{method}"
    timeout = aiohttp.ClientTimeout(total=8)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=payload) as response:
            data = await response.json(content_type=None)
            if not data.get("ok"):
                description = data.get("description", "Telegram API error")
                raise TelegramBadRequest(method=method, message=description)
            return data.get("result")


async def telegram_api_get(bot: Bot, method: str) -> dict:
    url = f"https://api.telegram.org/bot{bot.token}/{method}"
    timeout = aiohttp.ClientTimeout(total=8)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as response:
            data = await response.json(content_type=None)
            if not data.get("ok"):
                description = data.get("description", "Telegram API error")
                raise TelegramBadRequest(method=method, message=description)
            return data.get("result")


async def set_chat_available_reactions(bot: Bot, chat_id: int, reactions: list) -> None:
    await telegram_api_call(
        bot,
        "setChatAvailableReactions",
        {
            "chat_id": chat_id,
            "available_reactions": reactions,
        },
    )


async def safe_edit(callback: CallbackQuery, text: str, **kwargs) -> None:
    if not callback.message:
        return
    retry_on_flood = bool(kwargs.pop("retry_on_flood", True))
    if callback.message.text is None:
        with suppress(TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter):
            await callback.message.edit_reply_markup(reply_markup=None)
        with suppress(TelegramBadRequest, TelegramForbiddenError, TelegramNotFound, TelegramRetryAfter):
            await callback.message.answer(text, **kwargs)
        return
    try:
        await callback.message.edit_text(text, **kwargs)
    except TelegramRetryAfter as exc:
        if not retry_on_flood:
            return
        await asyncio.sleep(int(getattr(exc, "retry_after", 3)) + 1)
        try:
            await callback.message.edit_text(text, **kwargs)
        except TelegramBadRequest as retry_exc:
            if "message is not modified" in str(retry_exc).lower():
                return
            if message_edit_target_is_missing(retry_exc):
                with suppress(TelegramBadRequest, TelegramForbiddenError, TelegramNotFound, TelegramRetryAfter):
                    await callback.message.answer(text, **kwargs)
                return
            raise
        except (TelegramForbiddenError, TelegramNotFound, TelegramRetryAfter):
            return
    except TelegramBadRequest as exc:
        error = str(exc).lower()
        if "message is not modified" in error:
            return
        if message_edit_target_is_missing(exc):
            with suppress(TelegramBadRequest, TelegramForbiddenError, TelegramNotFound, TelegramRetryAfter):
                await callback.message.answer(text, **kwargs)
            return
        if "can't parse entities" in error:
            safe_text = escape(unescape(strip_html(text)))
            try:
                await callback.message.edit_text(safe_text, **kwargs)
            except TelegramRetryAfter as retry_after_exc:
                if not retry_on_flood:
                    return
                await asyncio.sleep(int(getattr(retry_after_exc, "retry_after", 3)) + 1)
                with suppress(TelegramBadRequest, TelegramForbiddenError, TelegramNotFound, TelegramRetryAfter):
                    await callback.message.edit_text(safe_text, **kwargs)
            except TelegramBadRequest as retry_exc:
                if message_edit_target_is_missing(retry_exc):
                    with suppress(TelegramBadRequest, TelegramForbiddenError, TelegramNotFound, TelegramRetryAfter):
                        await callback.message.answer(safe_text, **kwargs)
                    return
                raise
            return
        raise


async def safe_reply(message: Message, text: str, **kwargs) -> None:
    try:
        await message.reply(text, **kwargs)
    except TelegramRetryAfter as exc:
        await asyncio.sleep(int(getattr(exc, "retry_after", 3)) + 1)
        try:
            await message.reply(text, **kwargs)
        except (TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter):
            return
    except (TelegramBadRequest, TelegramForbiddenError):
        return


async def send_auto_reply_item(message: Message, item) -> None:
    text = (getattr(item, "text", "") or "").strip()
    media_type = getattr(item, "media_type", None)
    media_file_id = getattr(item, "media_file_id", None)
    if not media_type or not media_file_id:
        if text:
            await safe_reply(message, text, disable_web_page_preview=True)
        return

    caption = text or None
    media_payload = media_file_id
    local_path: Path | None = None
    if isinstance(media_file_id, str) and media_file_id.startswith("local:"):
        local_path = Path(media_file_id.removeprefix("local:"))
        if not local_path.exists():
            await notify_staff_autoreply_change(
                message.bot,
                f"Медиа-триггер «{escape(str(getattr(item, 'trigger', '')))}» не сработал: локальный файл не найден.",
            )
            if text:
                await safe_reply(message, text, disable_web_page_preview=True)
            return
        media_payload = FSInputFile(local_path)
    kwargs = {
        "chat_id": message.chat.id,
        "reply_to_message_id": message.message_id,
    }
    for attempt in range(2):
        try:
            if media_type == "photo":
                await message.bot.send_photo(**kwargs, photo=media_payload, caption=caption)
            elif media_type == "animation":
                await message.bot.send_animation(**kwargs, animation=media_payload, caption=caption)
            elif media_type == "voice":
                await message.bot.send_voice(**kwargs, voice=media_payload, caption=caption)
            elif media_type == "audio":
                await message.bot.send_audio(**kwargs, audio=media_payload, caption=caption)
            elif media_type == "video":
                await message.bot.send_video(**kwargs, video=media_payload, caption=caption)
            elif media_type == "video_note":
                await message.bot.send_video_note(**kwargs, video_note=media_payload)
                if text:
                    await safe_reply(message, text, disable_web_page_preview=True)
            elif media_type == "document":
                await message.bot.send_document(**kwargs, document=media_payload, caption=caption)
            elif text:
                await safe_reply(message, text, disable_web_page_preview=True)
            return
        except TelegramRetryAfter as exc:
            if attempt:
                return
            await asyncio.sleep(int(getattr(exc, "retry_after", 3)) + 1)
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            if media_type == "video":
                document_payload = FSInputFile(local_path) if local_path and local_path.exists() else media_file_id
                try:
                    await message.bot.send_document(
                        **kwargs,
                        document=document_payload,
                        caption=caption,
                    )
                    return
                except (TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter) as document_exc:
                    await notify_staff_autoreply_change(
                        message.bot,
                        (
                            f"Видео-триггер «{escape(str(getattr(item, 'trigger', '')))}» не отправился ни как видео, ни как файл.\n"
                            f"Видео: <code>{escape(str(exc))}</code>\n"
                            f"Файл: <code>{escape(str(document_exc))}</code>"
                        ),
                    )
            else:
                await notify_staff_autoreply_change(
                    message.bot,
                    f"Медиа-триггер «{escape(str(getattr(item, 'trigger', '')))}» не отправился: <code>{escape(str(exc))}</code>",
                )
            if text:
                await safe_reply(message, text, disable_web_page_preview=True)
            return


async def delete_message_later(bot: Bot, chat_id: int, message_id: int, delay_seconds: int = 60) -> None:
    await asyncio.sleep(delay_seconds)
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramRetryAfter as exc:
        await asyncio.sleep(int(getattr(exc, "retry_after", 3)) + 1)
        with suppress(TelegramBadRequest, TelegramForbiddenError, TelegramNotFound, TelegramRetryAfter):
            await bot.delete_message(chat_id, message_id)
    except (TelegramBadRequest, TelegramForbiddenError, TelegramNotFound):
        return


async def delete_message_now_or_later(message: Message) -> bool:
    try:
        await message.delete()
        return True
    except TelegramRetryAfter as exc:
        delay = int(getattr(exc, "retry_after", 3)) + 1
        asyncio.create_task(delete_message_later(message.bot, message.chat.id, message.message_id, delay))
        return True
    except (TelegramBadRequest, TelegramForbiddenError, TelegramNotFound):
        return False


async def temporary_reply(message: Message, text: str, delay_seconds: int = 60, **kwargs) -> None:
    try:
        sent = await message.reply(text, **kwargs)
    except TelegramRetryAfter as exc:
        await asyncio.sleep(int(getattr(exc, "retry_after", 3)) + 1)
        try:
            sent = await message.reply(text, **kwargs)
        except (TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter):
            return
    except (TelegramBadRequest, TelegramForbiddenError):
        return

    asyncio.create_task(delete_message_later(message.bot, sent.chat.id, sent.message_id, delay_seconds))


def schedule_message_delete(message: Message | None, delay_seconds: int = 60) -> None:
    if not message:
        return
    asyncio.create_task(delete_message_later(message.bot, message.chat.id, message.message_id, delay_seconds))


async def temporary_chat_notice(message: Message, text: str, delay_seconds: int = 60, **kwargs) -> None:
    try:
        sent = await message.bot.send_message(message.chat.id, text, **kwargs)
    except TelegramRetryAfter as exc:
        await asyncio.sleep(int(getattr(exc, "retry_after", 3)) + 1)
        try:
            sent = await message.bot.send_message(message.chat.id, text, **kwargs)
        except (TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter):
            return
    except (TelegramBadRequest, TelegramForbiddenError):
        return

    asyncio.create_task(delete_message_later(message.bot, sent.chat.id, sent.message_id, delay_seconds))


async def safe_reply_chunks(message: Message, lines: list[str], limit: int = 3800, **kwargs) -> None:
    chunk: list[str] = []
    size = 0
    for line in lines:
        line_size = len(line) + 1
        if chunk and size + line_size > limit:
            await safe_reply(message, "\n".join(chunk), **kwargs)
            chunk = []
            size = 0
        chunk.append(line)
        size += line_size
    if chunk:
        await safe_reply(message, "\n".join(chunk), **kwargs)


async def restart_process(delay_seconds: float = 1.0) -> None:
    await asyncio.sleep(delay_seconds)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)
    os.execv(sys.executable, [sys.executable, "-m", "app.bot"])


def restart_panel_path() -> str:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, "restart_panel_chat.txt")


def remember_restart_panel_chat(chat_id: int) -> None:
    with open(restart_panel_path(), "w", encoding="utf-8") as file:
        file.write(str(chat_id))


async def send_restart_panel_if_needed(bot: Bot) -> None:
    path = restart_panel_path()
    if not os.path.exists(path):
        return

    try:
        with open(path, "r", encoding="utf-8") as file:
            chat_id = int(file.read().strip())
    except (OSError, ValueError):
        try:
            os.remove(path)
        except OSError:
            pass
        return

    try:
        await bot.send_message(
            chat_id,
            "Бот перезапущен. Панель управления снова открыта.",
            reply_markup=main_menu(),
        )
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


async def clear_previous_control_buttons(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    control_chat_id = data.get("control_chat_id")
    control_message_id = data.get("control_message_id")
    if not isinstance(control_chat_id, int) or not isinstance(control_message_id, int):
        return

    try:
        await message.bot.edit_message_reply_markup(
            chat_id=control_chat_id,
            message_id=control_message_id,
            reply_markup=None,
        )
    except (TelegramBadRequest, TelegramForbiddenError):
        return


async def is_chat_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        return False
    return member.status in ADMIN_STATUSES or member_status_text(member.status) in ADMIN_STATUS_TEXTS


async def is_alarm_restriction_exempt(bot: Bot, chat_id: int, user_id: int | None) -> bool:
    if user_id is None:
        return True
    return await is_chat_admin(bot, chat_id, user_id)


async def has_chat_admin_permission(bot: Bot, chat_id: int, user_id: int, permission: str) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        return False
    status = member_status_text(member.status)
    if status == "creator":
        return True
    return status == "administrator" and bool(getattr(member, permission, False))


async def resolve_command_target(message: Message, username: str | None) -> tuple[int | None, str | None, str | None]:
    if username:
        user = db.get_seen_user_by_username(message.chat.id, username)
        if not user:
            return None, None, (
                f"Я еще не видел @{escape(username)} в этой группе. "
                "Ответь командой на сообщение пользователя или дождись, пока он напишет в чат."
            )
        name = f"@{user.username}" if user.username else user.full_name
        return user.user_id, name, None

    if not message.reply_to_message or not message.reply_to_message.from_user:
        return None, None, "Нужно ответить командой на сообщение пользователя или написать команду через @username."

    user = message.reply_to_message.from_user
    db.upsert_seen_user(
        chat_id=message.chat.id,
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        is_bot=user.is_bot,
    )
    name = f"@{user.username}" if user.username else user.full_name
    return user.id, name, None


async def actor_moderation_role(bot: Bot, chat_id: int, user_id: int) -> str | None:
    if is_bot_admin(user_id) or is_miniapp_admin_user(user_id) or await is_chat_admin(bot, chat_id, user_id):
        return "admin"
    row = db.get_chat_moderator_role(chat_id, user_id)
    return str(row["role"]) if row else None


async def actor_can_manage_moderators(bot: Bot, chat_id: int, user_id: int) -> bool:
    return is_bot_admin(user_id)


async def manageable_moderation_chats(bot: Bot, user_id: int) -> list[RegisteredChat]:
    if is_bot_admin(user_id):
        return db.list_chats()
    roles = await user_admin_roles(bot, user_id)
    return [chat for chat, _status in roles]


async def resolve_private_moderation_chat(bot: Bot, user_id: int, requested_chat_id: int | None) -> tuple[RegisteredChat | None, str | None]:
    chats = await manageable_moderation_chats(bot, user_id)
    if requested_chat_id is not None:
        chat = db.get_chat(requested_chat_id)
        if chat is None:
            return None, "Я не знаю такой chat_id. Сначала зарегистрируй группу или дождись активности бота в ней."
        if not any(item.chat_id == requested_chat_id for item in chats):
            return None, "У тебя нет прав назначать модераторов в этой группе."
        return chat, None
    if not chats:
        return None, "У тебя нет групп, где можно назначать модераторов через бота."
    if len(chats) == 1:
        return chats[0], None
    lines = ["У тебя несколько групп. Укажи chat_id в команде:", ""]
    lines.extend(f"<code>{chat.chat_id}</code> — {escape(chat.title)}" for chat in chats[:20])
    lines.append("\nПример: <code>+модератор -1001234567890 @username неделя</code>")
    return None, "\n".join(lines)


def render_moderation_actor(message: Message, role: str | None) -> str:
    if not message.from_user:
        return "unknown"
    username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
    if role == "admin":
        return f"{username} [админ]"
    return f"{username} [{moderator_role_title(role, short=True)}]"


def moderator_admin_panel_text(chat: RegisteredChat) -> str:
    rows = db.list_chat_moderators(chat.chat_id)
    rows.sort(key=lambda row: (-moderator_role_rank(str(row["role"])), str(row["full_name"]).casefold()))
    lines = [
        f"Группа: <b>{mention_chat(chat)}</b>",
        "",
        "<b>Модераторы чата</b>",
        "Назначение доступно владельцу бота. Ввод: <code>@username</code> или numeric id.",
    ]
    if not rows:
        lines.append("\nПока модераторов нет.")
    else:
        lines.append("\n<b>Список:</b>")
        for row in rows:
            name = f"@{row['username']}" if row["username"] else row["full_name"]
            expires = f", до {row['expires_at']}" if row.get("expires_at") else ""
            votes = int(row.get("votes_count") or 0)
            lines.append(f"• {escape(str(name))} — <b>{moderator_role_title(str(row['role']))}</b>, голосов: {votes}{escape(expires)}")
    return "\n".join(lines)


async def resolve_quiet_panel_target(bot: Bot, chat_id: int, target: str) -> tuple[int | None, str | None, str | None]:
    if target.startswith("@"):
        username = normalize_username(target)
        user = db.get_seen_user_by_username(chat_id, username)
        if not user:
            return None, None, (
                f"Я еще не видел @{escape(username)} в этой группе. "
                "Можно указать numeric id пользователя или дождаться, пока он напишет в чат."
            )
        name = f"@{user.username}" if user.username else user.full_name
        return user.user_id, name, None

    if not target.isdigit():
        return None, None, "Первым укажи @username или numeric id пользователя."

    user_id = int(target)
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        return None, None, f"Не получилось найти пользователя по id в этой группе.\n<code>{escape(str(exc))}</code>"

    user = member.user
    if user.is_bot:
        return None, None, "Ботов этой командой ограничивать не нужно."
    db.upsert_seen_user(
        chat_id=chat_id,
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        is_bot=user.is_bot,
    )
    name = f"@{user.username}" if user.username else user.full_name
    return user.id, name, None


def is_bot_admin(user_id: int | None) -> bool:
    return user_id is not None and user_id in BOT_ADMIN_IDS


def admin_permission_key(feature: str, mode: str) -> str:
    normalized_mode = mode if mode in {"view", "write"} else "write"
    return f"{feature}.{normalized_mode}"


def bot_admin_feature_allowed(chat_id: int, user_id: int | None, feature: str, mode: str = "write", default: bool = True) -> bool:
    if user_id is None:
        return False
    if is_bot_admin(user_id):
        return True
    if feature not in ADMIN_PERMISSION_IDS:
        return False
    mode_value = db.admin_feature_permission(chat_id, user_id, admin_permission_key(feature, mode))
    if mode_value is not None:
        return mode_value
    if db.has_admin_feature_permission(chat_id, user_id, admin_permission_key(feature, "view")) or db.has_admin_feature_permission(
        chat_id, user_id, admin_permission_key(feature, "write")
    ):
        return False
    legacy_value = db.admin_feature_permission(chat_id, user_id, feature)
    if legacy_value is not None:
        return legacy_value
    if "." not in feature:
        return default
    parent = feature.split(".", 1)[0]
    parent_mode_value = db.admin_feature_permission(chat_id, user_id, admin_permission_key(parent, mode))
    if parent_mode_value is not None:
        return parent_mode_value
    if db.has_admin_feature_permission(chat_id, user_id, admin_permission_key(parent, "view")) or db.has_admin_feature_permission(
        chat_id, user_id, admin_permission_key(parent, "write")
    ):
        return False
    return db.admin_feature_allowed(chat_id, user_id, parent, default=default)


async def require_callback_feature(
    callback: CallbackQuery,
    feature: str,
    mode: str = "write",
    default: bool = True,
    chat_id: int | None = None,
) -> bool:
    scoped_chat_id = chat_id
    if scoped_chat_id is None:
        scoped_chat_id = next((int(part) for part in callback.data.split(":") if part.startswith("-") and part[1:].isdigit()), None)
    if scoped_chat_id is not None and bot_admin_feature_allowed(scoped_chat_id, callback.from_user.id, feature, mode=mode, default=default):
        return True
    await callback.answer("Нет доступа к этой функции.", show_alert=True)
    return False


def access_permissions_menu(chat_id: int, user_id: int, page: int = 0) -> InlineKeyboardMarkup:
    page_size = 7
    permissions: list[tuple[str, str, bool]] = []
    for feature_id, title in ADMIN_FEATURES:
        permissions.append((feature_id, title, False))
        permissions.extend((child_id, child_title, True) for child_id, child_title in ADMIN_SUBFEATURES.get(feature_id, []))

    max_page = max(0, (len(permissions) - 1) // page_size)
    page = max(0, min(page, max_page))
    start = page * page_size
    rows: list[list[InlineKeyboardButton]] = []
    for feature_id, title, is_child in permissions[start : start + page_size]:
        view_allowed = bot_admin_feature_allowed(chat_id, user_id, feature_id, mode="view", default=False)
        write_allowed = bot_admin_feature_allowed(chat_id, user_id, feature_id, mode="write", default=False)
        view_mark = "✅" if view_allowed else "❌"
        write_mark = "✅" if write_allowed else "❌"
        title_prefix = "↳ " if is_child else ""
        write_title = "нажимать" if is_child else "менять"
        rows.append(
            [
                InlineKeyboardButton(text=f"{title_prefix}{title}", callback_data=f"access:noop:{chat_id}:{user_id}"),
                InlineKeyboardButton(text=f"{view_mark} читать", callback_data=f"access:set:{chat_id}:{user_id}:{feature_id}:view:{page}"),
                InlineKeyboardButton(text=f"{write_mark} {write_title}", callback_data=f"access:set:{chat_id}:{user_id}:{feature_id}:write:{page}"),
            ]
        )
    if max_page > 0:
        rows.append(
            [
                InlineKeyboardButton(text="в†ђ", callback_data=f"access:page:{chat_id}:{user_id}:{max(0, page - 1)}"),
                InlineKeyboardButton(text=f"{page + 1}/{max_page + 1}", callback_data=f"access:noop:{chat_id}:{user_id}"),
                InlineKeyboardButton(text="в†’", callback_data=f"access:page:{chat_id}:{user_id}:{min(max_page, page + 1)}"),
            ]
        )
    rows.append([InlineKeyboardButton(text="Админы группы", callback_data=f"act:access:{chat_id}")])
    rows.append([InlineKeyboardButton(text="Назад к настройкам", callback_data=f"chat:{chat_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def access_admins_menu(bot: Bot, chat_id: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    try:
        members = await bot.get_chat_administrators(chat_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        members = []
    for member in members:
        user = member.user
        if user.is_bot:
            continue
        title = user.full_name
        if user.username:
            title = f"{title} (@{user.username})"
        rows.append([InlineKeyboardButton(text=title, callback_data=f"access:user:{chat_id}:{user.id}")])
    if not rows:
        rows.append([InlineKeyboardButton(text="Не удалось прочитать админов", callback_data=f"chat:{chat_id}")])
    rows.append([InlineKeyboardButton(text="Назад к настройкам", callback_data=f"chat:{chat_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def participant_since_date(period: str) -> str | None:
    today = datetime.now(timezone.utc).date()
    if period == "day":
        return today.isoformat()
    if period == "week":
        return (today - timedelta(days=6)).isoformat()
    if period == "month":
        return (today - timedelta(days=29)).isoformat()
    if period == "all":
        return None
    return today.isoformat()


def participant_top_text(chat_id: int, period: str) -> str:
    labels = {"day": "день", "week": "неделю", "month": "месяц", "all": "все время"}
    items = db.top_participant_activity(chat_id, since_date=participant_since_date(period), limit=20)
    lines = [f"<b>Топ участников за {escape(labels.get(period, period))}</b>"]
    if not items:
        lines.append("\nПока нет данных. Топ начнет заполняться с новых сообщений после обновления.")
        return "\n".join(lines)
    for index, item in enumerate(items, start=1):
        name = f"@{item.username}" if item.username else item.full_name
        lines.append(f"{index}. {escape(name)} - <b>{item.messages_count}</b> сообщений")
    return "\n".join(lines)


async def admin_chats_for_user(bot: Bot, user_id: int) -> list[RegisteredChat]:
    return db.list_chats() if is_bot_admin(user_id) else []


async def is_chat_member(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        return False
    return member_status_text(member.status) not in {"left", "kicked"}


async def paid_chats_for_user(bot: Bot, user_id: int) -> list[RegisteredChat]:
    chats: list[RegisteredChat] = []
    for chat in db.list_chats():
        if await is_chat_member(bot, chat.chat_id, user_id):
            chats.append(chat)
    return chats


async def user_admin_roles(bot: Bot, user_id: int) -> list[tuple[RegisteredChat, str]]:
    roles: list[tuple[RegisteredChat, str]] = []
    for chat in db.list_chats():
        try:
            member = await bot.get_chat_member(chat.chat_id, user_id)
        except (TelegramBadRequest, TelegramForbiddenError):
            continue

        status = member_status_text(member.status)
        if member.status in ADMIN_STATUSES or status in ADMIN_STATUS_TEXTS:
            roles.append((chat, status))

    return roles


def configured_server_urls() -> list[str]:
    urls: list[str] = []
    for key in (
        "APP_SERVER_URL",
        "APP_PUBLIC_URL",
        "PUBLIC_BASE_URL",
        "ADMIN_PUBLIC_URL",
        "SERVER_PUBLIC_URL",
    ):
        value = os.getenv(key, "").strip().rstrip("/")
        if value and value not in urls:
            urls.append(value)
    return urls


def public_miniapp_url() -> str:
    """Return the HTTPS URL used by Telegram's native bot menu button."""
    url = os.getenv("MINI_APP_URL", "").strip().rstrip("/")
    if url:
        return url
    base = os.getenv("ADMIN_PUBLIC_URL", "").strip().rstrip("/")
    return f"{base}/miniapp" if base else ""


async def configure_miniapp_menu_button(bot: Bot) -> None:
    """Expose the Mini App in the Telegram input-area menu for private chats."""
    url = public_miniapp_url()
    if not url:
        logging.warning("Mini App menu button is not configured: set MINI_APP_URL in .env")
        return
    if not url.lower().startswith("https://"):
        logging.warning("Mini App menu button requires an HTTPS URL: %s", url)
        return
    try:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Шахта",
                web_app=WebAppInfo(url=url),
            )
        )
        logging.info("Mini App menu button configured: %s", url)
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        logging.warning("Could not configure Mini App menu button: %s", exc)


def local_ipv4_addresses() -> list[str]:
    addresses: list[str] = []

    def add_ip(ip: str) -> None:
        if ip and not ip.startswith("127.") and ip not in addresses:
            addresses.append(ip)

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.5)
            sock.connect(("8.8.8.8", 80))
            add_ip(sock.getsockname()[0])
    except OSError:
        pass

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            add_ip(info[4][0])
    except OSError:
        pass

    return addresses


def is_private_or_local_ip(ip: str) -> bool:
    try:
        parsed = ip_address(ip)
    except ValueError:
        return True
    return parsed.is_private or parsed.is_loopback or parsed.is_link_local or parsed.is_reserved or parsed.is_multicast


async def detect_public_ip() -> str | None:
    try:
        timeout = aiohttp.ClientTimeout(total=4)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://api.ipify.org?format=json") as response:
                if response.status != 200:
                    return None
                data = await response.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, OSError):
        return None
    ip = str(data.get("ip") or "").strip()
    return ip or None


def server_address_text(public_ip: str | None = None) -> str:
    lines = ["<b>Адрес сервера для приложения</b>"]
    configured_urls = configured_server_urls()
    if configured_urls:
        lines.append("\n<b>Из настроек:</b>")
        lines.extend(f"<code>{escape(url)}</code>" for url in configured_urls)

    public_hosts: list[str] = []
    if public_ip and not is_private_or_local_ip(public_ip):
        public_hosts.append(public_ip)

    if public_hosts:
        lines.append("\n<b>Пробуй в приложении:</b>")
        for host in public_hosts:
            safe_host = escape(host)
            lines.append(f"<code>http://{safe_host}:50000</code>")
            lines.append(f"<code>http://{safe_host}:8000</code>")
    elif not configured_urls:
        lines.append("\nВнешний IP не удалось определить автоматически.")

    local_hosts: list[str] = []
    if public_ip and is_private_or_local_ip(public_ip):
        local_hosts.append(public_ip)
    for ip in local_ipv4_addresses():
        if ip not in local_hosts:
            local_hosts.append(ip)

    if not public_hosts and local_hosts:
        lines.append("\n<b>Локальные адреса для диагностики:</b>")
        for host in local_hosts[:3]:
            lines.append(f"<code>{escape(host)}</code>")

    lines.append("\nОбычно для приложения нужен внешний адрес и порт <b>50000</b>. Если не открылся, попробуй <b>8000</b>.")
    return "\n".join(lines)


async def can_view_server_address(bot: Bot, user_id: int | None) -> bool:
    if user_id is None:
        return False
    if is_bot_admin(user_id):
        return True
    return bool(await user_admin_roles(bot, user_id))


async def main_menu_for_user(bot: Bot, user_id: int | None) -> InlineKeyboardMarkup:
    return main_menu()


async def chat_is_forum(bot: Bot, chat_id: int) -> bool:
    try:
        chat = await bot.get_chat(chat_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        return False
    return bool(getattr(chat, "is_forum", False))


async def require_admin(message: Message) -> bool:
    if not message.from_user:
        await message.answer("Не могу определить пользователя. Выполните команду от своего аккаунта администратора.")
        return False

    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        await message.answer("Эту команду нужно выполнить внутри группы или группы обсуждений, прикрепленной к каналу.")
        return False

    if not is_bot_admin(message.from_user.id):
        await message.answer("Административные команды Telegram-бота доступны только владельцу. Используй приложение.")
        return False

    return True


async def require_selected_admin(callback: CallbackQuery, chat_id: int) -> RegisteredChat | None:
    chat = db.get_chat(chat_id)
    if chat is None:
        await callback.answer("Группа не найдена. Сначала зарегистрируйте ее.", show_alert=True)
        return None

    if not is_bot_admin(callback.from_user.id):
        await callback.answer("Админ-панель Telegram-бота доступна только владельцу.", show_alert=True)
        return None

    return chat


async def require_state_admin(message: Message, state: FSMContext) -> int | None:
    data = await state.get_data()
    chat_id = data.get("chat_id")
    if not isinstance(chat_id, int):
        await state.clear()
        await message.answer("Группа не выбрана. Открой /start и выбери группу.", reply_markup=main_menu())
        return None

    if not message.from_user or not is_bot_admin(message.from_user.id):
        await state.clear()
        await message.answer("Настройка отменена: админ-панель Telegram-бота доступна только владельцу.")
        return None

    state_name = await state.get_state()
    state_key = state_name.rsplit(":", 1)[-1] if state_name else ""
    feature = STATE_FEATURES.get(state_key)
    if feature and not bot_admin_feature_allowed(chat_id, message.from_user.id, feature, default=True):
        await state.clear()
        await message.answer("Настройка отменена: у тебя нет доступа к этой функции.")
        return None

    return chat_id


async def register_current_chat(message: Message) -> None:
    db.upsert_chat(
        chat_id=message.chat.id,
        title=chat_title(message.chat),
        chat_type=message.chat.type,
        username=message.chat.username,
    )


async def remember_sender(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES or not message.from_user:
        return

    now = time.monotonic()
    chat_id = message.chat.id
    chat_seen_at = REMEMBERED_CHATS.get(chat_id, 0)
    if now - chat_seen_at >= SENDER_CACHE_SECONDS:
        await register_current_chat(message)
        REMEMBERED_CHATS[chat_id] = now

    user_key = (
        chat_id,
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name,
        message.from_user.is_bot,
    )
    user_seen_at = REMEMBERED_USERS.get(user_key, 0)
    if now - user_seen_at >= SENDER_CACHE_SECONDS:
        db.upsert_seen_user(
            chat_id=chat_id,
            user_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
            is_bot=message.from_user.is_bot,
        )
        REMEMBERED_USERS[user_key] = now

    activity_key = (chat_id, message.from_user.id)
    activity_seen_at = PARTICIPANT_ACTIVITY_TOUCHES.get(activity_key, 0)
    if not message.from_user.is_bot and now - activity_seen_at >= ACTIVITY_CACHE_SECONDS:
        db.increment_participant_activity(chat_id, message.from_user.id)
        PARTICIPANT_ACTIVITY_TOUCHES[activity_key] = now

    thread_id = message.message_thread_id
    is_real_topic = bool(getattr(message.chat, "is_forum", False) and getattr(message, "is_topic_message", False))
    if thread_id is not None and is_real_topic and (chat_id, thread_id) not in KNOWN_TOPICS:
        topic_name = None
        if message.reply_to_message and message.reply_to_message.forum_topic_created:
            topic_name = message.reply_to_message.forum_topic_created.name
        elif message.forum_topic_created:
            topic_name = message.forum_topic_created.name
        elif message.forum_topic_edited and message.forum_topic_edited.name:
            topic_name = message.forum_topic_edited.name
        if topic_name:
            db.upsert_topic(message.chat.id, thread_id, topic_name)
        else:
            db.upsert_topic(message.chat.id, thread_id, "Без названия", preserve_existing=True)
        KNOWN_TOPICS.add((chat_id, thread_id))


@router.my_chat_member()
async def bot_membership_changed(event: ChatMemberUpdated) -> None:
    old_status = member_status_text(event.old_chat_member.status)
    new_status = member_status_text(event.new_chat_member.status)
    active_statuses = {"member", "administrator", "creator"}
    if old_status not in active_statuses and new_status in active_statuses:
        db.upsert_chat(event.chat.id, event.chat.title or "Без названия", event.chat.type, event.chat.username)
        action = "Добавил бота в чат"
    elif old_status in active_statuses and new_status not in active_statuses:
        action = "Удалил бота из чата"
    else:
        action = "Изменил права бота в чате"
    db.add_audit_log(
        "Telegram",
        action,
        chat_id=event.chat.id,
        actor_id=event.from_user.id,
        actor_username=event.from_user.username,
        actor_name=event.from_user.full_name,
        details=f"{old_status} в†’ {new_status}",
    )


def replies_text(chat_id: int) -> str:
    replies = db.list_replies(chat_id)
    triggers = db.list_triggers(chat_id)
    lines = ["<b>Настроенные ответы:</b>"]
    if not replies and not triggers:
        lines.append("Пока ничего не настроено.")

    if replies:
        lines.append("\n<b>Ответы на @username:</b>")
        for item in replies:
            media = f" [{escape(item.media_type)}]" if item.media_type else ""
            lines.append(f"@{escape(item.username)}{media} - {preview_html(item.text)}")

    if triggers:
        lines.append("\n<b>Фиксированные ответы:</b>")
        for item in triggers:
            media = f" [{escape(item.media_type)}]" if item.media_type else ""
            lines.append(f"{escape(item.trigger)}{media} - {preview_html(item.text)}")

    return "\n".join(lines)


def trigger_page_text(chat_id: int, page: int) -> tuple[str, int, int]:
    triggers = db.list_triggers(chat_id)
    total = len(triggers)
    max_page = max(0, (total - 1) // TRIGGERS_PAGE_SIZE)
    page = max(0, min(page, max_page))
    start = page * TRIGGERS_PAGE_SIZE
    page_items = triggers[start : start + TRIGGERS_PAGE_SIZE]

    lines = [f"<b>Фиксированные ответы</b>"]
    if not page_items:
        lines.append("Пока нет фиксированных ответов.")
    else:
        lines.append(f"Страница {page + 1}/{max_page + 1}. Всего: {total}.")
        for offset, item in enumerate(page_items, start=start + 1):
            media = f" [{escape(item.media_type)}]" if item.media_type else ""
            lines.append(f"{offset}. <b>{escape(item.trigger)}</b>{media} - {preview_html(item.text)}")

    return "\n".join(lines), page, total


def quote_page_text(chat_id: int, page: int) -> tuple[str, int, int]:
    quotes = db.list_quotes(chat_id)
    total = len(quotes)
    max_page = max(0, (total - 1) // QUOTES_PAGE_SIZE)
    page = max(0, min(page, max_page))
    start = page * QUOTES_PAGE_SIZE
    page_items = quotes[start : start + QUOTES_PAGE_SIZE]

    lines = ["<b>Цитаты</b>"]
    if not page_items:
        lines.append("Пока нет сохраненных цитат.")
    else:
        lines.append(f"Страница {page + 1}/{max_page + 1}. Всего: {total}.")
        for offset, quote in enumerate(page_items, start=start + 1):
            author = f" — {escape(quote.author_name)}" if quote.author_name else ""
            lines.append(f"{offset}. {preview_html(quote.text, limit=100)}{author}")

    return "\n".join(lines), page, total


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    if message.chat.type == "private":
        start_parts = (message.text or "").split(maxsplit=1)
        if len(start_parts) == 2 and start_parts[1] in {"miniapp_mine", "miniapp_shop"}:
            view = "shop" if start_parts[1] == "miniapp_shop" else "mine"
            title = "Магазин шахты" if view == "shop" else "Шахта"
            await state.clear()
            await message.answer(
                f"<b>{title}</b>\n\nНажми кнопку ниже, чтобы открыть нужный раздел.",
                reply_markup=miniapp_private_menu(f"Открыть: {title}", view=view),
            )
            return
        if len(start_parts) == 2 and start_parts[1] in {"youtube", "youtube_music", "instagram"}:
            service_name = {"youtube_music": "YouTube Music", "instagram": "Instagram Reels"}.get(start_parts[1], "YouTube")
            await state.clear()
            await message.answer(
                f"<b>Скачать с {service_name}</b>\n\n"
                "Пришлите публичную ссылку на контент, который вам разрешено скачивать. Бот проверит её и покажет доступные форматы.\n"
                "Скачивание не начнётся до выбора формата.",
                reply_markup=media_cancel_menu(),
                disable_web_page_preview=True,
            )
            return
        if len(start_parts) == 2 and start_parts[1].startswith("media_") and message.from_user:
            task_type = start_parts[1][len("media_"):]
            if task_type in TASK_TITLES:
                if not premium_service.has_active_premium(message.from_user.id):
                    await message.answer("Для этой функции нужен Premium.", reply_markup=premium_menu())
                    return
                await state.set_state(MediaInput.waiting_file)
                await state.update_data(media_task_type=task_type)
                await message.answer(
                    f"<b>{escape(TASK_TITLES[task_type])}</b>\n\nПришлите видео, аудио, голосовое сообщение или файл.",
                    reply_markup=media_cancel_menu(),
                )
                return
        login_id = parse_app_login_start_payload(message.text)
        if login_id is not None and message.from_user:
            await message.answer(
                "<b>Запрос входа в MonkeyDin</b>\n\n"
                "Подтверждай только если ты сам прямо сейчас начал вход в приложении. "
                "Пересланная ссылка может дать отправителю доступ к твоему профилю.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Подтвердить вход", callback_data=f"app_login:{login_id}")],
                    [InlineKeyboardButton(text="Отмена", callback_data="ui:home")],
                ]),
            )
            return
        chat_id = parse_donate_start_payload(message.text)
        if chat_id is not None and message.from_user:
            chat = db.get_chat(chat_id)
            if chat is None:
                await message.answer("Группа для покупок шахты больше не найдена.", reply_markup=main_menu())
                return
            if not await is_chat_member(message.bot, chat_id, message.from_user.id):
                await message.answer("Покупки шахты доступны только участникам выбранной группы.", reply_markup=main_menu())
                return
            if db.get_dig_player(chat_id, message.from_user.id) is None:
                await message.answer("Сначала зарегистрируйся в шахте командой копай внутри группы.", reply_markup=main_menu())
                return
            await message.answer(
                f"<b>Покупки шахты за Stars переехали в Mini App</b>\n"
                f"Группа: <b>{mention_chat(chat)}</b>\n\n"
                "Открой магазин шахты — вкладка <b>Покупки за Stars</b> теперь там.",
                reply_markup=miniapp_private_menu("Открыть магазин", view="shop"),
            )
            return
        await message.answer(
            "Выбери раздел.",
            reply_markup=await main_menu_for_user(message.bot, message.from_user.id if message.from_user else None),
        )
        return

    await remember_sender(message)
    await message.answer(
        "Группа зарегистрирована. Управление группой выполняется через приложение Abstergo."
    )


@router.message(Command("settings"))
async def settings(message: Message) -> None:
    if message.chat.type == "private":
        await show_chat_select(message)
        return

    await remember_sender(message)
    if message.from_user and is_bot_admin(message.from_user.id):
        await message.answer("Открой личку с ботом и нажми /start, чтобы открыть панель владельца.")
    else:
        await message.answer("Управление группой выполняется через приложение Abstergo.")


@router.message(Command("id"))
async def show_user_id(message: Message) -> None:
    if not message.from_user:
        await message.answer("Не могу определить твой Telegram id.")
        return

    await message.answer(f"Твой Telegram id: <code>{message.from_user.id}</code>")


@router.message(Command("gift"))
async def gift_command(message: Message, state: FSMContext) -> None:
    await start_gift_flow(message, state, split_command_payload(message.text))


@router.message(F.text.casefold() == "/старт")
async def start_ru(message: Message, state: FSMContext) -> None:
    await start(message, state)


@router.message(F.text.casefold() == "/настройки")
async def settings_ru(message: Message) -> None:
    await settings(message)


@router.message(Command("register_chat"))
async def register_chat(message: Message) -> None:
    if not await require_admin(message):
        return
    await remember_sender(message)
    await message.answer(f"Группа зарегистрирована: <b>{escape(chat_title(message.chat))}</b>")


@router.message(F.text.casefold() == "/регистрация")
async def register_chat_ru(message: Message) -> None:
    await register_chat(message)


async def show_chat_select(message: Message) -> None:
    if not message.from_user:
        await message.answer("Не могу определить пользователя.", reply_markup=main_menu())
        return

    chats = await admin_chats_for_user(message.bot, message.from_user.id)
    if not chats:
        await message.answer(
            "Админ-панель Telegram-бота доступна только владельцу. Для управления группой используй приложение.",
            reply_markup=main_menu(),
        )
        return

    await message.answer("Выбери группу для настройки:", reply_markup=chat_select_menu(chats))


def telegram_user_profile_text(
    user_id: int,
    username: str | None,
    full_name: str,
    chat_id: int | None = None,
    short: bool = True,
) -> str:
    profile = build_user_profile(db, premium_service, user_id, username, full_name, chat_id=chat_id)
    return profile_chat_text(profile, short=short)


def social_profile_markup(chat_id: int, viewer_id: int, target_id: int) -> InlineKeyboardMarkup:
    return social_profile_menu(
        chat_id,
        viewer_id,
        target_id,
        db.friendship_state(chat_id, viewer_id, target_id),
        db.couple_state(chat_id, viewer_id, target_id),
    )


def secret_message_markup(message_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть скрытое сообщение", callback_data=f"sec:open:{message_id}")]
        ]
    )


def has_secret_message_compose(message: Message) -> bool:
    return bool(message.from_user and db.get_secret_message_compose_for_sender(message.from_user.id))


async def active_social_user(bot: Bot, chat_id: int, user_id: int) -> User | None:
    member = await get_active_chat_member(bot, chat_id, user_id)
    if member is None or is_deleted_or_empty_user(member.user):
        return None
    db.upsert_seen_user(
        chat_id,
        member.user.id,
        member.user.username,
        member.user.full_name,
        member.user.is_bot,
    )
    return member.user


def social_callback_ids(callback: CallbackQuery) -> tuple[str, int, int, int] | None:
    parts = (callback.data or "").split(":")
    if len(parts) != 5 or parts[0] != "soc":
        return None
    try:
        return parts[1], int(parts[2]), int(parts[3]), int(parts[4])
    except ValueError:
        return None


@router.callback_query(F.data.startswith("app_login:"))
async def confirm_app_login(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.data:
        return
    login_id = callback.data.partition(":")[2]
    approved = db.approve_user_login(
        login_id,
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.full_name,
    )
    await callback.answer("Вход подтверждён." if approved else "Ссылка устарела.", show_alert=not approved)
    if callback.message:
        await callback.message.edit_text(
            "Вход в приложение подтверждён. Вернись в MonkeyDin."
            if approved
            else "Ссылка входа устарела или уже использована.",
            reply_markup=await main_menu_for_user(callback.bot, callback.from_user.id),
        )


@router.callback_query(F.data == "ui:home")
async def cb_home(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_edit(callback, "Панель управления ботом.", reply_markup=await main_menu_for_user(callback.bot, callback.from_user.id))
    await callback.answer()


@router.callback_query(F.data == "ui:chats")
async def cb_chats(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    chats = await admin_chats_for_user(callback.bot, callback.from_user.id)
    if not chats:
        await safe_edit(
            callback,
            "Админ-панель Telegram-бота доступна только владельцу. Для управления группой используй приложение.",
            reply_markup=await main_menu_for_user(callback.bot, callback.from_user.id),
        )
        await callback.answer()
        return

    await safe_edit(callback, "Панель владельца.", reply_markup=admin_menu())
    await callback.answer()


@router.callback_query(F.data == "ui:chat_select")
async def cb_chat_select(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    chats = await admin_chats_for_user(callback.bot, callback.from_user.id)
    if not chats:
        await safe_edit(
            callback,
            "Админ-панель Telegram-бота доступна только владельцу. Для управления группой используй приложение.",
            reply_markup=admin_back_menu(),
        )
        await callback.answer()
        return

    await safe_edit(callback, "Выбери группу для настройки:", reply_markup=chat_select_menu(chats))
    await callback.answer()


@router.callback_query(F.data == "user:chats")
async def cb_user_chats(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    chats = await paid_chats_for_user(callback.bot, callback.from_user.id)
    if not chats:
        await safe_edit(
            callback,
            "Нет доступных групп. Сначала вступи в группу, где есть бот.",
            reply_markup=await main_menu_for_user(callback.bot, callback.from_user.id),
        )
        await callback.answer()
        return

    await safe_edit(callback, "Выбери группу:", reply_markup=user_chat_select_menu(chats))
    await callback.answer()


@router.callback_query(F.data.startswith("user:chat:"))
async def cb_user_chat(callback: CallbackQuery) -> None:
    chat_id = int(callback.data.split(":", 2)[2])
    chat = db.get_chat(chat_id)
    if chat is None:
        await callback.answer("Группа не найдена.", show_alert=True)
        return
    if not await is_chat_member(callback.bot, chat_id, callback.from_user.id):
        await callback.answer("Ты больше не состоишь в этой группе.", show_alert=True)
        return

    await safe_edit(
        callback,
        f"Пользовательский раздел.\nГруппа: <b>{mention_chat(chat)}</b>",
        reply_markup=user_menu(chat_id),
    )
    await callback.answer()


@router.callback_query(F.data == "profile:me")
async def cb_profile_me(callback: CallbackQuery) -> None:
    text = telegram_user_profile_text(
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.full_name,
        short=False,
    )
    await safe_edit(callback, text, reply_markup=await main_menu_for_user(callback.bot, callback.from_user.id))
    await callback.answer()


@router.callback_query(F.data == "server:ip")
async def cb_server_ip(callback: CallbackQuery) -> None:
    if not await can_view_server_address(callback.bot, callback.from_user.id):
        await callback.answer("Доступно только владельцу бота и администраторам групп.", show_alert=True)
        return

    await callback.answer("Проверяю адрес...")
    public_ip = await detect_public_ip()
    await safe_edit(callback, server_address_text(public_ip), reply_markup=admin_menu())


@router.callback_query(F.data.startswith("profile:chat:"))
async def cb_profile_chat(callback: CallbackQuery) -> None:
    chat_id = int(callback.data.split(":", 2)[2])
    if not await is_chat_member(callback.bot, chat_id, callback.from_user.id):
        await callback.answer("Ты больше не состоишь в этой группе.", show_alert=True)
        return
    text = telegram_user_profile_text(
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.full_name,
        chat_id=chat_id,
        short=False,
    )
    await safe_edit(callback, text, reply_markup=user_menu(chat_id))
    await callback.answer()


@router.callback_query(F.data == "soc:noop")
async def cb_social_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data.startswith("soc:fl:"))
async def cb_social_friend_list(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        await callback.answer("Кнопка устарела.", show_alert=True)
        return
    try:
        chat_id, owner_id = int(parts[2]), int(parts[3])
    except ValueError:
        await callback.answer("Кнопка устарела.", show_alert=True)
        return
    if callback.from_user.id != owner_id:
        await callback.answer("Это список другого пользователя.", show_alert=True)
        return
    if not callback.message or callback.message.chat.id != chat_id:
        await callback.answer("Открой профиль заново в нужной группе.", show_alert=True)
        return

    active_friends: list[User] = []
    for friend in db.list_chat_friends(chat_id, owner_id, limit=50):
        user = await active_social_user(callback.bot, chat_id, friend.user_id)
        if user:
            active_friends.append(user)
    if not active_friends:
        text = "В этой группе список друзей пока пуст."
    else:
        lines = ["<b>Друзья в этой группе</b>"]
        lines.extend(f"{index}. {escape(user.full_name)}" for index, user in enumerate(active_friends, start=1))
        text = "\n".join(lines)
    await temporary_reply(callback.message, text, disable_web_page_preview=True)
    await callback.answer()


@router.callback_query(F.data.startswith("sec:open:"))
async def cb_secret_message_open(callback: CallbackQuery) -> None:
    message_id = (callback.data or "").rsplit(":", 1)[-1]
    secret_message = db.get_secret_message(message_id)
    if secret_message is None:
        await callback.answer("Сообщение устарело или удалено.", show_alert=True)
        return
    if callback.from_user.id != secret_message.target_id:
        await callback.answer("Это личное сообщение адресовано не тебе.", show_alert=True)
        return

    sender = f"@{secret_message.sender_username}" if secret_message.sender_username else secret_message.sender_name
    alert_text = f"От {sender}:\n\n{secret_message.text}"
    if len(alert_text) <= SECRET_MESSAGE_ALERT_LIMIT:
        await callback.answer(alert_text, show_alert=True)
        db.mark_secret_message_delivered(message_id)
        if callback.message:
            try:
                await callback.message.edit_text(
                    "Скрытое сообщение открыто.",
                    reply_markup=None,
                )
            except (TelegramBadRequest, TelegramForbiddenError):
                pass
        return

    chat_title = callback.message.chat.title if callback.message and callback.message.chat else "чате"
    try:
        await callback.bot.send_message(
            callback.from_user.id,
            (
                f"<b>Скрытое сообщение</b>\n"
                f"От: <b>{escape(sender)}</b>\n"
                f"Чат: <b>{escape(chat_title or 'чат')}</b>\n\n"
                f"{escape(secret_message.text)}"
            ),
            disable_web_page_preview=True,
        )
    except (TelegramBadRequest, TelegramForbiddenError):
        await callback.answer("Открой личный чат с ботом и нажми /start, потом нажми кнопку снова.", show_alert=True)
        return

    db.mark_secret_message_delivered(message_id)
    if callback.message:
        try:
            await callback.message.edit_text(
                "Скрытое сообщение слишком длинное для окна и доставлено адресату в личку.",
                reply_markup=None,
            )
        except (TelegramBadRequest, TelegramForbiddenError):
            pass
    await callback.answer("Отправил в личку.")


@router.callback_query(F.data.regexp(re.compile(r"^soc:(?:fq|fr|fa|fd|pq|pa|pd|pe|px):")))
async def cb_social_action(callback: CallbackQuery) -> None:
    parsed = social_callback_ids(callback)
    if not parsed or not callback.message:
        await callback.answer("Кнопка устарела.", show_alert=True)
        return
    action, chat_id, requester_id, target_id = parsed
    if callback.message.chat.id != chat_id:
        await callback.answer("Эта кнопка относится к другой группе.", show_alert=True)
        return

    recipient_actions = {"fa", "fd", "pa", "pd"}
    expected_user_id = target_id if action in recipient_actions else requester_id
    if callback.from_user.id != expected_user_id:
        await callback.answer(
            "Подтвердить эту заявку может только её получатель."
            if action in recipient_actions
            else "Эта кнопка принадлежит другому пользователю.",
            show_alert=True,
        )
        return

    requester = await active_social_user(callback.bot, chat_id, requester_id)
    target = await active_social_user(callback.bot, chat_id, target_id)
    if requester is None or target is None:
        await callback.answer("Один из участников больше не состоит в этой группе.", show_alert=True)
        return
    requester_link = profile_link(requester.id, requester.username, requester.full_name)
    target_link = profile_link(target.id, target.username, target.full_name)

    if action == "fq":
        state = db.create_friend_request(chat_id, requester_id, target_id)
        if state != "created":
            messages = {
                "friends": "Вы уже друзья.",
                "outgoing": "Заявка уже отправлена.",
                "incoming": "У тебя уже есть входящая заявка от этого пользователя.",
                "self": "Нельзя добавить себя в друзья.",
            }
            await callback.answer(messages.get(state, "Не получилось создать заявку."), show_alert=True)
            return
        await callback.message.answer(
            f"{target_link}, {requester_link} предлагает дружить.",
            reply_markup=social_request_menu("friend", chat_id, requester_id, target_id),
            disable_web_page_preview=True,
        )
        await callback.answer("Заявка отправлена.")
        return

    if action == "fa":
        accepted = db.accept_friend_request(chat_id, requester_id, target_id)
        if not accepted:
            await callback.answer("Заявка уже обработана или устарела.", show_alert=True)
            return
        await safe_edit(
            callback,
            f"{requester_link} и {target_link} теперь друзья.",
            reply_markup=None,
            disable_web_page_preview=True,
        )
        await callback.answer("Дружба подтверждена.")
        return

    if action == "fd":
        declined = db.decline_friend_request(chat_id, requester_id, target_id)
        await safe_edit(
            callback,
            "Заявка в друзья отклонена." if declined else "Эта заявка уже не действует.",
            reply_markup=None,
        )
        await callback.answer()
        return

    if action == "fr":
        if db.couple_state(chat_id, requester_id, target_id) == "couple":
            await callback.answer("Сначала нужно расстаться, затем можно удалить дружбу.", show_alert=True)
            return
        removed = db.remove_friendship(chat_id, requester_id, target_id)
        text = telegram_user_profile_text(
            target.id,
            target.username,
            target.full_name,
            chat_id=chat_id,
            short=True,
        )
        await safe_edit(
            callback,
            text,
            reply_markup=social_profile_markup(chat_id, requester_id, target_id),
            disable_web_page_preview=True,
        )
        await callback.answer("Удалено из друзей." if removed else "Вы уже не друзья.", show_alert=not removed)
        return

    if action == "pq":
        state = db.create_couple_request(chat_id, requester_id, target_id)
        if state != "created":
            messages = {
                "couple": "Вы уже пара.",
                "user_busy": "У тебя уже есть пара в этой группе.",
                "target_busy": "У этого пользователя уже есть пара в этой группе.",
                "outgoing": "Предложение уже отправлено.",
                "incoming": "У тебя уже есть входящее предложение от этого пользователя.",
                "self": "Нельзя предложить отношения самому себе.",
            }
            await callback.answer(messages.get(state, "Не получилось отправить предложение."), show_alert=True)
            return
        await callback.message.answer(
            f"{target_link}, {requester_link} предлагает стать парой.",
            reply_markup=social_request_menu("couple", chat_id, requester_id, target_id),
            disable_web_page_preview=True,
        )
        await callback.answer("Предложение отправлено.")
        return

    if action == "pa":
        result = db.accept_couple_request(chat_id, requester_id, target_id)
        if result != "accepted":
            await callback.answer(
                "Предложение устарело." if result == "missing" else "У одного из участников уже есть пара.",
                show_alert=True,
            )
            return
        await safe_edit(
            callback,
            f"{requester_link} и {target_link} теперь пара.",
            reply_markup=None,
            disable_web_page_preview=True,
        )
        await callback.answer("Предложение принято.")
        return

    if action == "pd":
        declined = db.decline_couple_request(chat_id, requester_id, target_id)
        await safe_edit(
            callback,
            "Предложение отклонено." if declined else "Это предложение уже не действует.",
            reply_markup=None,
        )
        await callback.answer()
        return

    if action == "pe":
        if db.couple_state(chat_id, requester_id, target_id) != "couple":
            await callback.answer("Вы уже не пара.", show_alert=True)
            return
        await callback.message.answer(
            f"{requester_link}, подтвердить расставание с {target_link}?",
            reply_markup=social_couple_end_menu(chat_id, requester_id, target_id),
            disable_web_page_preview=True,
        )
        await callback.answer()
        return

    if action == "px":
        ended = db.end_chat_couple(chat_id, requester_id, target_id)
        await safe_edit(
            callback,
            f"{requester_link} и {target_link} больше не пара."
            if ended
            else "Эта связь уже завершена.",
            reply_markup=None,
            disable_web_page_preview=True,
        )
        await callback.answer()


@router.callback_query(F.data.startswith("user:bag:"))
async def cb_user_bag(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    chat_id = int(parts[2])
    owner_id = await resolve_dig_button_owner(callback, parts[3] if len(parts) > 3 else None)
    if owner_id is None:
        return
    if not await is_chat_member(callback.bot, chat_id, callback.from_user.id):
        await callback.answer("Ты больше не состоишь в этой группе.", show_alert=True)
        return

    text = dig_bag_text(chat_id, callback.from_user.id)
    if text is None:
        await callback.answer("Сначала зарегистрируйся в шахте командой копай внутри группы.", show_alert=True)
        return

    await safe_edit(callback, text, reply_markup=user_bag_menu(chat_id, callback.from_user.id))
    await callback.answer()


@router.callback_query(F.data.startswith("user:mine:"))
async def cb_user_mine(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    chat_id = int(parts[2])
    owner_id = await resolve_dig_button_owner(callback, parts[3] if len(parts) > 3 else None)
    if owner_id is None:
        return
    chat = db.get_chat(chat_id)
    if chat is None:
        await callback.answer("Группа не найдена.", show_alert=True)
        return
    if not await is_chat_member(callback.bot, chat_id, callback.from_user.id):
        await callback.answer("Ты больше не состоишь в этой группе.", show_alert=True)
        return

    await safe_edit(
        callback,
        f"<b>Шахта</b>\nГруппа: <b>{mention_chat(chat)}</b>",
        reply_markup=user_mine_menu(
            chat_id,
            owner_id,
            show_back=bool(callback.message and callback.message.chat.type == "private"),
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("user:donate:"))
async def cb_user_donate(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    chat_id = int(parts[2])
    owner_id = await resolve_dig_button_owner(callback, parts[3] if len(parts) > 3 else None)
    if owner_id is None:
        return
    if not await is_chat_member(callback.bot, chat_id, callback.from_user.id):
        await callback.answer("Ты больше не состоишь в этой группе.", show_alert=True)
        return
    if db.get_dig_player(chat_id, callback.from_user.id) is None:
        await callback.answer("Сначала зарегистрируйся в шахте командой копай внутри группы.", show_alert=True)
        return

    await safe_edit(
        callback,
        "<b>Покупки шахты за Stars переехали в Mini App</b>\n\n"
        "Открой магазин шахты и выбери вкладку <b>Покупки за Stars</b>.",
        reply_markup=miniapp_private_menu("Открыть магазин", view="shop"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("user:shop:"))
async def cb_user_shop(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    if len(parts) < 3 or not parts[2].lstrip("-").isdigit():
        await callback.answer("Кнопка магазина устарела.", show_alert=True)
        return
    chat_id = int(parts[2])
    has_owner = len(parts) > 3 and parts[3].isdigit()
    owner_id = await resolve_dig_button_owner(callback, parts[3] if has_owner else None)
    if owner_id is None:
        return
    category_index = 4 if has_owner else 3
    category = parts[category_index] if len(parts) > category_index else None
    if category not in DIG_SHOP_CATEGORIES:
        category = None
    try:
        page = int(parts[category_index + 1]) if len(parts) > category_index + 1 else 0
    except ValueError:
        page = 0
    if not await is_chat_member(callback.bot, chat_id, callback.from_user.id):
        await callback.answer("Ты больше не состоишь в этой группе.", show_alert=True)
        return

    player = db.get_dig_player(chat_id, callback.from_user.id)
    if player is None:
        await callback.answer("Сначала зарегистрируйся в шахте командой копай внутри группы.", show_alert=True)
        return

    items = dig_items_map(chat_id, callback.from_user.id)
    if category:
        page_items, page, total_pages = dig_shop_page_items(category, items, page)
        await safe_edit(
            callback,
            dig_shop_category_text(player.coins, category, page, total_pages),
            reply_markup=user_shop_items_menu(chat_id, callback.from_user.id, category, page, total_pages, page_items),
        )
        await callback.answer()
        return

    await safe_edit(
        callback,
        dig_shop_overview_text(player.coins, items),
        reply_markup=user_shop_categories_menu(chat_id, owner_id, dig_shop_categories_for_keyboard()),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("user:buy:"))
async def cb_user_buy(callback: CallbackQuery) -> None:
    parts = callback.data.split(":", 4)
    if len(parts) != 5:
        await callback.answer("Не получилось открыть предмет.", show_alert=True)
        return

    chat_id = int(parts[2])
    owner_id = int(parts[3])
    item_key = parts[4]
    if not await require_dig_button_owner(callback, owner_id):
        return
    if not await is_chat_member(callback.bot, chat_id, callback.from_user.id):
        await callback.answer("Ты больше не состоишь в этой группе.", show_alert=True)
        return

    item = DIG_SHOP_ITEMS.get(item_key)
    if item is None:
        await callback.answer("Предмет не найден.", show_alert=True)
        return

    player = db.get_dig_player(chat_id, callback.from_user.id)
    if player is None:
        await callback.answer("Сначала зарегистрируйся в шахте.", show_alert=True)
        return

    name, _, description = item
    items = dig_items_map(chat_id, callback.from_user.id)
    price = dig_shop_price(item_key, items)
    discount = dig_rank_discount(items) if item_key in dig_discountable_item_keys() else 0
    discount_text = f"\nСкидка ранга: <b>{discount}%</b>" if discount else ""
    await safe_edit(
        callback,
        f"<b>{escape(name)}</b>\n"
        f"Цена: <b>{price}</b> котоинов{discount_text}\n"
        f"У тебя: <b>{player.coins}</b> котоинов\n\n"
        f"{escape(description)}",
        reply_markup=user_buy_confirm_menu(chat_id, callback.from_user.id, item_key),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("user:confirm:"))
async def cb_user_confirm(callback: CallbackQuery) -> None:
    parts = callback.data.split(":", 4)
    if len(parts) != 5:
        await callback.answer("Не получилось обработать покупку.", show_alert=True)
        return

    chat_id = int(parts[2])
    owner_id = int(parts[3])
    item_key = parts[4]
    if not await require_dig_button_owner(callback, owner_id):
        return
    if not await is_chat_member(callback.bot, chat_id, callback.from_user.id):
        await callback.answer("Ты больше не состоишь в этой группе.", show_alert=True)
        return

    item = DIG_SHOP_ITEMS.get(item_key)
    if item is None:
        await callback.answer("Предмет не найден.", show_alert=True)
        return

    player = db.get_dig_player(chat_id, callback.from_user.id)
    if player is None:
        await callback.answer("Сначала зарегистрируйся в шахте.", show_alert=True)
        return
    if not callback.message:
        await callback.answer("Не вижу сообщение магазина.", show_alert=True)
        return
    if dig_purchase_is_duplicate(chat_id, callback.from_user.id, item_key, callback.message.message_id):
        await callback.answer("Покупка уже обрабатывается.", show_alert=True)
        return

    items = dig_items_map(chat_id, callback.from_user.id)
    purchase_error = dig_purchase_error(items, item_key)
    if purchase_error:
        await callback.answer(purchase_error, show_alert=True)
        return

    name, _, _ = item
    price = dig_shop_price(item_key, items)
    result = f"Куплено: <b>{escape(name)}</b>."
    if item_key == "prank":
        if not db.spend_dig_coins(chat_id, callback.from_user.id, price):
            await callback.answer("Не хватает котоинов.", show_alert=True)
            return
        prank_text = f"{escape(dig_player_name(callback.from_user.username, callback.from_user.full_name))} оформил шахтерскую проверку. Кто-то явно копает не туда."
        try:
            await callback.bot.send_message(chat_id, prank_text)
        except (TelegramBadRequest, TelegramForbiddenError, TelegramNotFound) as exc:
            db.add_dig_coins(chat_id, callback.from_user.id, price)
            await callback.answer("Не получилось отправить подставу, котоины возвращены.", show_alert=True)
            await safe_edit(
                callback,
                "Не получилось отправить подставу, котоины возвращены.\n"
                f"<code>{escape(str(exc))}</code>",
                reply_markup=user_shop_categories_menu(chat_id, callback.from_user.id, dig_shop_categories_for_keyboard()),
            )
            return
        result = "Подстава куплена и отправлена в чат."
    else:
        purchase_status = db.purchase_dig_item(
            chat_id,
            callback.from_user.id,
            item_key,
            price,
            quantity=1,
            unique=item_key in DIG_PERMANENT_ITEMS,
        )
        if purchase_status == "owned":
            await callback.answer("Это улучшение уже куплено.", show_alert=True)
            return
        if purchase_status == "no_coins":
            await callback.answer("Не хватает котоинов.", show_alert=True)
            return

    updated = db.get_dig_player(chat_id, callback.from_user.id)
    achievement_text = award_dig_achievement(chat_id, callback.from_user.id, "first_purchase")
    items = dig_items_map(chat_id, callback.from_user.id)
    category = dig_shop_category_for_item(item_key)
    page_items, page, total_pages = dig_shop_page_items(category, items, 0)
    achievement_block = f"\n\n<b>Достижение:</b>\n{escape(achievement_text)}" if achievement_text else ""
    await safe_edit(
        callback,
        f"{result}\n\n"
        f"Котоины: <b>{updated.coins if updated else 0}</b>\n\n"
        f"<b>Активные эффекты:</b>\n{escape(dig_effects_text(items))}"
        f"{achievement_block}",
        reply_markup=user_shop_items_menu(chat_id, callback.from_user.id, category, page, total_pages, page_items),
    )
    await callback.answer("Куплено")


@router.callback_query(F.data.startswith("user:dig:"))
async def cb_user_dig(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    owner_raw: str | None = None
    if len(parts) >= 4:
        action = parts[2]
        chat_id = int(parts[3])
        owner_raw = parts[4] if len(parts) > 4 else None
        owner_id = await resolve_dig_button_owner(callback, owner_raw)
        if owner_id is None:
            return
        if action == "mode":
            if chat_id != 0 and not await is_chat_member(callback.bot, chat_id, callback.from_user.id):
                await callback.answer("Ты больше не состоишь в этой группе.", show_alert=True)
                return
            await safe_edit(
                callback,
                "Выбери способ раскопки:\n\n"
                "• <b>Автоматически</b> — быстрый результат, добыча ниже, без ручных событий и ресурсов.\n"
                "• <b>Вручную</b> — Mini App: клетки, события, ресурсы и выборы по ходу вылазки. Торговец ждёт снаружи в сумке.",
                reply_markup=user_dig_mode_menu(chat_id, owner_id),
            )
            await callback.answer()
            return
        if action == "manual":
            if chat_id != 0 and not await is_chat_member(callback.bot, chat_id, callback.from_user.id):
                await callback.answer("Ты больше не состоишь в этой группе.", show_alert=True)
                return
            try:
                await callback.bot.send_message(
                    callback.from_user.id,
                    "Ручная шахта открывается в Mini App.\n\n"
                    "Там есть клетки, события и ресурсы. Автоматический режим быстрее, но добыча ниже и без этих ручных находок.",
                    reply_markup=miniapp_private_menu(),
                )
            except (TelegramBadRequest, TelegramForbiddenError):
                await callback.answer(
                    "Сначала открой личный чат с ботом, нажми /start и повтори попытку.",
                    show_alert=True,
                )
                return
            await callback.answer("Кнопка шахты отправлена в личный чат.", show_alert=True)
            return
        if action != "auto":
            await callback.answer("Режим раскопки устарел.", show_alert=True)
            return
    else:
        # Старые сообщения с кнопкой «Копать» продолжают работать как автоматическая раскопка.
        chat_id = int(parts[2])
        owner_id = await resolve_dig_button_owner(callback, None)
        if owner_id is None:
            return
    if chat_id != 0 and not await is_chat_member(callback.bot, chat_id, callback.from_user.id):
        await callback.answer("Ты больше не состоишь в этой группе.", show_alert=True)
        return

    result = run_private_dig(chat_id, callback.from_user)
    reply_markup = user_mine_menu(chat_id, owner_id, show_back=False)
    if result.rich_message and callback.message:
        try:
            sent_result = await callback.bot.send_rich_message(
                chat_id=callback.message.chat.id,
                rich_message=result.rich_message,
                message_thread_id=getattr(callback.message, "message_thread_id", None),
                reply_markup=reply_markup,
            )
            schedule_message_delete(sent_result, 30)
            deleted = False
            try:
                await callback.message.delete()
                deleted = True
            except (TelegramBadRequest, TelegramForbiddenError, TelegramNotFound):
                deleted = False
            if not deleted:
                await safe_edit(callback, "Результат раскопки ниже.", reply_markup=None)
        except (TelegramBadRequest, TelegramForbiddenError):
            await safe_edit(callback, result.text, reply_markup=reply_markup)
            schedule_message_delete(callback.message, 30)
    else:
        await safe_edit(callback, result.text, reply_markup=reply_markup)
        schedule_message_delete(callback.message, 30)
    await callback.answer()


@router.callback_query(F.data.startswith("digcell:"))
async def cb_interactive_dig_cell(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        await callback.answer("Клетка устарела.", show_alert=True)
        return
    session_id = parts[1]
    try:
        expected_depth = int(parts[2])
        cell_index = int(parts[3])
    except ValueError:
        await callback.answer("Клетка устарела.", show_alert=True)
        return

    session = db.lock_interactive_dig_cell(session_id, callback.from_user.id, expected_depth, cell_index)
    if session is None:
        await callback.answer("Этот слой уже обработан или вылазка устарела.", show_alert=True)
        return
    await callback.answer()

    try:
        cells, used_cells, snapshot = interactive_dig_cells(session)
        if isinstance(cells, dict):
            if cells.get("type") in {"event", "final"}:
                db.update_interactive_dig_session(session_id, processing=0)
                await callback.answer("Сейчас в шахте событие, выбери действие ниже.", show_alert=True)
                return
            cells = cells.get("cells", [])
        if cell_index < 0 or cell_index >= len(cells):
            db.update_interactive_dig_session(session_id, processing=0)
            await callback.answer("Клетка не найдена.", show_alert=True)
            return

        current_depth = int(session["depth"])
        next_depth = current_depth + 1
        await safe_edit(callback, "⛏ Кот бьёт киркой по выбранному слою…", retry_on_flood=False)
        await asyncio.sleep(0.6)

        resolved = resolve_cell(cells[cell_index])
        if int(cells[cell_index].get("bonus", 0)):
            resolved["chance_modifier"] = float(resolved.get("chance_modifier", 0.0)) + int(cells[cell_index].get("bonus", 0))
        chance = final_cell_chance(
            DIG_SUCCESS_CHANCES[next_depth - 1],
            float(snapshot.get("chance_bonus", 0.0)),
            resolved,
        )
        success = secrets.randbelow(10000) < int(chance * 100)
        cell_title = {
            "normal": "обычный грунт",
            "ore": "рудная жила",
            "hard": "твёрдая порода",
            "roots": "странные корни",
        }.get(str(resolved.get("resolved_kind")), "неизвестный слой")

        if success:
            gained = cell_reward(
                dig_coin_reward(next_depth),
                float(snapshot.get("route_coins", 1.0)),
                resolved,
                int(snapshot.get("coin_bonus_percent", 0)),
            )
            if int(cells[cell_index].get("reward_bonus", 0)):
                gained = (gained * (100 + int(cells[cell_index].get("reward_bonus", 0))) + 99) // 100
            gained = scale_interactive_reward(gained)
            resource_drops = mined_resource_drops(resolved, str(snapshot.get("mine_key") or "old_mine"), next_depth)
            if resource_drops:
                add_snapshot_resources(snapshot, resource_drops)
            new_depth = next_depth
            new_temp = int(session["temporary_coins"]) + gained
            if new_depth >= INTERACTIVE_DIG_MAX_DEPTH:
                updated = dict(session)
                updated.update({
                    "depth": new_depth,
                    "temporary_coins": new_temp,
                    "equipment_snapshot": json.dumps(snapshot, ensure_ascii=False),
                    "processing": 0,
                })
                db.update_interactive_dig_session(
                    session_id,
                    depth=new_depth,
                    temporary_coins=new_temp,
                    equipment_snapshot=json.dumps(snapshot, ensure_ascii=False),
                    processing=0,
                )
                result = settle_interactive_dig(updated, callback.from_user, collapsed=False)
                await safe_edit(
                    callback,
                    f"✨ Слой пройден: <b>{escape(cell_title)}</b>.\n"
                    f"+<b>{gained}</b> котоинов во временную добычу."
                    f"{f' Добыча: {escape(resource_stack_text(resource_drops))}.' if resource_drops else ''}\n\n"
                    f"{result.text}",
                    reply_markup=user_mine_menu(int(session["chat_id"]), callback.from_user.id, show_back=False),
                )
                return

            next_cells = generate_dig_stage(new_depth + 1, str(snapshot.get("mine_key") or "old_mine"))
            db.update_interactive_dig_session(
                session_id,
                depth=new_depth,
                temporary_coins=new_temp,
                cells_json=json.dumps(next_cells, ensure_ascii=False),
                used_cells_json="[]",
                equipment_snapshot=json.dumps(snapshot, ensure_ascii=False),
                processing=0,
            )
            updated = db.get_interactive_dig_session(session_id)
            view = interactive_dig_view(
                updated,
                f"✨ Слой пройден: <b>{escape(cell_title)}</b>. +<b>{gained}</b> котоинов."
                f"{f' Добыча: {escape(resource_stack_text(resource_drops))}.' if resource_drops else ''}",
            )
            await safe_edit(
                callback,
                view.text,
                reply_markup=interactive_dig_menu(session_id, int(updated["depth"]), next_cells, [], interactive_dig_tools(snapshot, next_cells)),
            )
            return

        used_cells = sorted(set(used_cells) | {cell_index})
        durability = int(session["durability"])
        saved_by_gear = False
        if int(snapshot.get("insurance_count", 0)) > 0 and not snapshot.get("insurance_used"):
            if db.consume_dig_item(int(session["chat_id"]), callback.from_user.id, "insurance"):
                snapshot["insurance_used"] = True
                snapshot["insurance_count"] = max(0, int(snapshot.get("insurance_count", 0)) - 1)
                remember_repair_candidate(snapshot, "insurance")
                saved_by_gear = True
        protection = min(45, int(snapshot.get("loss_protection", 0)))
        if not saved_by_gear and protection and secrets.randbelow(100) < protection:
            saved_by_gear = True
        if not saved_by_gear:
            used_effects = list(snapshot.get("used_effects") or [])
            if use_interactive_medkit(
                int(session["chat_id"]),
                callback.from_user.id,
                snapshot,
                used_effects,
                "Аптечка: потеря прочности отменена",
            ):
                snapshot["used_effects"] = used_effects
                saved_by_gear = True
            else:
                durability -= 1

        if durability <= 0:
            updated = dict(session)
            updated.update(
                {
                    "durability": 0,
                    "used_cells_json": json.dumps(used_cells),
                    "processing": 0,
                }
            )
            db.update_interactive_dig_session(
                session_id,
                durability=0,
                used_cells_json=json.dumps(used_cells),
                equipment_snapshot=json.dumps(snapshot, ensure_ascii=False),
                processing=0,
            )
            result = settle_interactive_dig(updated, callback.from_user, collapsed=True)
            await safe_edit(
                callback,
                f"🪨 Слой не поддался: <b>{escape(cell_title)}</b>.\n\n{result.text}",
                reply_markup=user_mine_menu(int(session["chat_id"]), callback.from_user.id, show_back=False),
            )
            return

        replacement_stage = None
        if cell_row_is_exhausted(cells, used_cells):
            replacement_stage = replacement_cell_stage(next_depth, str(snapshot.get("mine_key") or "old_mine"))

        db.update_interactive_dig_session(
            session_id,
            durability=durability,
            cells_json=json.dumps(replacement_stage, ensure_ascii=False) if replacement_stage else None,
            used_cells_json="[]" if replacement_stage else json.dumps(used_cells),
            equipment_snapshot=json.dumps(snapshot, ensure_ascii=False),
            processing=0,
        )
        updated = db.get_interactive_dig_session(session_id)
        cells, used_cells, _snapshot = interactive_dig_cells(updated)
        prefix = f"🪨 Слой не поддался: <b>{escape(cell_title)}</b>."
        if saved_by_gear:
            prefix += " Снаряжение спасло прочность."
        else:
            prefix += f" Прочность: <b>{durability}</b>/{INTERACTIVE_DIG_DURABILITY}."
        if replacement_stage:
            prefix += " Этот ряд исчерпан, кот нашёл соседний ход."
        view = interactive_dig_view(updated, prefix)
        await safe_edit(
            callback,
            view.text,
            reply_markup=interactive_dig_menu(session_id, int(updated["depth"]), cells, used_cells, interactive_dig_tools(_snapshot, cells)),
        )
    except Exception:
        db.update_interactive_dig_session(session_id, processing=0)
        raise


@router.callback_query(F.data.startswith("digtool:"))
async def cb_interactive_dig_tool(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":", 3)
    if len(parts) != 4:
        await callback.answer("Предмет устарел.", show_alert=True)
        return
    session_id = parts[1]
    try:
        expected_depth = int(parts[2])
    except ValueError:
        await callback.answer("Предмет устарел.", show_alert=True)
        return
    tool_key = parts[3]
    if tool_key not in {"flashlight", "map", "dynamite", "miner_hearing", "magnet", "cat_companion"}:
        await callback.answer("Такого предмета нет.", show_alert=True)
        return

    session = db.lock_interactive_dig_cell(session_id, callback.from_user.id, expected_depth, -2)
    if session is None:
        await callback.answer("Сейчас предмет использовать нельзя.", show_alert=True)
        return
    await callback.answer()

    try:
        stage, used_cells, snapshot = interactive_dig_cells(session)
        if isinstance(stage, dict) and stage.get("type") == "cells":
            cells = stage.get("cells", [])
        elif isinstance(stage, list):
            cells = stage
            stage = {"type": "cells", "cells": cells}
        else:
            db.update_interactive_dig_session(session_id, processing=0)
            await callback.answer("В этой комнате предмет не нужен.", show_alert=True)
            return

        used_tools = set(snapshot.get("used_tools") or [])
        if tool_key in used_tools or int(snapshot.get(f"{tool_key}_count", 0)) <= 0:
            db.update_interactive_dig_session(session_id, processing=0)
            await callback.answer("Этот предмет уже использован.", show_alert=True)
            return
        if not db.consume_dig_item(int(session["chat_id"]), callback.from_user.id, tool_key):
            db.update_interactive_dig_session(session_id, processing=0)
            await callback.answer("Предмета уже нет в сумке.", show_alert=True)
            return

        available = [index for index, cell in enumerate(cells) if index not in set(used_cells)]
        message = ""
        if tool_key == "flashlight":
            if available:
                index = available[secrets.randbelow(len(available))]
                cells[index]["revealed"] = cells[index].get("kind", "unknown")
                message = f"🔦 Фонарь подсветил клетку <b>{index + 1}</b>."
        elif tool_key == "map":
            mine_key = str(snapshot.get("mine_key") or "old_mine")
            preview_cells = generate_dig_cells(int(session["depth"]) + 2, mine_key=mine_key)
            emoji_map = {"normal": "🟫", "ore": "✨", "hard": "🪨", "roots": "🌿", "unknown": "❓"}
            stage["preview"] = " ".join(emoji_map.get(str(cell.get("kind")), "❓") for cell in preview_cells)
            message = "🗺 Карта показала признаки следующего ряда."
        elif tool_key == "dynamite":
            if secrets.randbelow(100) < DYNAMITE_MISHAP_CHANCE:
                durability = max(0, int(session["durability"]) - 1)
                snapshot[f"{tool_key}_count"] = max(0, int(snapshot.get(f"{tool_key}_count", 0)) - 1)
                used_tools.add(tool_key)
                snapshot["used_tools"] = sorted(used_tools)
                remember_repair_candidate(snapshot, tool_key)
                db.update_interactive_dig_session(
                    session_id,
                    durability=durability,
                    equipment_snapshot=json.dumps(snapshot, ensure_ascii=False),
                    processing=0,
                )
                updated = db.get_interactive_dig_session(session_id)
                if durability <= 0:
                    finished = dict(updated)
                    finished.update({"durability": 0, "processing": 0})
                    result = settle_interactive_dig(finished, callback.from_user, collapsed=True)
                    await safe_edit(
                        callback,
                        f"🧨 {escape(DYNAMITE_MISHAP_MESSAGE)}\n\n{result.text}",
                        reply_markup=user_mine_menu(int(session["chat_id"]), callback.from_user.id, show_back=False),
                    )
                    return
                view = interactive_dig_view(
                    updated,
                    f"🧨 {escape(DYNAMITE_MISHAP_MESSAGE)} Прочность: <b>{durability}</b>/{INTERACTIVE_DIG_DURABILITY}.",
                )
                await safe_edit(
                    callback,
                    view.text,
                    reply_markup=interactive_dig_menu(session_id, int(updated["depth"]), stage, used_cells, interactive_dig_tools(snapshot, stage)),
                )
                return
            targets = [index for index in available if cells[index].get("kind") in {"hard", "unknown", "roots"}] or available
            blasted = targets[:]
            random.SystemRandom().shuffle(blasted)
            blasted = blasted[: min(3, len(blasted))]
            for index in blasted:
                cells[index]["revealed"] = cells[index].get("kind", "unknown")
                cells[index]["bonus"] = int(cells[index].get("bonus", 0)) + 8
            message = f"🧨 Динамит ослабил клеток: <b>{len(blasted)}</b>."
        elif tool_key == "miner_hearing":
            normals = [index for index in available if cells[index].get("kind") == "normal"]
            if normals:
                index = normals[secrets.randbelow(len(normals))]
                cells[index]["revealed"] = "normal"
                message = f"👂 Слух шахтёра нашёл спокойную клетку <b>{index + 1}</b>."
        elif tool_key == "magnet":
            ores = [index for index in available if cells[index].get("kind") == "ore"]
            if ores:
                index = ores[secrets.randbelow(len(ores))]
                cells[index]["revealed"] = "ore"
                cells[index]["reward_bonus"] = int(cells[index].get("reward_bonus", 0)) + 20
                message = f"🧲 Магнит потянул руду к клетке <b>{index + 1}</b>."
        elif tool_key == "cat_companion":
            suspicious = [index for index in available if cells[index].get("kind") != "normal"] or available
            if suspicious:
                index = suspicious[secrets.randbelow(len(suspicious))]
                cells[index]["revealed"] = cells[index].get("kind", "unknown")
                message = f"🐈 Компаньон насторожился у клетки <b>{index + 1}</b>."

        snapshot[f"{tool_key}_count"] = max(0, int(snapshot.get(f"{tool_key}_count", 0)) - 1)
        used_tools.add(tool_key)
        snapshot["used_tools"] = sorted(used_tools)
        remember_repair_candidate(snapshot, tool_key)
        db.update_interactive_dig_session(
            session_id,
            cells_json=json.dumps(stage, ensure_ascii=False),
            equipment_snapshot=json.dumps(snapshot, ensure_ascii=False),
            processing=0,
        )
        updated = db.get_interactive_dig_session(session_id)
        view = interactive_dig_view(updated, message or "Предмет использован.")
        await safe_edit(
            callback,
            view.text,
            reply_markup=interactive_dig_menu(session_id, int(updated["depth"]), stage, used_cells, interactive_dig_tools(snapshot, stage)),
        )
    except Exception:
        db.update_interactive_dig_session(session_id, processing=0)
        raise


@router.callback_query(F.data.startswith("digevent:"))
async def cb_interactive_dig_event(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":", 3)
    if len(parts) != 4:
        await callback.answer("Событие устарело.", show_alert=True)
        return
    session_id = parts[1]
    try:
        expected_depth = int(parts[2])
    except ValueError:
        await callback.answer("Событие устарело.", show_alert=True)
        return
    choice_key = parts[3]

    session = db.lock_interactive_dig_cell(session_id, callback.from_user.id, expected_depth, -1)
    if session is None:
        await callback.answer("Событие уже обработано или вылазка устарела.", show_alert=True)
        return
    await callback.answer()

    try:
        stage, _used_cells, snapshot = interactive_dig_cells(session)
        if not isinstance(stage, dict) or stage.get("type") not in {"event", "final"}:
            db.update_interactive_dig_session(session_id, processing=0)
            await callback.answer("Событие уже закончилось.", show_alert=True)
            return
        choice = event_choice(stage, choice_key)
        if choice is None:
            db.update_interactive_dig_session(session_id, processing=0)
            await callback.answer("Такого выбора уже нет.", show_alert=True)
            return

        if choice.get("settle"):
            final_depth = INTERACTIVE_DIG_MAX_DEPTH if stage.get("type") == "final" else int(session["depth"])
            choice_coins = int(choice.get("coins", 0))
            if choice_coins > 0:
                choice_coins = scale_interactive_reward(choice_coins)
            used_effects = list(snapshot.get("used_effects") or [])
            if choice_coins < 0 and use_interactive_medkit(
                int(session["chat_id"]),
                callback.from_user.id,
                snapshot,
                used_effects,
                "Аптечка: потеря котоинов в событии отменена",
            ):
                choice_coins = 0
                snapshot["used_effects"] = used_effects
            final_coins = max(0, int(session["temporary_coins"]) + choice_coins)
            final_durability = min(
                INTERACTIVE_DIG_DURABILITY,
                int(session["durability"]) + int(choice.get("durability", 0)),
            )
            risk = int(choice.get("risk", 0))
            collapsed = False
            if risk and secrets.randbelow(100) < risk:
                used_effects = list(snapshot.get("used_effects") or [])
                if use_interactive_medkit(
                    int(session["chat_id"]),
                    callback.from_user.id,
                    snapshot,
                    used_effects,
                    "Аптечка: повреждение от риска отменено",
                ):
                    snapshot["used_effects"] = used_effects
                else:
                    final_durability -= 1
                collapsed = final_durability <= 0
            db.update_interactive_dig_session(
                session_id,
                depth=final_depth,
                durability=max(0, final_durability),
                temporary_coins=final_coins,
                equipment_snapshot=json.dumps(snapshot, ensure_ascii=False),
                processing=0,
            )
            session.update(
                {
                    "depth": final_depth,
                    "durability": max(0, final_durability),
                    "temporary_coins": final_coins,
                    "equipment_snapshot": json.dumps(snapshot, ensure_ascii=False),
                    "processing": 0,
                }
            )
            db.update_interactive_dig_session(session_id, processing=0)
            result = settle_interactive_dig(session, callback.from_user, collapsed=collapsed)
            prefix = ""
            if stage.get("type") == "final":
                prefix = (
                    f"{escape(str(stage.get('emoji') or '🏁'))} <b>{escape(str(stage.get('title') or 'Финальная комната'))}</b>\n"
                    f"Выбор: <b>{escape(str(choice.get('label') or 'награда'))}</b>.\n\n"
                )
            await safe_edit(
                callback,
                prefix + result.text,
                reply_markup=user_mine_menu(int(session["chat_id"]), callback.from_user.id, show_back=False),
            )
            return

        current_depth = int(session["depth"])
        choice_coins = int(choice.get("coins", 0))
        if choice_coins > 0:
            choice_coins = scale_interactive_reward(choice_coins)
        used_effects = list(snapshot.get("used_effects") or [])
        if choice_coins < 0 and use_interactive_medkit(
            int(session["chat_id"]),
            callback.from_user.id,
            snapshot,
            used_effects,
            "Аптечка: потеря котоинов в событии отменена",
        ):
            choice_coins = 0
            snapshot["used_effects"] = used_effects
        temporary_coins = max(0, int(session["temporary_coins"]) + choice_coins)
        durability = min(
            INTERACTIVE_DIG_DURABILITY,
            int(session["durability"]) + int(choice.get("durability", 0)),
        )
        messages = [
            f"{escape(str(stage.get('emoji') or '❔'))} <b>{escape(str(stage.get('title') or 'Событие'))}</b>",
            f"Выбор: <b>{escape(str(choice.get('label') or 'действие'))}</b>.",
        ]
        if choice.get("merchant"):
            messages.append("Купец теперь ждёт снаружи, в сумке.")
        if choice_coins:
            sign = "+" if choice_coins > 0 else ""
            messages.append(f"Добыча: <b>{sign}{choice_coins}</b> котоинов.")
        if int(choice.get("durability", 0)):
            messages.append(f"Прочность: <b>{durability}</b>/{INTERACTIVE_DIG_DURABILITY}.")
        if int(choice.get("chance", 0)):
            snapshot["chance_bonus"] = float(snapshot.get("chance_bonus", 0.0)) + int(choice.get("chance", 0))
            messages.append(f"Следующие слои: <b>+{int(choice.get('chance', 0))}%</b> к шансу.")

        failed = False
        risk = int(choice.get("risk", 0))
        if risk and secrets.randbelow(100) < risk:
            failed = True
            used_effects = list(snapshot.get("used_effects") or [])
            if use_interactive_medkit(
                int(session["chat_id"]),
                callback.from_user.id,
                snapshot,
                used_effects,
                "Аптечка: повреждение от риска отменено",
            ):
                snapshot["used_effects"] = used_effects
                messages.append("Риск сыграл против кота, но аптечка спасла прочность.")
            else:
                durability -= 1
                messages.append(f"Риск сыграл против кота. Прочность: <b>{durability}</b>/{INTERACTIVE_DIG_DURABILITY}.")

        if durability <= 0:
            updated = dict(session)
            updated.update({"durability": 0, "temporary_coins": temporary_coins, "processing": 0})
            db.update_interactive_dig_session(
                session_id,
                durability=0,
                temporary_coins=temporary_coins,
                equipment_snapshot=json.dumps(snapshot, ensure_ascii=False),
                processing=0,
            )
            result = settle_interactive_dig(updated, callback.from_user, collapsed=True)
            await safe_edit(
                callback,
                "\n".join(messages) + "\n\n" + result.text,
                reply_markup=user_mine_menu(int(session["chat_id"]), callback.from_user.id, show_back=False),
            )
            return

        gained_depth = 0 if failed else int(choice.get("depth", 0))
        new_depth = min(INTERACTIVE_DIG_MAX_DEPTH, current_depth + gained_depth)
        if gained_depth:
            messages.append(f"Удалось пройти ещё <b>{gained_depth}</b> м.")
        if new_depth >= INTERACTIVE_DIG_MAX_DEPTH:
            updated = dict(session)
            updated.update(
                {
                    "depth": new_depth,
                    "durability": durability,
                    "temporary_coins": temporary_coins,
                    "equipment_snapshot": json.dumps(snapshot, ensure_ascii=False),
                    "processing": 0,
                }
            )
            db.update_interactive_dig_session(
                session_id,
                depth=new_depth,
                durability=durability,
                temporary_coins=temporary_coins,
                equipment_snapshot=json.dumps(snapshot, ensure_ascii=False),
                processing=0,
            )
            result = settle_interactive_dig(updated, callback.from_user, collapsed=False)
            await safe_edit(
                callback,
                "\n".join(messages) + "\n\n" + result.text,
                reply_markup=user_mine_menu(int(session["chat_id"]), callback.from_user.id, show_back=False),
            )
            return

        mine_key = str(snapshot.get("mine_key") or "old_mine")
        if choice.get("repeat") and secrets.randbelow(100) < int(choice.get("repeat", 0)):
            next_stage = generate_event_stage(new_depth + 1, mine_key, preferred=str(stage.get("event") or "ore_vein"))
            messages.append("Жила продолжается дальше.")
        else:
            next_stage = {"type": "cells", "cells": generate_dig_cells(new_depth + 1, mine_key=mine_key)}

        db.update_interactive_dig_session(
            session_id,
            depth=new_depth,
            durability=durability,
            temporary_coins=temporary_coins,
            cells_json=json.dumps(next_stage, ensure_ascii=False),
            used_cells_json="[]",
            equipment_snapshot=json.dumps(snapshot, ensure_ascii=False),
            processing=0,
        )
        updated = db.get_interactive_dig_session(session_id)
        view = interactive_dig_view(updated, "\n".join(messages))
        await safe_edit(
            callback,
            view.text,
            reply_markup=interactive_dig_menu(session_id, int(updated["depth"]), next_stage, [], interactive_dig_tools(snapshot, next_stage)),
        )
    except Exception:
        db.update_interactive_dig_session(session_id, processing=0)
        raise


@router.callback_query(F.data.startswith("digexit:"))
async def cb_interactive_dig_exit(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 2:
        await callback.answer("Вылазка устарела.", show_alert=True)
        return
    session = db.get_interactive_dig_session(parts[1])
    if session is None or session.get("status") != "active":
        await callback.answer("Эта вылазка уже завершена.", show_alert=True)
        return
    if int(session["user_id"]) != callback.from_user.id:
        await callback.answer("Это чужая вылазка.", show_alert=True)
        return
    if int(session.get("processing") or 0):
        await callback.answer("Кот еще машет киркой, секунду.", show_alert=True)
        return

    result = settle_interactive_dig(session, callback.from_user, collapsed=False)
    await safe_edit(
        callback,
        result.text,
        reply_markup=user_mine_menu(int(session["chat_id"]), callback.from_user.id, show_back=False),
    )
    await callback.answer("Добыча забрана.")


@router.callback_query(F.data == "ui:help")
async def cb_help(callback: CallbackQuery) -> None:
    await safe_edit(
        callback,
        "Как пользоваться:\n"
        "1. Добавь бота в группу или чат обсуждений.\n"
        "2. Один раз отправь в группе /register_chat.\n"
        "3. Вернись сюда, выбери группу кнопкой и настраивай ответы.\n\n"
        "В группе бот отвечает на упоминания @username, фиксированные слова и фразу 'кто пидор'.",
        reply_markup=admin_back_menu(),
    )
    await callback.answer()


@router.callback_query(F.data == "ui:clear_chat")
async def cb_clear_chat(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_bot_admin(callback.from_user.id):
        await callback.answer("Доступно только владельцу.", show_alert=True)
        return
    await state.clear()
    if not callback.message:
        await callback.answer("Не вижу сообщение для очистки.", show_alert=True)
        return

    current_id = callback.message.message_id
    deleted = 0
    for message_id in range(current_id - 1, max(0, current_id - 150), -1):
        try:
            await callback.bot.delete_message(callback.message.chat.id, message_id)
            deleted += 1
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
        except (TelegramBadRequest, TelegramForbiddenError, TelegramNotFound):
            continue

    await safe_edit(
        callback,
        f"Чат очищен выше этого сообщения.\nУдалено сообщений: <b>{deleted}</b>.",
        reply_markup=admin_back_menu(),
    )
    await callback.answer("Готово")


@router.callback_query(F.data == "feedback:start")
async def cb_feedback_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminInput.feedback)
    await safe_edit(
        callback,
        "Опиши ошибку или предложение одним сообщением. Я отправлю это администратору бота.",
        reply_markup=main_menu(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("dig:register"))
async def cb_dig_register(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не вижу сообщение регистрации.", show_alert=True)
        return
    parts = callback.data.split(":")
    owner_id = await resolve_dig_button_owner(callback, parts[2] if len(parts) > 2 else None)
    if owner_id is None:
        return
    block = db.get_dig_block(callback.from_user.id)
    if block:
        reason = str(block.get("reason") or "").strip()
        await callback.answer(
            "Доступ к шахте заблокирован." + (f" Причина: {reason}" if reason else ""),
            show_alert=True,
        )
        return

    is_private = callback.message.chat.type == "private"
    if not is_private and callback.message.chat.type not in SUPPORTED_CHAT_TYPES:
        await callback.answer("Регистрироваться можно в группе или в личном чате с ботом.", show_alert=True)
        return
    chat_id = 0 if is_private else callback.message.chat.id
    if not is_private:
        await register_current_chat(callback.message)
    user = callback.from_user
    created = db.register_dig_player(
        chat_id=chat_id,
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
    )
    if created:
        await callback.answer("Ты в игре.", show_alert=True)
        if is_private:
            await callback.message.answer(
                "Ты зарегистрирован в шахте.\n\n"
                "Теперь можно писать <code>копай</code> прямо здесь или открыть Mini App.",
                reply_markup=user_dig_mode_menu(0, user.id),
            )
        else:
            await callback.message.answer(
                f"{escape(dig_player_name(user.username, user.full_name))} зарегистрировался в раскопках.\n"
                "Теперь можно писать: <code>копай</code>"
            )
    else:
        await callback.answer("Ты уже зарегистрирован.", show_alert=True)


@router.callback_query(F.data.startswith("dig:bag"))
async def cb_dig_bag(callback: CallbackQuery) -> None:
    if not callback.message or callback.message.chat.type not in SUPPORTED_CHAT_TYPES:
        await callback.answer("Сумка доступна в группе.", show_alert=True)
        return

    parts = callback.data.split(":")
    owner_id = await resolve_dig_button_owner(callback, parts[2] if len(parts) > 2 else None)
    if owner_id is None:
        return

    player = db.get_dig_player(callback.message.chat.id, callback.from_user.id)
    if player is None:
        await callback.answer("Сначала зарегистрируйся.", show_alert=True)
        return

    text = dig_bag_text(callback.message.chat.id, callback.from_user.id)
    if text is None:
        await callback.answer("Сначала зарегистрируйся.", show_alert=True)
        return
    await safe_edit(
        callback,
        text,
        reply_markup=dig_bag_menu(callback.from_user.id),
    )
    schedule_message_delete(callback.message, 30)
    await callback.answer()


@router.callback_query(F.data.startswith("user:routes:"))
async def cb_user_routes(callback: CallbackQuery) -> None:
    _, _, chat_raw, owner_raw = callback.data.split(":", 3)
    chat_id, owner_id = int(chat_raw), int(owner_raw)
    if not await require_dig_button_owner(callback, owner_id):
        return
    progress = db.get_dig_progress(owner_id)
    routes = [(key, data[0], key == progress["selected_route"]) for key, data in DIG_ROUTES.items()]
    await safe_edit(callback, dig_routes_text(owner_id), reply_markup=user_routes_menu(chat_id, owner_id, routes))
    await callback.answer()


@router.callback_query(F.data.startswith("user:route:"))
async def cb_user_route_select(callback: CallbackQuery) -> None:
    _, _, chat_raw, owner_raw, route_key = callback.data.split(":", 4)
    chat_id, owner_id = int(chat_raw), int(owner_raw)
    if not await require_dig_button_owner(callback, owner_id):
        return
    route = DIG_ROUTES.get(route_key)
    progress = db.get_dig_progress(owner_id)
    if route is None or int(progress["level"]) < route[5]:
        await callback.answer("Маршрут пока закрыт.", show_alert=True)
        return
    db.set_dig_route(owner_id, route_key)
    routes = [(key, data[0], key == route_key) for key, data in DIG_ROUTES.items()]
    await safe_edit(callback, dig_routes_text(owner_id), reply_markup=user_routes_menu(chat_id, owner_id, routes))
    await callback.answer(f"Выбран маршрут: {route[0]}")


@router.callback_query(F.data.startswith("user:contracts:"))
async def cb_user_contracts(callback: CallbackQuery) -> None:
    _, _, chat_raw, owner_raw = callback.data.split(":", 3)
    chat_id, owner_id = int(chat_raw), int(owner_raw)
    if not await require_dig_button_owner(callback, owner_id):
        return
    await safe_edit(callback, dig_contracts_text(owner_id), reply_markup=user_bag_menu(chat_id, owner_id))
    await callback.answer()


@router.callback_query(F.data.startswith("user:shift:"))
async def cb_user_rank_shift(callback: CallbackQuery) -> None:
    _, _, chat_raw, owner_raw = callback.data.split(":", 3)
    chat_id, owner_id = int(chat_raw), int(owner_raw)
    if not await require_dig_button_owner(callback, owner_id):
        return
    selected = dig_rank_shift_contract(owner_id)
    keys = [] if selected or dig_rank_name(dig_items_map(0, owner_id)) == "Новичок" else list(DIG_RANK_SHIFT_CONTRACTS)
    await safe_edit(callback, dig_rank_shift_text(owner_id), reply_markup=user_shift_contract_menu(chat_id, owner_id, keys) if keys else user_bag_menu(chat_id, owner_id))
    await callback.answer()


@router.callback_query(F.data.startswith("user:shiftpick:"))
async def cb_user_rank_shift_pick(callback: CallbackQuery) -> None:
    _, _, chat_raw, owner_raw, contract_key = callback.data.split(":", 4)
    chat_id, owner_id = int(chat_raw), int(owner_raw)
    if not await require_dig_button_owner(callback, owner_id):
        return
    error = select_dig_rank_shift_contract(owner_id, contract_key)
    if error:
        await callback.answer(error, show_alert=True)
        return
    await safe_edit(callback, dig_rank_shift_text(owner_id), reply_markup=user_bag_menu(chat_id, owner_id))
    await callback.answer("Сменное задание выбрано.")


@router.callback_query(F.data.startswith("user:expedition:"))
async def cb_user_expedition(callback: CallbackQuery) -> None:
    _, _, chat_raw, owner_raw = callback.data.split(":", 3)
    chat_id, owner_id = int(chat_raw), int(owner_raw)
    if not await require_dig_button_owner(callback, owner_id):
        return
    await safe_edit(callback, dig_expedition_text(chat_id), reply_markup=user_bag_menu(chat_id, owner_id))
    await callback.answer()


@router.callback_query(F.data.startswith("dig:routes:"))
async def cb_dig_routes(callback: CallbackQuery) -> None:
    owner_id = int(callback.data.split(":", 2)[2])
    if not await require_dig_button_owner(callback, owner_id):
        return
    progress = db.get_dig_progress(callback.from_user.id)
    routes = [(key, data[0], key == progress["selected_route"]) for key, data in DIG_ROUTES.items()]
    await safe_edit(callback, dig_routes_text(callback.from_user.id), reply_markup=dig_routes_menu(owner_id, routes))
    await callback.answer()


@router.callback_query(F.data.startswith("dig:route:"))
async def cb_dig_route_select(callback: CallbackQuery) -> None:
    _, _, owner_raw, route_key = callback.data.split(":", 3)
    owner_id = int(owner_raw)
    if not await require_dig_button_owner(callback, owner_id):
        return
    route = DIG_ROUTES.get(route_key)
    if route is None:
        await callback.answer("Маршрут не найден.", show_alert=True)
        return
    progress = db.get_dig_progress(owner_id)
    if int(progress["level"]) < route[5]:
        await callback.answer(f"Маршрут откроется на {route[5]} уровне.", show_alert=True)
        return
    db.set_dig_route(owner_id, route_key)
    routes = [(key, data[0], key == route_key) for key, data in DIG_ROUTES.items()]
    await safe_edit(callback, dig_routes_text(owner_id), reply_markup=dig_routes_menu(owner_id, routes))
    await callback.answer(f"Выбран маршрут: {route[0]}")


@router.callback_query(F.data.startswith("dig:contracts:"))
async def cb_dig_contracts(callback: CallbackQuery) -> None:
    owner_id = int(callback.data.split(":", 2)[2])
    if not await require_dig_button_owner(callback, owner_id):
        return
    await safe_edit(callback, dig_contracts_text(owner_id), reply_markup=dig_section_back_menu(owner_id))
    await callback.answer()


@router.callback_query(F.data.startswith("dig:shiftpick:"))
async def cb_dig_rank_shift_pick(callback: CallbackQuery) -> None:
    _, _, _, owner_raw, contract_key = callback.data.split(":", 4)
    owner_id = int(owner_raw)
    if not await require_dig_button_owner(callback, owner_id):
        return
    error = select_dig_rank_shift_contract(owner_id, contract_key)
    if error:
        await callback.answer(error, show_alert=True)
        return
    await safe_edit(callback, dig_rank_shift_text(owner_id), reply_markup=dig_section_back_menu(owner_id))
    await callback.answer("Сменное задание выбрано.")


@router.callback_query(F.data.startswith("dig:shift:"))
async def cb_dig_rank_shift(callback: CallbackQuery) -> None:
    owner_id = int(callback.data.split(":", 2)[2])
    if not await require_dig_button_owner(callback, owner_id):
        return
    selected = dig_rank_shift_contract(owner_id)
    keys = [] if selected or dig_rank_name(dig_items_map(0, owner_id)) == "Новичок" else list(DIG_RANK_SHIFT_CONTRACTS)
    await safe_edit(callback, dig_rank_shift_text(owner_id), reply_markup=dig_shift_contract_menu(owner_id, keys) if keys else dig_section_back_menu(owner_id))
    await callback.answer()


@router.callback_query(F.data.startswith("dig:expedition:"))
async def cb_dig_expedition(callback: CallbackQuery) -> None:
    owner_id = int(callback.data.split(":", 2)[2])
    if not await require_dig_button_owner(callback, owner_id):
        return
    if not callback.message or callback.message.chat.type not in SUPPORTED_CHAT_TYPES:
        await callback.answer("Экспедиция доступна в группе.", show_alert=True)
        return
    await safe_edit(callback, dig_expedition_text(callback.message.chat.id), reply_markup=dig_section_back_menu(owner_id))
    await callback.answer()


@router.callback_query(F.data.startswith("dig:shop"))
async def cb_dig_shop(callback: CallbackQuery) -> None:
    if not callback.message or callback.message.chat.type not in SUPPORTED_CHAT_TYPES:
        await callback.answer("Магазин доступен в группе.", show_alert=True)
        return

    parts = callback.data.split(":")
    owner_id = await resolve_dig_button_owner(callback, parts[2] if len(parts) > 2 else None)
    if owner_id is None:
        return
    category = parts[3] if len(parts) > 3 else None
    if category not in DIG_SHOP_CATEGORIES:
        category = None
    try:
        page = int(parts[4]) if len(parts) > 4 else 0
    except ValueError:
        page = 0
    player = db.get_dig_player(callback.message.chat.id, callback.from_user.id)
    if player is None:
        await callback.answer("Сначала зарегистрируйся.", show_alert=True)
        return

    items = dig_items_map(player.chat_id, player.user_id)
    if category:
        page_items, page, total_pages = dig_shop_page_items(category, items, page)
        await safe_edit(
            callback,
            dig_shop_category_text(player.coins, category, page, total_pages),
            reply_markup=dig_shop_items_menu(callback.from_user.id, category, page, total_pages, page_items),
        )
        await callback.answer()
        return

    await safe_edit(
        callback,
        dig_shop_overview_text(player.coins, items),
        reply_markup=dig_shop_categories_menu(callback.from_user.id, dig_shop_categories_for_keyboard()),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("dig:donate:"))
async def cb_dig_donate(callback: CallbackQuery) -> None:
    if not callback.message or callback.message.chat.type not in SUPPORTED_CHAT_TYPES:
        await callback.answer("Покупки шахты доступны в группе.", show_alert=True)
        return

    owner_id = int(callback.data.split(":", 2)[2])
    if not await require_dig_button_owner(callback, owner_id):
        return
    if db.get_dig_player(callback.message.chat.id, callback.from_user.id) is None:
        await callback.answer("Сначала зарегистрируйся.", show_alert=True)
        return

    await callback.answer(url=miniapp_deep_link(f"shop_{callback.from_user.id}"))


@router.callback_query(F.data.startswith("dig:star:"))
async def cb_dig_star(callback: CallbackQuery) -> None:
    if not callback.message or callback.message.chat.type not in SUPPORTED_CHAT_TYPES:
        await callback.answer("Сумка доступна в группе.", show_alert=True)
        return

    parts = callback.data.split(":", 3)
    if len(parts) != 4 or parts[2] not in DIG_STAR_ACTIONS or not parts[3].isdigit():
        await callback.answer("Кнопка устарела. Открой сумку заново.", show_alert=True)
        return

    action = parts[2]
    owner_id = int(parts[3])
    if not await require_dig_button_owner(callback, owner_id):
        return

    player = db.get_dig_player(callback.message.chat.id, callback.from_user.id)
    if player is None:
        await callback.answer("Сначала зарегистрируйся.", show_alert=True)
        return

    title, description, price = dig_star_invoice(action)

    try:
        await callback.bot.send_invoice(
            chat_id=callback.from_user.id,
            title=title,
            description=description,
            payload=dig_star_payload(action, callback.from_user.id, callback.message.chat.id),
            currency="XTR",
            prices=[LabeledPrice(label=title, amount=price)],
            provider_token="",
        )
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        await callback.answer(
            "Не получилось отправить счет в личку. Открой бота в личных сообщениях и нажми /start, потом попробуй снова.",
            show_alert=True,
        )
        return
    await callback.answer("Счет отправлен в личку.")


@router.callback_query(F.data.startswith("user:star:"))
async def cb_user_dig_star(callback: CallbackQuery) -> None:
    parts = callback.data.split(":", 4)
    if len(parts) != 5 or parts[2] not in DIG_STAR_ACTIONS or not parts[3].lstrip("-").isdigit() or not parts[4].isdigit():
        await callback.answer("Кнопка устарела. Открой сумку заново.", show_alert=True)
        return

    action = parts[2]
    chat_id = int(parts[3])
    owner_id = int(parts[4])
    if not await require_dig_button_owner(callback, owner_id):
        return
    if not await is_chat_member(callback.bot, chat_id, callback.from_user.id):
        await callback.answer("Ты больше не состоишь в этой группе.", show_alert=True)
        return
    if db.get_dig_player(chat_id, callback.from_user.id) is None:
        await callback.answer("Сначала зарегистрируйся в шахте командой копай внутри группы.", show_alert=True)
        return

    title, description, price = dig_star_invoice(action)

    try:
        await callback.bot.send_invoice(
            chat_id=callback.from_user.id,
            title=title,
            description=description,
            payload=dig_star_payload(action, callback.from_user.id, chat_id),
            currency="XTR",
            prices=[LabeledPrice(label=title, amount=price)],
            provider_token="",
        )
    except (TelegramBadRequest, TelegramForbiddenError):
        await callback.answer("Не получилось отправить счет. Нажми /start и попробуй снова.", show_alert=True)
        return
    await callback.answer("Счет отправлен.")


@router.callback_query(F.data == "miniapp:open")
async def cb_miniapp_open(callback: CallbackQuery) -> None:
    await callback.answer(
        "Mini App пока не настроен. Укажи MINI_APP_URL или ADMIN_PUBLIC_URL в .env и перезапусти бота.",
        show_alert=True,
    )


@router.callback_query(F.data.startswith("dig:open_store:"))
async def cb_dig_open_store(callback: CallbackQuery) -> None:
    requested_user_id = int(callback.data.rsplit(":", 1)[1])
    if requested_user_id != callback.from_user.id:
        await callback.answer("Эта кнопка принадлежит другому пользователю.", show_alert=True)
        return
    try:
        await callback.bot.send_message(
            callback.from_user.id,
            "Магазин шахты находится в Mini App.",
            reply_markup=miniapp_private_menu("Открыть магазин", view="shop"),
        )
    except (TelegramBadRequest, TelegramForbiddenError):
        await callback.answer(
            "Сначала открой личный чат с ботом, нажми /start и повтори попытку.",
            show_alert=True,
        )
        return
    await callback.answer("Кнопка магазина отправлена в личный чат.", show_alert=True)


@router.callback_query(F.data == "gold_ticket:buy")
async def cb_buy_golden_ticket(callback: CallbackQuery) -> None:
    if not callback.from_user:
        await callback.answer("Не получилось определить пользователя.", show_alert=True)
        return
    title, description, price = dig_star_invoice("golden_ticket")
    try:
        await callback.bot.send_invoice(
            chat_id=callback.from_user.id,
            title=title,
            description=description,
            payload=dig_star_payload("golden_ticket", callback.from_user.id, 0),
            currency="XTR",
            prices=[LabeledPrice(label=title, amount=price)],
            provider_token="",
        )
    except (TelegramBadRequest, TelegramForbiddenError):
        await callback.answer("Открой личный чат с ботом и нажми /start.", show_alert=True)
        return
    await callback.answer("Счет на 2 ⭐ отправлен в личку.")


@router.callback_query(F.data.startswith("dig:achievements:"))
async def cb_dig_achievements(callback: CallbackQuery) -> None:
    if not callback.message or callback.message.chat.type not in SUPPORTED_CHAT_TYPES:
        await callback.answer("Достижения доступны в группе.", show_alert=True)
        return

    parts = callback.data.split(":")
    owner_id = await resolve_dig_button_owner(callback, parts[2] if len(parts) > 2 else None)
    if owner_id is None:
        return

    player = db.get_dig_player(callback.message.chat.id, callback.from_user.id)
    if player is None:
        await callback.answer("Сначала зарегистрируйся.", show_alert=True)
        return

    await safe_edit(
        callback,
        dig_achievements_text(callback.message.chat.id, callback.from_user.id),
        reply_markup=dig_bag_menu(callback.from_user.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("dig:buy:"))
async def cb_dig_buy(callback: CallbackQuery) -> None:
    if not callback.message or callback.message.chat.type not in SUPPORTED_CHAT_TYPES:
        await callback.answer("Магазин доступен в группе.", show_alert=True)
        return

    parts = callback.data.split(":", 3)
    if len(parts) == 4 and parts[2].isdigit():
        owner_raw = parts[2]
        item_key = parts[3]
    else:
        owner_raw = None
        item_key = callback.data.split(":", 2)[2]
    owner_id = await resolve_dig_button_owner(callback, owner_raw)
    if owner_id is None:
        return

    item = DIG_SHOP_ITEMS.get(item_key)
    if item is None:
        await callback.answer("Предмет не найден.", show_alert=True)
        return

    player = db.get_dig_player(callback.message.chat.id, callback.from_user.id)
    if player is None:
        await callback.answer("Сначала зарегистрируйся.", show_alert=True)
        return

    name, _, description = item
    items = dig_items_map(callback.message.chat.id, callback.from_user.id)
    price = dig_shop_price(item_key, items)
    discount = dig_rank_discount(items) if item_key in dig_discountable_item_keys() else 0
    discount_text = f"\nСкидка ранга: <b>{discount}%</b>" if discount else ""
    await safe_edit(
        callback,
        f"<b>{escape(name)}</b>\n"
        f"Цена: <b>{price}</b> котоинов{discount_text}\n"
        f"У тебя: <b>{player.coins}</b> котоинов\n\n"
        f"{escape(description)}",
        reply_markup=dig_buy_confirm_menu(callback.from_user.id, item_key),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("dig:confirm:"))
async def cb_dig_confirm(callback: CallbackQuery) -> None:
    if not callback.message or callback.message.chat.type not in SUPPORTED_CHAT_TYPES:
        await callback.answer("Магазин доступен в группе.", show_alert=True)
        return

    parts = callback.data.split(":", 3)
    if len(parts) == 4 and parts[2].isdigit():
        owner_raw = parts[2]
        item_key = parts[3]
    else:
        owner_raw = None
        item_key = callback.data.split(":", 2)[2]
    owner_id = await resolve_dig_button_owner(callback, owner_raw)
    if owner_id is None:
        return

    item = DIG_SHOP_ITEMS.get(item_key)
    if item is None:
        await callback.answer("Предмет не найден.", show_alert=True)
        return

    chat_id = callback.message.chat.id
    player = db.get_dig_player(chat_id, callback.from_user.id)
    if player is None:
        await callback.answer("Сначала зарегистрируйся.", show_alert=True)
        return

    if dig_purchase_is_duplicate(chat_id, callback.from_user.id, item_key, callback.message.message_id):
        await callback.answer("Покупка уже обрабатывается.", show_alert=True)
        return

    items = dig_items_map(chat_id, callback.from_user.id)
    purchase_error = dig_purchase_error(items, item_key)
    if purchase_error:
        await callback.answer(purchase_error, show_alert=True)
        return

    name, _, _ = item
    price = dig_shop_price(item_key, items)
    result = f"Куплено: <b>{escape(name)}</b>."
    if item_key == "prank":
        if not db.spend_dig_coins(chat_id, callback.from_user.id, price):
            await callback.answer("Не хватает котоинов.", show_alert=True)
            return
        prank_text = f"{escape(dig_player_name(callback.from_user.username, callback.from_user.full_name))} оформил шахтерскую проверку. Кто-то явно копает не туда."
        try:
            await callback.message.answer(prank_text)
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            db.add_dig_coins(chat_id, callback.from_user.id, price)
            await callback.answer("Не получилось отправить подставу, котоины возвращены.", show_alert=True)
            await safe_edit(
                callback,
                "Не получилось отправить подставу, котоины возвращены.\n"
                f"<code>{escape(str(exc))}</code>",
                reply_markup=dig_shop_categories_menu(callback.from_user.id, dig_shop_categories_for_keyboard()),
            )
            return
        result = "Подстава куплена и отправлена в чат."
    else:
        purchase_status = db.purchase_dig_item(
            chat_id,
            callback.from_user.id,
            item_key,
            price,
            quantity=1,
            unique=item_key in DIG_PERMANENT_ITEMS,
        )
        if purchase_status == "owned":
            await callback.answer("Это улучшение уже куплено.", show_alert=True)
            return
        if purchase_status == "no_coins":
            await callback.answer("Не хватает котоинов.", show_alert=True)
            return

    updated = db.get_dig_player(chat_id, callback.from_user.id)
    achievement_text = award_dig_achievement(chat_id, callback.from_user.id, "first_purchase")
    items = dig_items_map(chat_id, callback.from_user.id)
    category = dig_shop_category_for_item(item_key)
    page_items, page, total_pages = dig_shop_page_items(category, items, 0)
    achievement_block = f"\n\n<b>Достижение:</b>\n{escape(achievement_text)}" if achievement_text else ""
    await safe_edit(
        callback,
        f"{result}\n\n"
        f"Котоины: <b>{updated.coins if updated else 0}</b>\n\n"
        f"<b>Активные эффекты:</b>\n{escape(dig_effects_text(items))}"
        f"{achievement_block}",
        reply_markup=dig_shop_items_menu(callback.from_user.id, category, page, total_pages, page_items),
    )
    await callback.answer("Куплено")


@router.callback_query(F.data.startswith("feedback:reply:"))
async def cb_feedback_reply(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_bot_admin(callback.from_user.id):
        await callback.answer("Ответ доступен только администратору бота.", show_alert=True)
        return

    user_id = int(callback.data.split(":", 2)[2])
    await state.set_state(AdminInput.feedback_reply)
    await state.update_data(feedback_user_id=user_id)
    await safe_edit(
        callback,
        f"Напиши ответ пользователю <code>{user_id}</code>. Я отправлю его от имени бота.",
        reply_markup=main_menu(),
    )
    await callback.answer()


@router.message(Command("feedback"))
async def feedback_command(message: Message, state: FSMContext) -> None:
    if message.chat.type != "private":
        return
    await state.set_state(AdminInput.feedback)
    await message.answer("Опиши ошибку или предложение одним сообщением. Я отправлю это администратору бота.")


@router.callback_query(F.data == "ui:status")
async def cb_status(callback: CallbackQuery) -> None:
    chats = await admin_chats_for_user(callback.bot, callback.from_user.id)
    if not chats:
        await safe_edit(callback, "Нет доступных групп, где ты админ.", reply_markup=admin_back_menu())
        await callback.answer()
        return

    bot_user = await callback.bot.me()
    lines = ["<b>Проверка групп:</b>"]
    for item in chats:
        try:
            member = await callback.bot.get_chat_member(item.chat_id, bot_user.id)
            status = member_status_text(member.status)
        except (TelegramBadRequest, TelegramForbiddenError):
            status = "нет доступа"
        lines.append(f"{mention_chat_link(item)} - {escape(status)}")

    await safe_edit(callback, "\n".join(lines), reply_markup=admin_back_menu())
    await callback.answer()


@router.callback_query(F.data == "ui:whoami")
async def cb_whoami(callback: CallbackQuery) -> None:
    if not is_bot_admin(callback.from_user.id):
        await callback.answer("Панель владельца доступна только владельцу.", show_alert=True)
        return
    bot_admin = is_bot_admin(callback.from_user.id)
    admin_roles = await user_admin_roles(callback.bot, callback.from_user.id)
    has_chat_admin = bool(admin_roles)

    if bot_admin and has_chat_admin:
        status = "админ бота и админ групп"
    elif bot_admin:
        status = "админ бота"
    elif has_chat_admin:
        status = "админ групп"
    else:
        status = "обычный пользователь"

    lines = [
        "<b>Кто я</b>",
        f"Telegram id: <code>{callback.from_user.id}</code>",
        f"Статус: <b>{escape(status)}</b>",
    ]

    if bot_admin:
        lines.append("Доступ в панели: все группы, где есть бот.")
    elif has_chat_admin:
        lines.append("Доступ в панели: только группы, где ты админ.")
    else:
        lines.append("Доступ в панели: нет доступных групп.")

    lines.append("\n<b>Группы, где ты админ:</b>")
    if not admin_roles:
        lines.append("Не найдено.")
    else:
        for chat, role in admin_roles:
            lines.append(f"{mention_chat(chat)} - <code>{escape(role)}</code>")

    await safe_edit(callback, "\n".join(lines), reply_markup=admin_back_menu())
    await callback.answer()


@router.callback_query(F.data == "ui:restart")
async def cb_restart(callback: CallbackQuery) -> None:
    if not is_bot_admin(callback.from_user.id):
        await callback.answer("Перезагрузка доступна только администратору бота.", show_alert=True)
        return

    await safe_edit(
        callback,
        "Перезапустить бота сейчас?\n\n"
        "Процесс будет перезапущен на этой машине.",
        reply_markup=restart_confirm_menu(),
    )
    await callback.answer()


@router.callback_query(F.data == "paid:chats")
async def cb_paid_chats(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    chats = await paid_chats_for_user(callback.bot, callback.from_user.id)
    if not chats:
        await safe_edit(
            callback,
            "Пока нет доступных групп для платной публикации.",
            reply_markup=main_menu(),
        )
        await callback.answer()
        return

    await safe_edit(
        callback,
        "Выбери группу, куда бот опубликует платное сообщение.",
        reply_markup=paid_chat_select_menu(chats),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("paid:chat:"))
async def cb_paid_chat(callback: CallbackQuery, state: FSMContext) -> None:
    chat_id = int(callback.data.split(":", 2)[2])
    chat = db.get_chat(chat_id)
    if chat is None:
        await callback.answer("Группа не найдена.", show_alert=True)
        return
    if not await is_chat_member(callback.bot, chat_id, callback.from_user.id):
        await callback.answer("Платная публикация доступна только в группах, где ты состоишь.", show_alert=True)
        return

    await state.set_state(AdminInput.paid_message)
    await state.update_data(chat_id=chat_id)
    await safe_edit(
        callback,
        f"Группа: <b>{mention_chat(chat)}</b>\n\n"
        "Отправь текст платного сообщения. Цена публикации: <b>1 ⭐</b>.",
        reply_markup=main_menu(),
    )
    await callback.answer()


@router.callback_query(F.data == "restart:yes")
async def cb_restart_confirm(callback: CallbackQuery) -> None:
    if not is_bot_admin(callback.from_user.id):
        await callback.answer("Перезагрузка доступна только администратору бота.", show_alert=True)
        return

    if callback.message:
        remember_restart_panel_chat(callback.message.chat.id)
    await safe_edit(callback, "Перезапускаюсь...", reply_markup=None)
    await callback.answer()
    asyncio.create_task(restart_process())


@router.callback_query(F.data == "stars:menu")
async def cb_stars_menu(callback: CallbackQuery) -> None:
    if not is_bot_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администратору бота.", show_alert=True)
        return

    await safe_edit(callback, "Раздел Stars.", reply_markup=stars_menu())
    await callback.answer()


@router.callback_query(F.data == "stars:balance")
async def cb_stars_balance(callback: CallbackQuery) -> None:
    if not is_bot_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администратору бота.", show_alert=True)
        return

    try:
        balance = await telegram_api_get(callback.bot, "getMyStarBalance")
        amount = balance.get("amount", 0)
        nanostar_amount = balance.get("nanostar_amount")
    except TelegramBadRequest as exc:
        await safe_edit(
            callback,
            f"Не получилось получить баланс Stars.\n<code>{escape(str(exc))}</code>",
            reply_markup=stars_menu(),
        )
        await callback.answer()
        return

    extra = f"\nNanostars: <code>{nanostar_amount}</code>" if nanostar_amount is not None else ""
    await safe_edit(callback, f"Баланс бота: <b>{amount} ⭐</b>{extra}", reply_markup=stars_menu())
    await callback.answer()


@router.callback_query(F.data == "stars:payers")
async def cb_stars_payers(callback: CallbackQuery) -> None:
    if not is_bot_admin(callback.from_user.id):
        await callback.answer("Раздел доступен только администратору бота.", show_alert=True)
        return

    payments = db.list_star_payments(limit=25)
    lines = ["<b>Последние оплаты Stars:</b>"]
    if not payments:
        lines.append("Пока оплат нет.")
    else:
        for payment in payments:
            username = f"@{payment.username}" if payment.username else payment.full_name
            chat = db.get_chat(payment.chat_id) if payment.chat_id else None
            chat_title_text = chat.title if chat else str(payment.chat_id or "-")
            lines.append(
                f"{payment.id}. {escape(username)} - <b>{payment.amount} в­ђ</b> "
                f"в {escape(chat_title_text)} · {escape(payment.created_at)}"
            )

    await safe_edit(callback, "\n".join(lines), reply_markup=stars_menu())
    await callback.answer()


@router.callback_query(F.data == "gift:start")
async def cb_gift_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer("Не вижу сообщение панели.", show_alert=True)
        return
    if not is_bot_admin(callback.from_user.id):
        await callback.answer("Подарки доступны только администраторам бота.", show_alert=True)
        return
    await callback.answer("Загружаю подарки...")
    await start_gift_flow(callback.message, state, actor=callback.from_user)


@router.callback_query(F.data.startswith("gift:list:"))
async def cb_gift_list(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        await callback.answer("Кнопка устарела.", show_alert=True)
        return
    token = parts[2]
    page = int(parts[3]) if parts[3].isdigit() else 0
    flow = await get_gift_flow_from_callback(callback, token)
    if flow is None:
        return
    balance = await bot_star_balance(callback.bot)
    await safe_edit(callback, gift_list_text(flow, balance), reply_markup=gift_flow_markup(flow, page))
    await callback.answer()


@router.callback_query(F.data.startswith("gift:pick:"))
async def cb_gift_pick(callback: CallbackQuery, state: FSMContext) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        await callback.answer("Кнопка устарела.", show_alert=True)
        return
    token = parts[2]
    index = int(parts[3]) if parts[3].isdigit() else -1
    flow = await get_gift_flow_from_callback(callback, token)
    if flow is None:
        return
    if index < 0 or index >= len(flow.gifts):
        await callback.answer("Подарок больше не найден. Начни заново.", show_alert=True)
        return
    selected_gift = flow.gifts[index]
    flow.selected_gift_id = selected_gift.gift_id
    if callback.message and selected_gift.sticker_file_id:
        with suppress(TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter):
            await callback.message.answer_sticker(selected_gift.sticker_file_id)
    if flow.recipient_id is None:
        await state.set_state(AdminInput.gift_recipient)
        await state.update_data(gift_token=token)
        await safe_edit(
            callback,
            "Подарок выбран.\n\n"
            "Теперь отправь numeric Telegram user_id получателя.\n"
            "Можно отменить операцию кнопкой ниже.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data=f"gift:cancel:{token}")]]
            ),
        )
        await callback.answer()
        return
    balance = await bot_star_balance(callback.bot)
    await safe_edit(callback, gift_confirm_text(flow, balance), reply_markup=gift_confirm_markup(flow))
    await callback.answer()


@router.message(AdminInput.gift_recipient)
async def ui_gift_recipient(message: Message, state: FSMContext) -> None:
    if not message.from_user or not is_bot_admin(message.from_user.id):
        await state.clear()
        await message.answer("Операция отменена: подарки доступны только администраторам бота.")
        return
    data = await state.get_data()
    token = data.get("gift_token")
    if not isinstance(token, str):
        await state.clear()
        await message.answer("Операция устарела. Запусти /gift заново.")
        return
    payload = (message.text or "").strip()
    if payload.casefold() in {"отмена", "cancel", "/cancel"}:
        GIFT_SELECTIONS.pop(token, None)
        GIFT_CONFIRM_IN_PROGRESS.discard(token)
        GIFT_COMPLETED.pop(token, None)
        await state.clear()
        await message.answer("Операция отправки подарка отменена.", reply_markup=stars_menu())
        return
    cleanup_gift_flows()
    flow = GIFT_SELECTIONS.get(token)
    if flow is None or gift_flow_expired(flow) or flow.admin_id != message.from_user.id:
        await state.clear()
        await message.answer("Операция устарела. Запусти /gift заново.")
        return
    recipient_id, recipient_label, error = await resolve_gift_recipient_from_message(message, payload)
    if error:
        await message.answer(error)
        return
    if recipient_id is None:
        await message.answer("Отправь numeric Telegram user_id получателя или нажми «Отмена».")
        return
    flow.recipient_id = recipient_id
    flow.recipient_label = recipient_label
    await state.clear()
    balance = await bot_star_balance(message.bot)
    await message.answer(gift_confirm_text(flow, balance), reply_markup=gift_confirm_markup(flow))


@router.callback_query(F.data.startswith("gift:cancel:"))
async def cb_gift_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    parts = (callback.data or "").split(":", 2)
    token = parts[2] if len(parts) == 3 else ""
    flow = GIFT_SELECTIONS.get(token)
    if flow is not None and flow.admin_id != callback.from_user.id:
        await callback.answer("Эта операция принадлежит другому администратору.", show_alert=True)
        return
    GIFT_SELECTIONS.pop(token, None)
    GIFT_CONFIRM_IN_PROGRESS.discard(token)
    GIFT_COMPLETED.pop(token, None)
    await state.clear()
    await safe_edit(callback, "Операция отправки подарка отменена.", reply_markup=stars_menu())
    await callback.answer("Отменено")


@router.callback_query(F.data.startswith("gift:send:"))
async def cb_gift_send(callback: CallbackQuery, state: FSMContext) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer("Кнопка устарела.", show_alert=True)
        return
    token = parts[2]
    flow = await get_gift_flow_from_callback(callback, token)
    if flow is None:
        return
    if token in GIFT_COMPLETED:
        await callback.answer("Этот подарок уже был отправлен.", show_alert=True)
        return
    if token in GIFT_CONFIRM_IN_PROGRESS:
        await callback.answer("Отправка уже выполняется.", show_alert=True)
        return
    gift = gift_by_id(flow)
    if gift is None or flow.recipient_id is None:
        await callback.answer("Данные операции неполные. Начни заново.", show_alert=True)
        return

    GIFT_CONFIRM_IN_PROGRESS.add(token)
    try:
        fresh_gifts = await callback.bot.get_available_gifts()
        fresh = next((gift_summary(item) for item in fresh_gifts.gifts if item.id == gift.gift_id), None)
        if fresh is None or (fresh.remaining_count is not None and fresh.remaining_count <= 0):
            await safe_edit(callback, "Этот подарок больше недоступен. Запусти /gift заново.", reply_markup=stars_menu())
            GIFT_SELECTIONS.pop(token, None)
            await callback.answer("Подарок недоступен", show_alert=True)
            return
        if fresh.star_count != gift.star_count:
            gift.star_count = fresh.star_count
            gift.remaining_count = fresh.remaining_count
            gift.total_count = fresh.total_count
        balance = await bot_star_balance(callback.bot)
        if balance is not None and int(balance.amount or 0) < gift.star_count:
            await safe_edit(
                callback,
                "Недостаточно Stars на балансе бота.\n\n" + gift_confirm_text(flow, balance),
                reply_markup=gift_confirm_markup(flow),
            )
            await callback.answer("Не хватает Stars", show_alert=True)
            return
        await callback.bot.send_gift(user_id=flow.recipient_id, gift_id=gift.gift_id)
        GIFT_COMPLETED[token] = time.monotonic()
        flow.confirmed = True
        balance_after = await bot_star_balance(callback.bot)
        await state.clear()
        await safe_edit(callback, gift_done_text(flow, balance_after), reply_markup=stars_menu())
        await callback.answer("Подарок отправлен")
    except TelegramForbiddenError as exc:
        await safe_edit(
            callback,
            "Не получилось отправить подарок: пользователь заблокировал бота или недоступен.\n"
            f"<code>{escape(str(exc))}</code>",
            reply_markup=stars_menu(),
        )
        await callback.answer("Пользователь недоступен", show_alert=True)
    except TelegramBadRequest as exc:
        description = str(exc)
        await safe_edit(
            callback,
            "Telegram Bot API вернул ошибку при отправке подарка.\n"
            "Возможные причины: не хватает Stars, неверный user_id, подарок больше недоступен "
            "или получатель не может принять подарок.\n\n"
            f"<code>{escape(description)}</code>",
            reply_markup=stars_menu(),
        )
        await callback.answer("Ошибка Telegram API", show_alert=True)
    except TelegramRetryAfter as exc:
        await safe_edit(
            callback,
            f"Telegram попросил повторить позже: {int(getattr(exc, 'retry_after', 1))} сек.",
            reply_markup=stars_menu(),
        )
        await callback.answer("Flood control", show_alert=True)
    finally:
        GIFT_CONFIRM_IN_PROGRESS.discard(token)


@router.callback_query(F.data.startswith("chat:"))
async def cb_select_chat(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    chat_id = int(callback.data.split(":", 1)[1])
    chat = await require_selected_admin(callback, chat_id)
    if chat is None:
        return

    allowed_features = None
    if not is_bot_admin(callback.from_user.id):
        allowed_features = {
            feature_id
            for feature_id, _ in ADMIN_FEATURES
            if bot_admin_feature_allowed(chat_id, callback.from_user.id, feature_id, mode="view", default=True)
        }
    await safe_edit(
        callback,
        f"Выбрана группа: <b>{mention_chat(chat)}</b>\nЧто настроим?",
        reply_markup=chat_admin_menu(chat_id, include_access=is_bot_admin(callback.from_user.id), allowed_features=allowed_features),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("list:"))
async def cb_trigger_list_page(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    _, chat_id_raw, page_raw = callback.data.split(":", 2)
    chat_id = int(chat_id_raw)
    page = int(page_raw)
    chat = await require_selected_admin(callback, chat_id)
    if chat is None:
        return
    if not await require_callback_feature(callback, "triggers", default=True):
        return

    text, page, total = trigger_page_text(chat_id, page)
    await safe_edit(callback, text, reply_markup=trigger_list_menu(chat_id, page, total))
    await callback.answer()


@router.callback_query(F.data.startswith("participants:top:"))
async def cb_participant_top(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    _, _, chat_id_raw, period = callback.data.split(":", 3)
    chat_id = int(chat_id_raw)
    chat = await require_selected_admin(callback, chat_id)
    if chat is None:
        return
    if not await require_callback_feature(callback, "participants", mode="view", default=True):
        return

    await safe_edit(callback, participant_top_text(chat_id, period), reply_markup=participant_top_menu(chat_id))
    await callback.answer()


@router.callback_query(F.data.startswith("act:"))
async def cb_action(callback: CallbackQuery, state: FSMContext) -> None:
    _, action, chat_id_raw = callback.data.split(":", 2)
    chat_id = int(chat_id_raw)
    chat = await require_selected_admin(callback, chat_id)
    if chat is None:
        return

    if action == "access":
        if not is_bot_admin(callback.from_user.id):
            await callback.answer("Доступ может менять только владелец.", show_alert=True)
            return
        await state.clear()
        await safe_edit(
            callback,
            f"Группа: <b>{mention_chat(chat)}</b>\n\nВыбери админа, которому нужно настроить права.",
            reply_markup=await access_admins_menu(callback.bot, chat_id),
        )
        await callback.answer()
        return

    if action == "access":
        if not is_bot_admin(callback.from_user.id):
            await callback.answer("Доступ может менять только владелец.", show_alert=True)
            return
        await state.set_state(AdminInput.set_access_user)
        await state.update_data(chat_id=chat_id)
        await safe_edit(
            callback,
            f"Группа: <b>{mention_chat(chat)}</b>\n\n"
            "Отправь Telegram ID пользователя, которому нужно настроить доступ к кнопкам панели.",
            reply_markup=back_to_chat_menu(chat_id),
        )
        await callback.answer()
        return

    feature = ACTION_FEATURES.get(action)
    if feature and not await require_callback_feature(callback, feature, mode="view", default=True):
        return

    if action == "moderators":
        if not is_bot_admin(callback.from_user.id):
            await callback.answer("Управление модераторами доступно только владельцу.", show_alert=True)
            return
        await state.clear()
        await safe_edit(callback, moderator_admin_panel_text(chat), reply_markup=moderator_panel_menu(chat_id))
        await callback.answer()
        return

    if action == "logs":
        await state.clear()
        items = db.list_audit_logs(chat_id, limit=30)
        lines = [f"Группа: <b>{mention_chat(chat)}</b>", "", "<b>Последние действия:</b>"]
        if not items:
            lines.append("Журнал пока пуст.")
        for item in items:
            actor = f"@{item.actor_username}" if item.actor_username else (item.actor_name or f"ID {item.actor_id}")
            lines.append(
                f"\n<b>{escape(item.action)}</b>\n"
                f"{escape(actor)} В· {escape(item.source)} В· <code>{escape(item.created_at)}</code>"
                + (f"\n<code>{escape(item.details)}</code>" if item.details else "")
            )
        await safe_edit(callback, "\n".join(lines), reply_markup=back_to_chat_menu(chat_id))
        await callback.answer()
        return

    if action == "set_reply":
        await state.set_state(AdminInput.set_reply)
        await state.update_data(chat_id=chat_id)
        await safe_edit(
            callback,
            f"Группа: <b>{mention_chat(chat)}</b>\n\n"
            "Отправь автоответ в формате:\n"
            "<code>@username - текст ответа</code>\n\n"
            "Можно прикрепить гиф, голос, аудио, видео или кружок.",
            reply_markup=back_to_chat_menu(chat_id),
        )
    elif action == "del_reply":
        await state.set_state(AdminInput.del_reply)
        await state.update_data(chat_id=chat_id)
        await safe_edit(
            callback,
            f"Группа: <b>{mention_chat(chat)}</b>\n\n"
            "Отправь username для удаления:\n"
            "<code>@username</code>",
            reply_markup=back_to_chat_menu(chat_id),
        )
    elif action == "set_trigger":
        await state.set_state(AdminInput.set_trigger)
        await state.update_data(chat_id=chat_id)
        await safe_edit(
            callback,
            f"Группа: <b>{mention_chat(chat)}</b>\n\n"
            "Отправь фиксированный ответ в формате:\n"
            "<code>слово - текст ответа</code>\n\n"
            "Можно прикрепить гиф, голос, аудио, видео или кружок.",
            reply_markup=back_to_chat_menu(chat_id),
        )
    elif action == "del_trigger":
        await state.set_state(AdminInput.del_trigger)
        await state.update_data(chat_id=chat_id)
        await safe_edit(
            callback,
            f"Группа: <b>{mention_chat(chat)}</b>\n\n"
            "Отправь номер слова из списка для удаления.",
            reply_markup=back_to_chat_menu(chat_id),
        )
    elif action == "list":
        text, page, total = trigger_page_text(chat_id, 0)
        await safe_edit(callback, text, reply_markup=trigger_list_menu(chat_id, page, total))
    elif action == "participants":
        await safe_edit(
            callback,
            participant_top_text(chat_id, "day"),
            reply_markup=participant_top_menu(chat_id),
        )
    elif action == "giveaway":
        await safe_edit(
            callback,
            f"Группа: <b>{mention_chat(chat)}</b>\n\nНастройки розыгрышей и дней рождения.",
            reply_markup=giveaway_menu(chat_id),
        )
        await callback.answer()
        return
    elif action == "giveaway":
        settings = db.get_giveaway_settings(chat_id)
        await state.set_state(AdminInput.set_giveaway)
        await state.update_data(chat_id=chat_id)
        await safe_edit(
            callback,
            f"Группа: <b>{mention_chat(chat)}</b>\n\n"
            "Отправь настройку розыгрыша в формате:\n"
            "<code>фраза вызова - количество - заголовок</code>\n\n"
            "Пример:\n"
            "<code>кто пидор - 3 - Пидоры дня</code>\n\n"
            f"Сейчас: <code>{escape(settings.trigger)} - {settings.winners_count} - {escape(settings.title)}</code>",
            reply_markup=back_to_chat_menu(chat_id),
        )
    elif action == "alarm":
        settings = db.get_alarm_settings(chat_id)
        await safe_edit(
            callback,
            f"Группа: <b>{mention_chat(chat)}</b>\n\n"
            f"Режим тревоги: <b>{'включен' if settings.enabled else 'выключен'}</b>\n\n"
            f"Автотревога Alerts.in.ua ({ALERTS_LOCATION_TITLE}): <b>{'включена' if db.alarm_api_enabled(chat_id) else 'выключена'}</b>\n\n"
            f"Ограничения медиа и реакций: <b>{'включены' if db.alarm_restrictions_enabled(chat_id) else 'выключены'}</b>\n\n"
            f"Текст тревоги: {preview_html(settings.alarm_text or 'Тревога включена: медиа, реакции и одиночные эмодзи отключены.')}\n"
            f"Текст отбоя: {preview_html(settings.clear_text or 'Отбой: медиа, реакции и одиночные эмодзи снова включены.')}",
            reply_markup=alarm_menu(
                chat_id,
                bool(settings.enabled),
                db.alarm_api_enabled(chat_id),
                db.alarm_restrictions_enabled(chat_id),
            ),
        )
    elif action == "roll_mute":
        if not is_bot_admin(callback.from_user.id):
            await callback.answer("Настройка доступна только администратору бота.", show_alert=True)
            return

        settings = db.get_roll_mute_settings(chat_id)
        await state.set_state(AdminInput.set_roll_mute)
        await state.update_data(chat_id=chat_id)
        await safe_edit(
            callback,
            f"Группа: <b>{mention_chat(chat)}</b>\n\n"
            "Настройка roll mute.\n"
            "Отправь два числа в минутах:\n"
            "<code>мут кулдаун</code>\n\n"
            "Пример: <code>60 30</code>\n\n"
            f"Сейчас: мут <b>{settings.mute_minutes}</b> мин, кулдаун <b>{settings.cooldown_minutes}</b> мин.",
            reply_markup=back_to_chat_menu(chat_id),
        )
    elif action == "quiet":
        settings = db.get_quiet_settings(chat_id)
        text_preview = preview_html(settings.reply_text or "{user} затих на <b>{minutes}</b> мин.{reason_line}")
        media_text = settings.media_type or "не выбрано"
        await safe_edit(
            callback,
            f"Группа: <b>{mention_chat(chat)}</b>\n\n"
            "<b>Настройка команды затихни</b>\n"
            f"Текст: {text_preview}\n"
            f"Медиа: <code>{escape(media_text)}</code>\n\n"
            "В тексте можно использовать: <code>{user}</code>, <code>{minutes}</code>, <code>{reason}</code>, <code>{reason_line}</code>.",
            reply_markup=quiet_menu(chat_id, bool(settings.media_file_id)),
        )
    elif action == "blacklist":
        await safe_edit(callback, blacklist_text(chat_id), reply_markup=blacklist_menu(chat_id))
    elif action == "quotes":
        text, page, total = quote_page_text(chat_id, 0)
        await safe_edit(callback, text, reply_markup=quotes_menu(chat_id, page, total))
    elif action == "check":
        bot_user = await callback.bot.me()
        try:
            member = await callback.bot.get_chat_member(chat_id, bot_user.id)
            status = member_status_text(member.status)
        except (TelegramBadRequest, TelegramForbiddenError):
            status = "нет доступа"
        await safe_edit(
            callback,
            f"Группа: <b>{mention_chat_link(chat)}</b>\nСтатус бота: <b>{escape(status)}</b>",
            reply_markup=back_to_chat_menu(chat_id),
        )
    elif action == "send_message":
        if await chat_is_forum(callback.bot, chat_id):
            topics = db.list_topics(chat_id)
        else:
            db.delete_topics(chat_id)
            topics = []
        if topics:
            await safe_edit(
                callback,
                f"Группа: <b>{mention_chat(chat)}</b>\n\n"
                "Выбери тему, куда отправить сообщение.",
                reply_markup=topic_select_menu(chat_id, topics),
            )
        else:
            await state.set_state(AdminInput.send_message)
            await state.update_data(
                chat_id=chat_id,
                thread_id=None,
                control_chat_id=callback.message.chat.id,
                control_message_id=callback.message.message_id,
            )
            await safe_edit(
                callback,
                f"Группа: <b>{mention_chat(chat)}</b>\n\n"
                "Отправь текст или стикер, который бот должен написать в этот чат.",
                reply_markup=back_to_chat_menu(chat_id),
            )
    elif action == "leave":
        await safe_edit(
            callback,
            f"Бот выйдет из группы: <b>{mention_chat(chat)}</b>\n\n"
            "После выхода он перестанет отвечать и группа пропадет из списка. Подтвердить?",
            reply_markup=leave_confirm_menu(chat_id),
        )

    await callback.answer()


@router.callback_query(F.data.startswith("quotes:"))
async def cb_quotes(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("Неизвестное действие.", show_alert=True)
        return

    action = parts[1]
    chat_id = int(parts[2])
    chat = await require_selected_admin(callback, chat_id)
    if chat is None:
        return
    if not await require_callback_feature(callback, "quotes", default=True):
        return

    if action == "page":
        await state.clear()
        page = int(parts[3]) if len(parts) > 3 else 0
        text, page, total = quote_page_text(chat_id, page)
        await safe_edit(callback, text, reply_markup=quotes_menu(chat_id, page, total))
    elif action == "delete":
        if not is_bot_admin(callback.from_user.id):
            await callback.answer("Удалять цитаты может только администратор бота.", show_alert=True)
            return
        await state.set_state(AdminInput.delete_quote)
        await state.update_data(chat_id=chat_id)
        await safe_edit(
            callback,
            f"Группа: <b>{mention_chat(chat)}</b>\n\n"
            "Отправь номер цитаты из списка для удаления.",
            reply_markup=quotes_menu(chat_id, 0, len(db.list_quotes(chat_id))),
        )
    else:
        await callback.answer("Неизвестное действие.", show_alert=True)
        return

    await callback.answer()


@router.callback_query(F.data.startswith("mod:"))
async def cb_moderator_panel(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_bot_admin(callback.from_user.id):
        await callback.answer("Управление модераторами доступно только владельцу.", show_alert=True)
        return

    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("Неизвестное действие.", show_alert=True)
        return
    action = parts[1]
    chat_id = int(parts[2])
    chat = await require_selected_admin(callback, chat_id)
    if chat is None:
        return

    if action == "role":
        if len(parts) != 4 or parts[3] not in MODERATOR_ROLE_SPECS:
            await callback.answer("Неизвестная роль.", show_alert=True)
            return
        role = parts[3]
        await state.set_state(AdminInput.set_moderator_user)
        await state.update_data(chat_id=chat_id, moderator_role=role)
        await safe_edit(
            callback,
            f"Группа: <b>{mention_chat(chat)}</b>\n\n"
            f"Назначаем: <b>{moderator_role_title(role)}</b>\n"
            "Отправь <code>@username</code> или numeric id пользователя.\n\n"
            "Можно добавить срок: <code>@username неделя</code>, <code>123456 30 дней</code>.",
            reply_markup=moderator_panel_menu(chat_id),
        )
        await callback.answer()
        return

    if action == "demote":
        await state.clear()
        rows = db.list_chat_moderators(chat_id)
        rows.sort(key=lambda row: (-moderator_role_rank(str(row["role"])), str(row["full_name"]).casefold()))
        await safe_edit(
            callback,
            f"Группа: <b>{mention_chat(chat)}</b>\n\nВыбери модератора для расжалования или введи @/id вручную.",
            reply_markup=moderator_demote_menu(chat_id, rows),
        )
        await callback.answer()
        return

    if action == "drop_input":
        await state.set_state(AdminInput.remove_moderator_user)
        await state.update_data(chat_id=chat_id)
        await safe_edit(
            callback,
            f"Группа: <b>{mention_chat(chat)}</b>\n\nОтправь <code>@username</code> или numeric id пользователя для расжалования.",
            reply_markup=moderator_panel_menu(chat_id),
        )
        await callback.answer()
        return

    if action == "drop":
        if len(parts) != 4:
            await callback.answer("Неизвестное действие.", show_alert=True)
            return
        user_id = int(parts[3])
        before = db.get_chat_moderator_role(chat_id, user_id)
        if not before:
            await callback.answer("Пользователь уже не модератор.", show_alert=True)
            return
        db.clear_chat_moderator_role(chat_id, user_id)
        user = db.get_known_user(user_id)
        target_name = f"@{user.username}" if user and user.username else (user.full_name if user else f"ID {user_id}")
        actor = f"@{callback.from_user.username}" if callback.from_user.username else callback.from_user.full_name
        await notify_staff_moderation(
            callback.bot,
            (
                "🛡 <b>Расжалование через панель</b>\n"
                f"Кто: {escape(actor)} [владелец]\n"
                f"С кого: {escape(target_name)}\n"
                f"Группа: {escape(chat.title)}"
            ),
        )
        await safe_edit(callback, moderator_admin_panel_text(chat), reply_markup=moderator_panel_menu(chat_id))
        await callback.answer("Расжалован")
        return

    await callback.answer("Неизвестное действие.", show_alert=True)


@router.callback_query(F.data.startswith("blacklist:"))
async def cb_blacklist(callback: CallbackQuery, state: FSMContext) -> None:
    _, action, chat_id_raw = callback.data.split(":", 2)
    chat_id = int(chat_id_raw)
    chat = await require_selected_admin(callback, chat_id)
    if chat is None:
        return
    if not await require_callback_feature(callback, "blacklist", default=True):
        return

    if action == "add":
        await state.set_state(AdminInput.add_blacklist_word)
        text = "Напиши слово или выражение, которое нужно запретить."
    elif action == "delete":
        await state.set_state(AdminInput.delete_blacklist_word)
        text = "Напиши слово или выражение, которое нужно удалить из черного списка."
    else:
        await callback.answer("Неизвестное действие.", show_alert=True)
        return

    await state.update_data(chat_id=chat_id)
    await safe_edit(
        callback,
        f"Группа: <b>{mention_chat(chat)}</b>\n\n{text}",
        reply_markup=blacklist_menu(chat_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("leave:yes:"))
async def cb_leave_chat(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    chat_id = int(callback.data.split(":", 2)[2])
    chat = await require_selected_admin(callback, chat_id)
    if chat is None:
        return

    try:
        await callback.bot.leave_chat(chat_id)
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        description = str(exc).casefold()
        if "chat not found" in description or "bot is not a member" in description or "forbidden" in description:
            db.delete_chat(chat_id)
            await safe_edit(
                callback,
                f"Группа <b>{mention_chat(chat)}</b> уже недоступна для бота, я убрал ее из списка.",
                reply_markup=admin_back_menu(),
            )
            await callback.answer()
            return

        await safe_edit(
            callback,
            f"Не получилось выйти из группы <b>{mention_chat(chat)}</b>.\n"
            f"<code>{escape(str(exc))}</code>",
            reply_markup=back_to_chat_menu(chat_id),
        )
        await callback.answer()
        return

    db.delete_chat(chat_id)
    await safe_edit(
        callback,
        f"Бот вышел из группы: <b>{mention_chat(chat)}</b>.",
        reply_markup=admin_back_menu(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("access:toggle:"))
async def cb_access_toggle(callback: CallbackQuery) -> None:
    if not is_bot_admin(callback.from_user.id):
        await callback.answer("Доступ может менять только владелец.", show_alert=True)
        return

    parts = callback.data.split(":")
    if len(parts) != 5:
        await callback.answer("Неизвестное действие.", show_alert=True)
        return

    chat_id = int(parts[2])
    user_id = int(parts[3])
    feature = parts[4]
    if feature not in ADMIN_FEATURE_IDS:
        await callback.answer("Неизвестная функция.", show_alert=True)
        return

    allowed = not db.admin_feature_allowed(chat_id, user_id, feature, default=False)
    db.set_admin_feature_permission(chat_id, user_id, feature, allowed, callback.from_user.id)
    await safe_edit(
        callback,
        f"Доступ для <code>{user_id}</code>\n\n"
        "Включенные функции будут доступны в приложении. Для Telegram-админки группы запрет закрывает выбранную функцию.",
        reply_markup=access_permissions_menu(chat_id, user_id),
    )
    await callback.answer("Доступ обновлен")


@router.callback_query(F.data.startswith("access:set:"))
async def cb_access_set(callback: CallbackQuery) -> None:
    if not is_bot_admin(callback.from_user.id):
        await callback.answer("Доступ может менять только владелец.", show_alert=True)
        return
    parts = callback.data.split(":")
    if len(parts) not in {6, 7}:
        await callback.answer("Неизвестное действие.", show_alert=True)
        return
    chat_id = int(parts[2])
    user_id = int(parts[3])
    feature = parts[4]
    mode = parts[5]
    page = int(parts[6]) if len(parts) == 7 else 0
    if feature not in ADMIN_PERMISSION_IDS or mode not in {"view", "write"}:
        await callback.answer("Неизвестное право.", show_alert=True)
        return
    key = admin_permission_key(feature, mode)
    allowed = not bot_admin_feature_allowed(chat_id, user_id, feature, mode=mode, default=False)
    db.set_admin_feature_permission(chat_id, user_id, key, allowed, callback.from_user.id)
    if "." not in feature:
        db.set_admin_feature_permission(chat_id, user_id, feature, False, callback.from_user.id)
    await safe_edit(
        callback,
        f"Доступ для <code>{user_id}</code>\n\n"
        "Читать = может открыть кнопку. Менять = может нажимать действия внутри нее.",
        reply_markup=access_permissions_menu(chat_id, user_id, page),
    )
    await callback.answer("Доступ обновлен")


@router.callback_query(F.data.startswith("access:page:"))
async def cb_access_page(callback: CallbackQuery) -> None:
    if not is_bot_admin(callback.from_user.id):
        await callback.answer("Доступ может менять только владелец.", show_alert=True)
        return
    parts = callback.data.split(":")
    if len(parts) != 5:
        await callback.answer("Неизвестное действие.", show_alert=True)
        return
    chat_id = int(parts[2])
    user_id = int(parts[3])
    page = int(parts[4])
    await safe_edit(
        callback,
        f"Доступ для <code>{user_id}</code>\n\n"
        "Читать = может открыть кнопку. Менять = может нажимать действия внутри нее.",
        reply_markup=access_permissions_menu(chat_id, user_id, page),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("access:user:"))
async def cb_access_user(callback: CallbackQuery) -> None:
    if not is_bot_admin(callback.from_user.id):
        await callback.answer("Доступ может менять только владелец.", show_alert=True)
        return
    _, _, chat_id_raw, user_id_raw = callback.data.split(":", 3)
    chat_id = int(chat_id_raw)
    user_id = int(user_id_raw)
    await safe_edit(
        callback,
        f"Доступ для <code>{user_id}</code>\n\n"
        "Читать = может открыть кнопку. Менять = может нажимать действия внутри нее.",
        reply_markup=access_permissions_menu(chat_id, user_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("access:noop:"))
async def cb_access_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data.startswith("giveaway:"))
async def cb_giveaway_menu(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    action = parts[1]
    chat_id = int(parts[2])
    chat = await require_selected_admin(callback, chat_id)
    if chat is None:
        return
    if not await require_callback_feature(callback, "giveaway", mode="view", default=True):
        return

    if action == "settings":
        if not await require_callback_feature(callback, "giveaway.settings", default=True):
            return
        settings = db.get_giveaway_settings(chat_id)
        await state.set_state(AdminInput.set_giveaway)
        await state.update_data(chat_id=chat_id)
        await safe_edit(
            callback,
            f"Группа: <b>{mention_chat(chat)}</b>\n\n"
            "Отправь настройку розыгрыша в формате:\n"
            "<code>фраза вызова - количество - заголовок</code>\n\n"
            "Пример:\n"
            "<code>кто пидор - 3 - Пидоры дня</code>\n\n"
            f"Сейчас: <code>{escape(settings.trigger)} - {settings.winners_count} - {escape(settings.title)}</code>",
            reply_markup=giveaway_menu(chat_id),
        )
    elif action == "birthdays":
        if not await require_callback_feature(callback, "giveaway.birthdays", mode="view", default=True):
            return
        birthdays = db.list_birthdays(chat_id)
        lines = [f"Группа: <b>{mention_chat(chat)}</b>", "", "<b>Дни рождения:</b>"]
        if birthdays:
            lines.extend(f"{item.id}. {item.day:02d}.{item.month:02d} — {escape(item.text)}" for item in birthdays[:50])
        else:
            lines.append("Пока пусто.")
        await safe_edit(callback, "\n".join(lines), reply_markup=birthday_menu(chat_id, birthdays))
    elif action == "add_birthday":
        if not await require_callback_feature(callback, "giveaway.birthdays", default=True):
            return
        await state.set_state(AdminInput.add_birthday)
        await state.update_data(chat_id=chat_id)
        await safe_edit(
            callback,
            f"Группа: <b>{mention_chat(chat)}</b>\n\n"
            "Отправь день рождения в формате:\n"
            "<code>31.12 Имя или событие</code>",
            reply_markup=giveaway_menu(chat_id),
        )
    elif action == "delete_birthday":
        if not await require_callback_feature(callback, "giveaway.birthdays", default=True):
            return
        birthday_id = int(parts[3])
        deleted = db.delete_birthday(chat_id, birthday_id)
        birthdays = db.list_birthdays(chat_id)
        await safe_edit(
            callback,
            "День рождения удален." if deleted else "День рождения не найден.",
            reply_markup=birthday_menu(chat_id, birthdays),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("alarm:"))
async def cb_alarm(callback: CallbackQuery, state: FSMContext) -> None:
    _, action, chat_id_raw = callback.data.split(":", 2)
    chat_id = int(chat_id_raw)
    chat = await require_selected_admin(callback, chat_id)
    if chat is None:
        return
    if not await require_callback_feature(callback, "alarm", mode="view", default=True):
        return

    settings = db.get_alarm_settings(chat_id)
    if action == "toggle":
        if not await require_callback_feature(callback, "alarm.toggle", default=True):
            return
        enabled = not bool(settings.enabled)
        db.set_alarm_enabled(chat_id, enabled, callback.from_user.id)
        invalidate_chat_runtime_cache(chat_id)
        settings = db.get_alarm_settings(chat_id)
        await safe_edit(
            callback,
            f"Группа: <b>{mention_chat(chat)}</b>\n\n"
            f"Режим тревоги: <b>{'включен' if settings.enabled else 'выключен'}</b>\n\n"
            f"Автотревога Alerts.in.ua ({ALERTS_LOCATION_TITLE}): <b>{'включена' if db.alarm_api_enabled(chat_id) else 'выключена'}</b>\n\n"
            f"Ограничения медиа и реакций: <b>{'включены' if db.alarm_restrictions_enabled(chat_id) else 'выключены'}</b>\n\n"
            f"Текст тревоги: {preview_html(settings.alarm_text or 'Тревога включена: медиа, реакции и одиночные эмодзи отключены.')}\n"
            f"Текст отбоя: {preview_html(settings.clear_text or 'Отбой: медиа, реакции и одиночные эмодзи снова включены.')}",
            reply_markup=alarm_menu(
                chat_id,
                bool(settings.enabled),
                db.alarm_api_enabled(chat_id),
                db.alarm_restrictions_enabled(chat_id),
            ),
        )
    elif action == "api":
        if not await require_callback_feature(callback, "alarm.api", default=True):
            return
        if not ALERTS_API_TOKEN:
            await callback.answer("Добавь ALERTS_API_TOKEN в файл .env и перезапусти бота.", show_alert=True)
            return
        enabled = not db.alarm_api_enabled(chat_id)
        previous_status = db.alarm_api_last_status(chat_id)
        if not enabled and previous_status in {"A", "P"}:
            await deactivate_alarm_from_api(callback.bot, chat_id)
        db.set_alarm_api_enabled(chat_id, enabled, callback.from_user.id)
        invalidate_chat_runtime_cache(chat_id)
        settings = db.get_alarm_settings(chat_id)
        await safe_edit(
            callback,
            f"Группа: <b>{mention_chat(chat)}</b>\n\n"
            f"Режим тревоги: <b>{'включен' if settings.enabled else 'выключен'}</b>\n\n"
            f"Автотревога Alerts.in.ua ({ALERTS_LOCATION_TITLE}): <b>{'включена' if enabled else 'выключена'}</b>\n\n"
            f"Ограничения медиа и реакций: <b>{'включены' if db.alarm_restrictions_enabled(chat_id) else 'выключены'}</b>\n\n"
            f"Текст тревоги: {preview_html(settings.alarm_text or 'Тревога включена: медиа, реакции и одиночные эмодзи отключены.')}\n"
            f"Текст отбоя: {preview_html(settings.clear_text or 'Отбой: медиа, реакции и одиночные эмодзи снова включены.')}",
            reply_markup=alarm_menu(
                chat_id,
                bool(settings.enabled),
                enabled,
                db.alarm_restrictions_enabled(chat_id),
            ),
        )
    elif action == "restrictions":
        if not await require_callback_feature(callback, "alarm.restrictions", default=True):
            return
        enabled = not db.alarm_restrictions_enabled(chat_id)
        if not enabled:
            await restore_alarm_restrictions(callback.bot, chat_id)
        db.set_alarm_restrictions_enabled(chat_id, enabled, callback.from_user.id)
        invalidate_chat_runtime_cache(chat_id)
        if enabled and db.alarm_api_last_status(chat_id) in {"A", "P"}:
            await apply_alarm_restrictions(callback.bot, chat_id)
        settings = db.get_alarm_settings(chat_id)
        await safe_edit(
            callback,
            f"Группа: <b>{mention_chat(chat)}</b>\n\n"
            f"Режим тревоги: <b>{'включен' if settings.enabled else 'выключен'}</b>\n\n"
            f"Автотревога Alerts.in.ua ({ALERTS_LOCATION_TITLE}): <b>{'включена' if db.alarm_api_enabled(chat_id) else 'выключена'}</b>\n\n"
            f"Ограничения медиа и реакций: <b>{'включены' if enabled else 'выключены'}</b>\n\n"
            f"Текст тревоги: {preview_html(settings.alarm_text or 'Тревога включена: медиа, реакции и одиночные эмодзи отключены.')}\n"
            f"Текст отбоя: {preview_html(settings.clear_text or 'Отбой: медиа, реакции и одиночные эмодзи снова включены.')}",
            reply_markup=alarm_menu(chat_id, bool(settings.enabled), db.alarm_api_enabled(chat_id), enabled),
        )
    elif action == "text_on":
        if not await require_callback_feature(callback, "alarm.text", default=True):
            return
        await state.set_state(AdminInput.set_alarm_text)
        await state.update_data(chat_id=chat_id)
        await safe_edit(
            callback,
            f"Группа: <b>{mention_chat(chat)}</b>\n\n"
            "Отправь текст оповещения для слова <code>тревога</code>.",
            reply_markup=back_to_chat_menu(chat_id),
        )
    elif action == "text_off":
        if not await require_callback_feature(callback, "alarm.text", default=True):
            return
        await state.set_state(AdminInput.set_clear_text)
        await state.update_data(chat_id=chat_id)
        await safe_edit(
            callback,
            f"Группа: <b>{mention_chat(chat)}</b>\n\n"
            "Отправь текст оповещения для слова <code>отбой</code>.",
            reply_markup=back_to_chat_menu(chat_id),
        )

    await callback.answer()


@router.callback_query(F.data.startswith("quiet:"))
async def cb_quiet(callback: CallbackQuery, state: FSMContext) -> None:
    _, action, chat_id_raw = callback.data.split(":", 2)
    chat_id = int(chat_id_raw)
    chat = await require_selected_admin(callback, chat_id)
    if chat is None:
        return
    if not await require_callback_feature(callback, "quiet", mode="view", default=True):
        return

    if action == "text":
        if not await require_callback_feature(callback, "quiet.text", default=True):
            return
        await state.set_state(AdminInput.set_quiet_text)
        await state.update_data(chat_id=chat_id)
        await safe_edit(
            callback,
            f"Группа: <b>{mention_chat(chat)}</b>\n\n"
            "Отправь текст, который бот напишет после команды затихни.\n\n"
            "Можно использовать:\n"
            "<code>{user}</code> - пользователь\n"
            "<code>{minutes}</code> - минуты\n"
            "<code>{reason}</code> - причина без новой строки\n"
            "<code>{reason_line}</code> - строка с причиной, если она есть\n\n"
            "Пример:\n"
            "<code>{user} затих на {minutes} мин.{reason_line}</code>",
            reply_markup=back_to_chat_menu(chat_id),
        )
    elif action == "media":
        if not await require_callback_feature(callback, "quiet.mediaSave", default=True):
            return
        if False:
            await callback.answer("Медиа может менять только администратор бота.", show_alert=True)
            return

        await state.set_state(AdminInput.set_quiet_media)
        await state.update_data(chat_id=chat_id)
        await safe_edit(
            callback,
            f"Группа: <b>{mention_chat(chat)}</b>\n\n"
            "Отправь сюда гиф, голосовое или аудио. Бот сохранит его и будет отправлять после команды затихни.",
            reply_markup=back_to_chat_menu(chat_id),
        )
    elif action == "manual":
        if not await require_callback_feature(callback, "quiet.manual", default=True):
            return
        await state.set_state(AdminInput.set_quiet_manual)
        await state.update_data(chat_id=chat_id)
        await safe_edit(
            callback,
            f"Группа: <b>{mention_chat(chat)}</b>\n\n"
            "Кого замутить через бота?\n\n"
            "Формат:\n"
            "<code>@username 10 - причина</code>\n"
            "или\n"
            "<code>123456789 10 - причина</code>\n\n"
            "Причина необязательна. Число - минуты.",
            reply_markup=back_to_chat_menu(chat_id),
        )
    elif action == "clear_media":
        if not await require_callback_feature(callback, "quiet.mediaDelete", default=True):
            return
        if False:
            await callback.answer("Медиа может менять только администратор бота.", show_alert=True)
            return

        db.clear_quiet_media(chat_id, callback.from_user.id)
        settings = db.get_quiet_settings(chat_id)
        await safe_edit(
            callback,
            "Медиа для команды затихни удалено.",
            reply_markup=quiet_menu(chat_id, bool(settings.media_file_id)),
        )

    await callback.answer()


@router.callback_query(F.data.startswith("topic:"))
async def cb_select_topic(callback: CallbackQuery, state: FSMContext) -> None:
    _, chat_id_raw, thread_id_raw = callback.data.split(":", 2)
    chat_id = int(chat_id_raw)
    thread_id = int(thread_id_raw)
    chat = await require_selected_admin(callback, chat_id)
    if chat is None:
        return

    await state.set_state(AdminInput.send_message)
    await state.update_data(
        chat_id=chat_id,
        thread_id=thread_id or None,
        control_chat_id=callback.message.chat.id,
        control_message_id=callback.message.message_id,
    )
    topic = next((item for item in db.list_topics(chat_id) if item.thread_id == thread_id), None)
    target = "основной чат" if thread_id == 0 else (topic.title if topic else "выбранную тему")
    await safe_edit(
        callback,
        f"Группа: <b>{mention_chat(chat)}</b>\n"
        f"Цель: <b>{escape(target)}</b>\n\n"
        "Отправь текст или стикер, который бот должен написать.",
        reply_markup=back_to_chat_menu(chat_id),
    )
    await callback.answer()


@router.message(AdminInput.set_access_user, F.chat.type == "private")
async def ui_set_access_user(message: Message, state: FSMContext) -> None:
    if not message.from_user or not is_bot_admin(message.from_user.id):
        await state.clear()
        await message.answer("Доступ может менять только владелец.")
        return

    data = await state.get_data()
    chat_id = data.get("chat_id")
    if not isinstance(chat_id, int):
        await state.clear()
        await message.answer("Группа не выбрана. Открой /start и выбери группу.", reply_markup=main_menu())
        return

    text = (message.text or "").strip()
    if not text.lstrip("-").isdigit():
        await message.answer("Отправь Telegram ID числом.")
        return

    user_id = int(text)
    await state.clear()
    await message.answer(
        f"Доступ для <code>{user_id}</code>\n\n"
        "Включи функции, которые можно использовать в приложении. Выключенная функция будет закрыта и в Telegram-админке.",
        reply_markup=access_permissions_menu(chat_id, user_id),
    )


@router.message(AdminInput.set_moderator_user, F.chat.type == "private")
async def ui_set_moderator_user(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    chat_id = data.get("chat_id")
    role = data.get("moderator_role")
    if not isinstance(chat_id, int) or role not in MODERATOR_ROLE_SPECS:
        await state.clear()
        await message.answer("Настройка модератора потерялась. Открой панель заново.", reply_markup=main_menu())
        return
    if not message.from_user or not is_bot_admin(message.from_user.id):
        await state.clear()
        await message.answer("Управление модераторами доступно только владельцу.", reply_markup=main_menu())
        return

    chat = db.get_chat(chat_id)
    if chat is None:
        await state.clear()
        await message.answer("Группа не найдена.", reply_markup=main_menu())
        return

    raw = (message.text or "").strip()
    if not raw:
        await message.answer("Отправь <code>@username</code> или numeric id пользователя.")
        return
    target_token, _, tail = raw.partition(" ")
    target_id, target_name, error = await resolve_quiet_panel_target(message.bot, chat_id, target_token)
    if error:
        await message.answer(error, reply_markup=moderator_panel_menu(chat_id))
        return
    if not target_id or not target_name:
        await message.answer("Не получилось определить пользователя.", reply_markup=moderator_panel_menu(chat_id))
        return
    _unused, expires_at = parse_moderator_duration(tail)

    db.set_chat_moderator_role(chat_id, target_id, str(role), message.from_user.id, expires_at)
    await state.clear()
    until_line = f"\nСрок: до <b>{escape(expires_at)}</b>" if expires_at else "\nСрок: бессрочно"
    await message.answer(
        f"{escape(target_name)} назначен: <b>{moderator_role_title(str(role))}</b>.{until_line}\n\n"
        f"{moderator_admin_panel_text(chat)}",
        reply_markup=moderator_panel_menu(chat_id),
    )
    actor = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
    await notify_staff_moderation(
        message.bot,
        (
            "🛡 <b>Назначение модератора через панель</b>\n"
            f"Кто: {escape(actor)} [владелец]\n"
            f"Кому: {escape(target_name)}\n"
            f"Должность: <b>{moderator_role_title(str(role))}</b>{until_line}\n"
            f"Группа: {escape(chat.title)}"
        ),
    )


@router.message(AdminInput.remove_moderator_user, F.chat.type == "private")
async def ui_remove_moderator_user(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    chat_id = data.get("chat_id")
    if not isinstance(chat_id, int):
        await state.clear()
        await message.answer("Настройка модератора потерялась. Открой панель заново.", reply_markup=main_menu())
        return
    if not message.from_user or not is_bot_admin(message.from_user.id):
        await state.clear()
        await message.answer("Управление модераторами доступно только владельцу.", reply_markup=main_menu())
        return

    chat = db.get_chat(chat_id)
    if chat is None:
        await state.clear()
        await message.answer("Группа не найдена.", reply_markup=main_menu())
        return
    target_token = (message.text or "").strip().split(maxsplit=1)[0] if (message.text or "").strip() else ""
    if not target_token:
        await message.answer("Отправь <code>@username</code> или numeric id пользователя.")
        return
    target_id, target_name, error = await resolve_quiet_panel_target(message.bot, chat_id, target_token)
    if error:
        await message.answer(error, reply_markup=moderator_panel_menu(chat_id))
        return
    if not target_id or not target_name:
        await message.answer("Не получилось определить пользователя.", reply_markup=moderator_panel_menu(chat_id))
        return
    if not db.clear_chat_moderator_role(chat_id, target_id):
        await message.answer(f"{escape(target_name)} не числится в модераторах.", reply_markup=moderator_panel_menu(chat_id))
        return

    await state.clear()
    await message.answer(
        f"С {escape(target_name)} снята модераторская должность.\n\n{moderator_admin_panel_text(chat)}",
        reply_markup=moderator_panel_menu(chat_id),
    )
    actor = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
    await notify_staff_moderation(
        message.bot,
        (
            "🛡 <b>Расжалование через панель</b>\n"
            f"Кто: {escape(actor)} [владелец]\n"
            f"С кого: {escape(target_name)}\n"
            f"Группа: {escape(chat.title)}"
        ),
    )


@router.message(AdminInput.set_reply, F.chat.type == "private")
async def ui_set_reply(message: Message, state: FSMContext) -> None:
    chat_id = await require_state_admin(message, state)
    if chat_id is None:
        return

    payload = message_html_content(message)
    media = reply_media_from_message(message)
    username, reply_text = split_reply_payload(payload)
    if not username.startswith("@"):
        await message.answer("Формат: <code>@username - текст ответа</code> или сообщение с таким caption и медиа.")
        return
    if not reply_text and not media:
        await state.set_state(AdminInput.set_reply_media)
        await state.update_data(chat_id=chat_id, reply_username=username)
        await message.answer(
            f"Ок, теперь отправь медиа для автоответа <b>@{escape(normalize_username(username))}</b>: "
            "гиф, голос, аудио, видео, кружок или аудио/видео-файл.",
            reply_markup=back_to_chat_menu(chat_id),
        )
        return

    media_type, media_file_id = media if media else (None, None)
    db.set_reply(chat_id, username, reply_text, message.from_user.id if message.from_user else None, media_type, media_file_id)
    invalidate_chat_runtime_cache(chat_id)
    await notify_staff_autoreply_change(message.bot, f"@ответ @{normalize_username(username)} изменён для чата {chat_id}.")
    await state.clear()
    await message.answer(
        f"Готово. Автоответ для <b>@{escape(normalize_username(username))}</b> сохранен.",
        reply_markup=back_to_chat_menu(chat_id),
    )


@router.message(AdminInput.set_reply_media, F.chat.type == "private")
async def ui_set_reply_media(message: Message, state: FSMContext) -> None:
    chat_id = await require_state_admin(message, state)
    if chat_id is None:
        return

    data = await state.get_data()
    username = data.get("reply_username")
    if not isinstance(username, str) or not username.startswith("@"):
        await state.clear()
        await message.answer("Не вижу, для какого @username сохранить медиа. Открой настройку заново.", reply_markup=main_menu())
        return

    media = reply_media_from_message(message)
    if not media:
        await message.answer("Нужно отправить гиф, голос, аудио, видео, кружок или аудио/видео-файл.")
        return

    reply_text = message_html_content(message)
    media_type, media_file_id = media
    db.set_reply(chat_id, username, reply_text, message.from_user.id if message.from_user else None, media_type, media_file_id)
    invalidate_chat_runtime_cache(chat_id)
    await notify_staff_autoreply_change(message.bot, f"Медиа-@ответ @{normalize_username(username)} изменён для чата {chat_id}.")
    await state.clear()
    await message.answer(
        f"Готово. Медиа-автоответ для <b>@{escape(normalize_username(username))}</b> сохранен.",
        reply_markup=back_to_chat_menu(chat_id),
    )


@router.message(AdminInput.del_reply, F.chat.type == "private")
async def ui_del_reply(message: Message, state: FSMContext) -> None:
    chat_id = await require_state_admin(message, state)
    if chat_id is None:
        return

    username = (message.text or "").strip()
    if not username.startswith("@"):
        await message.answer("Формат: <code>@username</code>")
        return

    deleted = db.delete_reply(chat_id, username)
    invalidate_chat_runtime_cache(chat_id)
    if deleted:
        await notify_staff_autoreply_change(message.bot, f"@ответ @{normalize_username(username)} удалён из чата {chat_id}.")
    await state.clear()
    await message.answer(
        "Автоответ удален." if deleted else "Для этого username автоответ не найден.",
        reply_markup=back_to_chat_menu(chat_id),
    )


@router.message(AdminInput.set_trigger, F.chat.type == "private")
async def ui_set_trigger(message: Message, state: FSMContext) -> None:
    chat_id = await require_state_admin(message, state)
    if chat_id is None:
        return

    payload = message_html_content(message)
    media = reply_media_from_message(message)
    trigger, reply_text = split_trigger_payload(payload)
    if not trigger:
        await message.answer("Формат: <code>слово - текст ответа</code> или сообщение с таким caption и медиа.")
        return
    if not reply_text and not media:
        await state.set_state(AdminInput.set_trigger_media)
        await state.update_data(chat_id=chat_id, trigger=trigger)
        await message.answer(
            f"Ок, теперь отправь медиа для триггера <b>{escape(normalize_trigger(trigger))}</b>: "
            "гиф, голос, аудио, видео, кружок или аудио/видео-файл.",
            reply_markup=back_to_chat_menu(chat_id),
        )
        return

    media_type, media_file_id = media if media else (None, None)
    db.set_trigger(chat_id, trigger, reply_text, message.from_user.id if message.from_user else None, media_type, media_file_id)
    invalidate_chat_runtime_cache(chat_id)
    await notify_staff_autoreply_change(message.bot, f"Триггер «{normalize_trigger(trigger)}» изменён для чата {chat_id}.")
    await state.clear()
    await message.answer(
        f"Фиксированный ответ на <b>{escape(normalize_trigger(trigger))}</b> сохранен.",
        reply_markup=back_to_chat_menu(chat_id),
    )


@router.message(AdminInput.set_trigger_media, F.chat.type == "private")
async def ui_set_trigger_media(message: Message, state: FSMContext) -> None:
    chat_id = await require_state_admin(message, state)
    if chat_id is None:
        return

    data = await state.get_data()
    trigger = data.get("trigger")
    if not isinstance(trigger, str) or not trigger.strip():
        await state.clear()
        await message.answer("Не вижу, для какого триггера сохранить медиа. Открой настройку заново.", reply_markup=main_menu())
        return

    media = reply_media_from_message(message)
    if not media:
        await message.answer("Нужно отправить гиф, голос, аудио, видео, кружок или аудио/видео-файл.")
        return

    reply_text = message_html_content(message)
    media_type, media_file_id = media
    db.set_trigger(chat_id, trigger, reply_text, message.from_user.id if message.from_user else None, media_type, media_file_id)
    invalidate_chat_runtime_cache(chat_id)
    await notify_staff_autoreply_change(message.bot, f"Медиа-триггер «{normalize_trigger(trigger)}» изменён для чата {chat_id}.")
    await state.clear()
    await message.answer(
        f"Фиксированный медиа-ответ на <b>{escape(normalize_trigger(trigger))}</b> сохранен.",
        reply_markup=back_to_chat_menu(chat_id),
    )


@router.message(AdminInput.del_trigger, F.chat.type == "private")
async def ui_del_trigger(message: Message, state: FSMContext) -> None:
    chat_id = await require_state_admin(message, state)
    if chat_id is None:
        return

    number_text = (message.text or "").strip()
    if not number_text.isdigit():
        await message.answer("Отправь номер слова из списка, например: <code>3</code>")
        return

    index = int(number_text)
    triggers = db.list_triggers(chat_id)
    if index < 1 or index > len(triggers):
        await message.answer(f"Нет слова с номером {index}. Открой список и выбери номер из него.")
        return

    trigger = triggers[index - 1].trigger
    deleted = db.delete_trigger(chat_id, trigger)
    invalidate_chat_runtime_cache(chat_id)
    if deleted:
        await notify_staff_autoreply_change(message.bot, f"Триггер «{normalize_trigger(trigger)}» удалён из чата {chat_id}.")
    await state.clear()
    text, page, total = trigger_page_text(chat_id, (index - 1) // TRIGGERS_PAGE_SIZE)
    result = f"Удалено слово №{index}: <b>{escape(trigger)}</b>" if deleted else "Такой фиксированный ответ не найден."
    await message.answer(f"{result}\n\n{text}", reply_markup=trigger_list_menu(chat_id, page, total))


@router.message(AdminInput.add_blacklist_word, F.chat.type == "private")
async def ui_add_blacklist_word(message: Message, state: FSMContext) -> None:
    chat_id = await require_state_admin(message, state)
    if chat_id is None:
        return

    word = normalize_trigger(message.text or "")
    if not word:
        await message.answer("Напиши слово или выражение, которое нужно запретить.")
        return

    db.add_blacklist_word(chat_id, word, message.from_user.id if message.from_user else None)
    invalidate_chat_runtime_cache(chat_id)
    await state.clear()
    await message.answer(
        f"Добавлено в черный список: <b>{escape(word)}</b>\n\n{blacklist_text(chat_id)}",
        reply_markup=blacklist_menu(chat_id),
    )


@router.message(AdminInput.delete_blacklist_word, F.chat.type == "private")
async def ui_delete_blacklist_word(message: Message, state: FSMContext) -> None:
    chat_id = await require_state_admin(message, state)
    if chat_id is None:
        return

    word = normalize_trigger(message.text or "")
    if not word:
        await message.answer("Напиши слово или выражение, которое нужно удалить.")
        return

    deleted = db.delete_blacklist_word(chat_id, word)
    invalidate_chat_runtime_cache(chat_id)
    await state.clear()
    result = f"Удалено из черного списка: <b>{escape(word)}</b>" if deleted else "Такого слова или выражения в черном списке нет."
    await message.answer(
        f"{result}\n\n{blacklist_text(chat_id)}",
        reply_markup=blacklist_menu(chat_id),
    )


@router.message(AdminInput.delete_quote, F.chat.type == "private")
async def ui_delete_quote(message: Message, state: FSMContext) -> None:
    chat_id = await require_state_admin(message, state)
    if chat_id is None:
        return
    if not message.from_user or not is_bot_admin(message.from_user.id):
        await state.clear()
        await message.answer("Удалять цитаты может только администратор бота.", reply_markup=back_to_chat_menu(chat_id))
        return

    number_text = (message.text or "").strip()
    if not number_text.isdigit():
        await message.answer("Отправь номер цитаты из списка, например: <code>3</code>")
        return

    index = int(number_text)
    quotes = db.list_quotes(chat_id)
    if index < 1 or index > len(quotes):
        await message.answer(f"Нет цитаты с номером {index}. Открой список и выбери номер из него.")
        return

    quote = quotes[index - 1]
    deleted = db.delete_quote(chat_id, quote.id)
    await state.clear()
    text, page, total = quote_page_text(chat_id, (index - 1) // QUOTES_PAGE_SIZE)
    result = f"Удалена цитата №{index}." if deleted else "Цитата уже удалена."
    await message.answer(f"{result}\n\n{text}", reply_markup=quotes_menu(chat_id, page, total))


@router.message(AdminInput.send_message, F.chat.type == "private")
async def ui_send_message(message: Message, state: FSMContext) -> None:
    chat_id = await require_state_admin(message, state)
    if chat_id is None:
        return
    data = await state.get_data()
    thread_id = data.get("thread_id")

    text = (message.text or message.caption or "").strip()
    sticker = message.sticker
    if not text and not sticker:
        await message.answer("Отправь текст или стикер, который нужно написать в выбранный чат.")
        return

    try:
        if sticker:
            kwargs = {"chat_id": chat_id, "sticker": sticker.file_id}
            if isinstance(thread_id, int):
                kwargs["message_thread_id"] = thread_id
            await message.bot.send_sticker(**kwargs)
        else:
            kwargs = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
            if isinstance(thread_id, int):
                kwargs["message_thread_id"] = thread_id
            await message.bot.send_message(**kwargs)
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        await state.clear()
        hint = ""
        if "TOPIC_CLOSED" in str(exc):
            hint = "\n\nЭта тема закрыта. Выбери другую открытую тему или открой тему в Telegram."
        await message.answer(
            f"Не получилось отправить сообщение: <code>{escape(str(exc))}</code>{hint}",
            reply_markup=back_to_chat_menu(chat_id),
        )
        return

    await clear_previous_control_buttons(message, state)
    control_message = await message.answer(
        "Отправлено. Можно отправить следующий текст или стикер в этот же чат.",
        reply_markup=back_to_chat_menu(chat_id),
    )
    await state.update_data(
        control_chat_id=control_message.chat.id,
        control_message_id=control_message.message_id,
    )


@router.message(AdminInput.set_giveaway, F.chat.type == "private")
async def ui_set_giveaway(message: Message, state: FSMContext) -> None:
    chat_id = await require_state_admin(message, state)
    if chat_id is None:
        return

    trigger, count, title = split_giveaway_payload((message.text or "").strip())
    if not trigger or not count or not title:
        await message.answer(
            "Формат: <code>фраза вызова - количество - заголовок</code>\n"
            "Пример: <code>кто пидор - 3 - Пидоры дня</code>"
        )
        return

    db.set_giveaway_settings(
        chat_id=chat_id,
        trigger=trigger,
        title=title,
        winners_count=count,
        updated_by=message.from_user.id if message.from_user else None,
    )
    await state.clear()
    await message.answer(
        "Настройка розыгрыша сохранена:\n"
        f"Фраза: <b>{escape(normalize_trigger(trigger))}</b>\n"
        f"Количество: <b>{count}</b>\n"
        f"Заголовок: <b>{escape(title)}</b>",
        reply_markup=back_to_chat_menu(chat_id),
    )


@router.message(AdminInput.add_birthday, F.chat.type == "private")
async def ui_add_birthday(message: Message, state: FSMContext) -> None:
    chat_id = await require_state_admin(message, state)
    if chat_id is None:
        return
    if not message.from_user or not bot_admin_feature_allowed(chat_id, message.from_user.id, "giveaway.birthdays", default=True):
        await state.clear()
        await message.answer("Нет доступа к дням рождения.", reply_markup=giveaway_menu(chat_id))
        return
    parsed = parse_birthday_payload(message.text or "")
    if not parsed:
        await message.answer("Формат: <code>31.12 Имя или событие</code>", reply_markup=giveaway_menu(chat_id))
        return
    day, month, label = parsed
    db.add_birthday(chat_id, day, month, label, message.from_user.id)
    await state.clear()
    await message.answer(f"Дата добавлена: <b>{day:02d}.{month:02d}</b> — {escape(label)}", reply_markup=giveaway_menu(chat_id))


@router.message(AdminInput.set_alarm_text, F.chat.type == "private")
async def ui_set_alarm_text(message: Message, state: FSMContext) -> None:
    chat_id = await require_state_admin(message, state)
    if chat_id is None:
        return

    text = message_html_text(message)
    if not text:
        await message.answer("Отправь текст оповещения для тревоги.")
        return

    db.set_alarm_texts(chat_id, alarm_text=text, updated_by=message.from_user.id if message.from_user else None)
    await state.clear()
    settings = db.get_alarm_settings(chat_id)
    await message.answer(
        "Текст тревоги сохранен.",
        reply_markup=alarm_menu(
            chat_id,
            bool(settings.enabled),
            db.alarm_api_enabled(chat_id),
            db.alarm_restrictions_enabled(chat_id),
        ),
    )


@router.message(AdminInput.set_clear_text, F.chat.type == "private")
async def ui_set_clear_text(message: Message, state: FSMContext) -> None:
    chat_id = await require_state_admin(message, state)
    if chat_id is None:
        return

    text = message_html_text(message)
    if not text:
        await message.answer("Отправь текст оповещения для отбоя.")
        return

    db.set_alarm_texts(chat_id, clear_text=text, updated_by=message.from_user.id if message.from_user else None)
    await state.clear()
    settings = db.get_alarm_settings(chat_id)
    await message.answer(
        "Текст отбоя сохранен.",
        reply_markup=alarm_menu(
            chat_id,
            bool(settings.enabled),
            db.alarm_api_enabled(chat_id),
            db.alarm_restrictions_enabled(chat_id),
        ),
    )


@router.message(AdminInput.set_quiet_text, F.chat.type == "private")
async def ui_set_quiet_text(message: Message, state: FSMContext) -> None:
    chat_id = await require_state_admin(message, state)
    if chat_id is None:
        return

    text = message_html_text(message)
    if not text:
        await message.answer("Отправь текст ответа для команды затихни.")
        return

    db.set_quiet_text(chat_id, text, message.from_user.id if message.from_user else None)
    await state.clear()
    settings = db.get_quiet_settings(chat_id)
    await message.answer(
        "Текст для команды затихни сохранен.",
        reply_markup=quiet_menu(chat_id, bool(settings.media_file_id)),
    )


@router.message(AdminInput.set_quiet_media, F.chat.type == "private")
async def ui_set_quiet_media(message: Message, state: FSMContext) -> None:
    chat_id = await require_state_admin(message, state)
    if chat_id is None:
        return
    if not message.from_user or not is_bot_admin(message.from_user.id):
        await state.clear()
        await message.answer("Медиа может менять только администратор бота.", reply_markup=main_menu())
        return

    media = quiet_media_from_message(message)
    if not media:
        await message.answer("Нужно отправить гиф, голосовое или аудио.")
        return

    media_type, file_id = media
    db.set_quiet_media(chat_id, media_type, file_id, message.from_user.id if message.from_user else None)
    await state.clear()
    await message.answer(
        f"Медиа для команды затихни сохранено: <code>{escape(media_type)}</code>.",
        reply_markup=quiet_menu(chat_id, True),
    )


@router.message(AdminInput.set_quiet_manual, F.chat.type == "private")
async def ui_set_quiet_manual(message: Message, state: FSMContext) -> None:
    chat_id = await require_state_admin(message, state)
    if chat_id is None:
        return

    target, minutes, reason = parse_quiet_manual_payload(message.text)
    if not target or not minutes:
        await message.answer(
            "Формат: <code>@username 10 - причина</code> или <code>123456789 10 - причина</code>."
        )
        return

    target_id, target_name, error = await resolve_quiet_panel_target(message.bot, chat_id, target)
    if error:
        await message.answer(error)
        return
    if not target_id or not target_name:
        return
    if await is_chat_admin(message.bot, chat_id, target_id):
        await message.answer("Администратора этой командой ограничивать нельзя.")
        return

    minutes = max(1, min(10080, minutes))
    until_date = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    try:
        await message.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=target_id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_audios=False,
                can_send_documents=False,
                can_send_photos=False,
                can_send_videos=False,
                can_send_video_notes=False,
                can_send_voice_notes=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
                can_react_to_messages=False,
            ),
            until_date=until_date,
            use_independent_chat_permissions=True,
        )
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        await message.answer(
            "Не получилось ограничить пользователя. Проверь, что бот админ и может ограничивать участников.\n"
            f"<code>{escape(str(exc))}</code>",
            reply_markup=quiet_menu(chat_id, bool(db.get_quiet_settings(chat_id).media_file_id)),
        )
        return

    settings = db.get_quiet_settings(chat_id)
    text = render_quiet_reply(settings.reply_text, target_name, minutes, reason)
    try:
        sent = await message.bot.send_message(chat_id, text, disable_web_page_preview=True)
        await send_quiet_media_to_chat(
            message.bot,
            chat_id,
            settings.media_type,
            settings.media_file_id,
            reply_to_message_id=sent.message_id,
        )
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        await message.answer(
            "Мут поставлен, но сообщение в чат отправить не получилось.\n"
            f"<code>{escape(str(exc))}</code>",
            reply_markup=quiet_menu(chat_id, bool(settings.media_file_id)),
        )
        return

    await state.clear()
    await message.answer(
        f"Готово: {escape(target_name)} затих на <b>{minutes}</b> мин.",
        reply_markup=quiet_menu(chat_id, bool(settings.media_file_id)),
    )


@router.message(AdminInput.paid_message, F.chat.type == "private")
async def ui_paid_message(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        await state.clear()
        await message.answer("Не могу определить пользователя.", reply_markup=main_menu())
        return

    data = await state.get_data()
    chat_id = data.get("chat_id")
    if not isinstance(chat_id, int):
        await state.clear()
        await message.answer("Группа не выбрана.", reply_markup=main_menu())
        return

    text = message_html_text(message)
    if not text:
        await message.answer("Отправь текст сообщения для публикации.")
        return

    chat = db.get_chat(chat_id)
    if chat is None:
        await state.clear()
        await message.answer("Группа не найдена.", reply_markup=main_menu())
        return
    if not await is_chat_member(message.bot, chat_id, message.from_user.id):
        await state.clear()
        await message.answer("Платная публикация доступна только в группах, где ты состоишь.", reply_markup=main_menu())
        return

    payload = f"paid_message:{message.from_user.id}:{chat_id}:{uuid4().hex}"
    db.save_pending_star_message(payload, message.from_user.id, chat_id, text)
    try:
        await message.bot.send_invoice(
            chat_id=message.chat.id,
            title="Сообщение за звезды",
            description=f"Публикация сообщения в группе {chat.title}",
            payload=payload,
            currency="XTR",
            prices=[LabeledPrice(label="Публикация сообщения", amount=1)],
            provider_token="",
        )
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        db.delete_pending_star_message(payload)
        await state.clear()
        await message.answer(
            "Не получилось создать счет на оплату.\n"
            f"<code>{escape(str(exc))}</code>",
            reply_markup=main_menu(),
        )
        return

    await state.clear()


def premium_status_text(user_id: int) -> str:
    current = premium_service.get_user_plan(user_id)
    subscription = premium_service.get_user_subscription(user_id)
    lines = ["<b>Premium-тарифы</b>", "Бесплатного доступа к медиа-функциям нет.", ""]
    for plan in PLANS.values():
        lines.extend(
            [
                f"<b>{escape(plan.title)}</b> — {plan.price_stars} ⭐ / {PREMIUM_PERIOD_DAYS} дней",
                f"Медиа-задач: {plan.daily_media_tasks}/день; файл до {plan.max_file_size_bytes // (1024 * 1024)} МБ; "
                f"расшифровка до {plan.max_transcription_seconds // 60} мин.",
                f"Шахта: ожидание −{round((1 - plan.cooldown_multiplier) * 100)}%, "
                f"монеты +{round((plan.coins_multiplier - 1) * 100)}%, "
                f"восстановление удачи +{round((plan.luck_regen_multiplier - 1) * 100)}%.",
                "",
            ]
        )
    if current and subscription:
        lines.append(f"Текущий тариф: <b>{escape(current.title)}</b>")
        lines.append(f"Активен до: <b>{datetime.fromisoformat(subscription['expires_at']).astimezone().strftime('%d.%m.%Y %H:%M')}</b>")
        lines.append(f"Использовано медиа-задач сегодня: <b>{premium_service.daily_media_usage(user_id)}/{current.daily_media_tasks}</b>")
    else:
        lines.append("Текущий тариф: <b>Premium не активен</b>")
    return "\n".join(lines)


async def send_premium_invoice(message: Message, plan_key: str) -> None:
    if not message.from_user:
        return
    plan = premium_service.get_plan_config(plan_key)
    try:
        await message.bot.send_invoice(
            chat_id=message.chat.id,
            title=plan.title,
            description=f"Premium на {PREMIUM_PERIOD_DAYS} дней: медиа-функции и бонусы шахты.",
            payload=premium_payment_payload(plan.key, message.from_user.id),
            currency="XTR",
            prices=[LabeledPrice(label=plan.title, amount=plan.price_stars)],
            provider_token="",
        )
    except Exception as exc:
        premium_service.log("ERROR", f"Premium invoice failed: user={message.from_user.id}, plan={plan.key}, error={exc}")
        await message.answer(f"Не получилось создать счёт Premium.\n<code>{escape(str(exc))}</code>")


async def send_premium_invoice_to_user(bot: Bot, chat_id: int, user_id: int, plan_key: str) -> None:
    plan = premium_service.get_plan_config(plan_key)
    await bot.send_invoice(
        chat_id=chat_id,
        title=plan.title,
        description=f"Premium на {PREMIUM_PERIOD_DAYS} дней: медиа-функции и бонусы шахты.",
        payload=premium_payment_payload(plan.key, user_id),
        currency="XTR",
        prices=[LabeledPrice(label=plan.title, amount=plan.price_stars)],
        provider_token="",
    )


@router.message(Command("premium"))
async def premium_command(message: Message) -> None:
    if message.from_user:
        premium_service.ensure_user(message.from_user.id, message.from_user.username)
        await message.answer(premium_status_text(message.from_user.id), reply_markup=premium_menu())


@router.message(Command("profile"))
async def profile_command(message: Message) -> None:
    if message.from_user:
        chat_id = message.chat.id if message.chat.type in SUPPORTED_CHAT_TYPES else None
        if chat_id is not None:
            await remember_sender(message)
        await message.answer(
            telegram_user_profile_text(
                message.from_user.id,
                message.from_user.username,
                message.from_user.full_name,
                chat_id=chat_id,
                short=False,
            ),
            reply_markup=(
                main_menu()
                if message.chat.type == "private"
                else social_profile_markup(chat_id, message.from_user.id, message.from_user.id)
            ),
            disable_web_page_preview=True,
        )


@router.message(F.chat.type == "private", F.text.casefold() == "профиль")
async def profile_private_ru(message: Message) -> None:
    await profile_command(message)


@router.message(F.chat.type.in_(SUPPORTED_CHAT_TYPES), F.text.regexp(SECRET_MESSAGE_RE))
async def secret_message_group_command(message: Message) -> None:
    if not message.from_user or not message.text:
        return

    match = SECRET_MESSAGE_RE.match(message.text)
    if not match:
        return
    username = normalize_username(match.group(1)) if match.group(1) else None
    leaked_text = (match.group(2) or "").strip()

    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass

    if leaked_text:
        await temporary_chat_notice(
            message,
            "Чтобы скрытый текст не попал в логи группы, пиши только <code>лс @ник</code> или ответом <code>лс</code>. Сам текст бот попросит в личке.",
            delay_seconds=20,
        )
        return

    if message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.is_bot:
        await temporary_chat_notice(message, "Ботам скрытые сообщения не отправляем.", delay_seconds=20)
        return

    target_id, target_name, error = await resolve_command_target(message, username)
    if error or target_id is None or target_name is None:
        await temporary_chat_notice(message, error or "Не удалось определить адресата.", delay_seconds=20)
        return
    if target_id == message.from_user.id:
        await temporary_chat_notice(message, "Себе можно написать и без посредников, но ход красивый.", delay_seconds=20)
        return

    compose_id = secrets.token_hex(8)
    try:
        await message.bot.send_message(
            message.from_user.id,
            (
                f"Напиши скрытое сообщение для <b>{escape(target_name)}</b>.\n"
                "Я не буду публиковать текст в группе — там появится только кнопка для адресата.\n\n"
                "Чтобы отменить, напиши <code>отмена</code>."
            ),
            disable_web_page_preview=True,
        )
    except (TelegramBadRequest, TelegramForbiddenError):
        await temporary_chat_notice(
            message,
            "Открой личный чат с ботом и нажми /start, потом повтори <code>лс</code> в группе.",
            delay_seconds=25,
        )
        return

    db.save_secret_message_compose(compose_id, message.from_user.id, message.chat.id, target_id, target_name)
    await temporary_chat_notice(message, "Ок, текст жду в личке. В группе его не будет.", delay_seconds=15)


@router.message(F.chat.type == "private", F.text, has_secret_message_compose)
async def secret_message_private_compose(message: Message) -> None:
    if not message.from_user or not message.text:
        return
    compose = db.get_secret_message_compose_for_sender(message.from_user.id)
    if compose is None:
        return
    text = message.text.strip()
    if text.casefold() in {"отмена", "cancel", "/cancel"}:
        db.delete_secret_message_compose(compose.compose_id)
        await message.answer("Скрытое сообщение отменено.")
        return
    if len(text) > 2000:
        await message.answer("Слишком длинно. Скрытое сообщение — до 2000 символов.")
        return

    message_id = secrets.token_hex(8)
    db.save_secret_message(
        message_id=message_id,
        chat_id=compose.chat_id,
        sender_id=message.from_user.id,
        sender_username=message.from_user.username,
        sender_name=message.from_user.full_name,
        target_id=compose.target_id,
        target_name=compose.target_name,
        text=text,
    )
    db.delete_secret_message_compose(compose.compose_id)
    try:
        await message.bot.send_message(
            compose.chat_id,
            f"{escape(compose.target_name)}, вам анонимное письмецо в конверте.",
            reply_markup=secret_message_markup(message_id),
            disable_web_page_preview=True,
        )
    except (TelegramBadRequest, TelegramForbiddenError):
        db.delete_secret_message(message_id)
        await message.answer("Не получилось отправить кнопку в группу. Сообщение отменено.")
        return
    await message.answer("Готово. В группе появилась кнопка для адресата, текст там не опубликован.")


@router.message(Command("media"))
async def media_command(message: Message) -> None:
    if not message.from_user:
        return
    if not premium_service.has_active_premium(message.from_user.id):
        await message.answer("Для этой функции нужен Premium.", reply_markup=premium_menu())
        return
    await message.answer(
        "<b>Медиа-инструменты</b>\n\nВыберите действие, затем пришлите файл.",
        reply_markup=media_tools_menu(),
    )


@router.message(Command("buy_basic"))
async def buy_basic_command(message: Message) -> None:
    await send_premium_invoice(message, "basic")


@router.message(Command("buy_extended"))
async def buy_extended_command(message: Message) -> None:
    await send_premium_invoice(message, "extended")


@router.callback_query(F.data == "premium:menu")
async def cb_premium_menu(callback: CallbackQuery) -> None:
    premium_service.ensure_user(callback.from_user.id, callback.from_user.username)
    await safe_edit(callback, premium_status_text(callback.from_user.id), reply_markup=premium_menu())


@router.callback_query(F.data.startswith("premium:buy:"))
async def cb_premium_buy(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    plan_key = (callback.data or "").rsplit(":", 1)[-1]
    if plan_key not in PLANS:
        await callback.answer("Неизвестный тариф.", show_alert=True)
        return
    try:
        await send_premium_invoice_to_user(callback.bot, callback.message.chat.id, callback.from_user.id, plan_key)
        await callback.answer()
    except Exception as exc:
        premium_service.log("ERROR", f"Premium invoice failed: user={callback.from_user.id}, plan={plan_key}, error={exc}")
        await callback.answer("Не получилось создать счёт.", show_alert=True)


def media_history_text(user_id: int) -> str:
    media = MediaTaskService(str(premium_service.path))
    try:
        tasks = media.get_user_media_tasks(user_id, 20)
    finally:
        media.close()
    if not tasks:
        return "<b>Мои медиа-задачи</b>\n\nЗадач пока нет."
    status_names = {
        "queued": "в очереди",
        "processing": "обрабатывается",
        "completed": "готово",
        "failed": "ошибка",
        "cancelled": "отменено",
    }
    lines = ["<b>Мои медиа-задачи</b>", ""]
    for task in tasks:
        title = TASK_TITLES.get(task.task_type, task.task_type)
        lines.append(f"#{task.id} В· {escape(title)} В· <b>{status_names.get(task.status, task.status)}</b>")
    return "\n".join(lines)


@router.callback_query(F.data == "media:menu")
async def cb_media_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if not premium_service.has_active_premium(callback.from_user.id):
        await callback.answer("Для этой функции нужен Premium.", show_alert=True)
        await safe_edit(callback, premium_status_text(callback.from_user.id), reply_markup=premium_menu())
        return
    availability = "доступен" if ffmpeg_available() else "не найден"
    whisper_status = "доступен" if whisper_available() else "не найден"
    await safe_edit(
        callback,
        "<b>Медиа-инструменты</b>\n\nВыберите действие, затем пришлите файл.\n"
        "Для скачивания с YouTube просто отправьте ссылку в этот чат.\n"
        f"FFmpeg: <b>{availability}</b>.\nFaster-Whisper: <b>{whisper_status}</b>.",
        reply_markup=media_tools_menu(),
    )


@router.callback_query(F.data == "media:history")
async def cb_media_history(callback: CallbackQuery) -> None:
    await safe_edit(callback, media_history_text(callback.from_user.id), reply_markup=media_tools_menu())


@router.callback_query(F.data.startswith("media:tool:"))
async def cb_media_tool(callback: CallbackQuery, state: FSMContext) -> None:
    task_type = (callback.data or "").split(":", 2)[-1]
    if task_type not in TASK_TITLES:
        await callback.answer("Операция не поддерживается.", show_alert=True)
        return
    if not premium_service.has_active_premium(callback.from_user.id):
        await callback.answer("Для этой функции нужен Premium.", show_alert=True)
        return
    await state.set_state(MediaInput.waiting_file)
    await state.update_data(media_task_type=task_type)
    await safe_edit(
        callback,
        f"<b>{escape(TASK_TITLES[task_type])}</b>\n\nПришлите видео, аудио, голосовое сообщение или файл.",
        reply_markup=media_cancel_menu(),
    )


def message_media_file(message: Message):
    return message.document or message.video or message.audio or message.voice or message.animation


@router.message(MediaInput.waiting_file)
async def media_file_received(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return
    media_file = message_media_file(message)
    if media_file is None:
        await message.answer("Пришлите файл, видео, аудио или голосовое сообщение.", reply_markup=media_cancel_menu())
        return
    data = await state.get_data()
    task_type = str(data.get("media_task_type", ""))
    if task_type not in TASK_TITLES:
        await state.clear()
        await message.answer("Операция потеряна. Выберите её заново.", reply_markup=media_tools_menu())
        return

    file_name = getattr(media_file, "file_name", None) or f"{media_file.file_unique_id}.bin"
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", file_name)
    input_dir = Path("media_storage") / "inputs" / str(message.from_user.id)
    input_dir.mkdir(parents=True, exist_ok=True)
    source_path = input_dir / f"{uuid4().hex}_{safe_name}"
    progress = await message.answer("Загружаю файл и ставлю задачу в очередь...")
    service = MediaTaskService(str(premium_service.path))
    task = None
    output_path: str | None = None
    try:
        declared_size = int(getattr(media_file, "file_size", 0) or 0)
        if declared_size <= 0:
            telegram_file = await message.bot.get_file(media_file.file_id)
            declared_size = int(getattr(telegram_file, "file_size", 0) or 0)
        if declared_size <= 0:
            raise PremiumLimitError("Telegram не сообщил размер файла; безопасная проверка лимита невозможна.")
        declared_duration = getattr(media_file, "duration", None)
        premium_service.check_media_limits(
            message.from_user.id, declared_size, declared_duration, task_type
        )
        await message.bot.download(media_file.file_id, destination=source_path)
        actual_size = source_path.stat().st_size
        duration_seconds = declared_duration
        if task_type in {"transcription", "transcription_timestamps"} and duration_seconds is None:
            duration_seconds = await asyncio.to_thread(probe_media_duration, str(source_path))
            if duration_seconds is None:
                raise PremiumLimitError("Не удалось определить длительность файла для проверки лимита расшифровки.")
        premium_service.check_media_limits(
            message.from_user.id, actual_size, duration_seconds, task_type
        )
        task = service.create_media_task(
            user_id=message.from_user.id,
            task_type=task_type,
            source_file_id=media_file.file_id,
            source_file_path=str(source_path),
            file_size_bytes=actual_size,
            duration_seconds=duration_seconds,
        )
        service.update_media_task_status(task.id, "processing")
        await progress.edit_text(f"Задача #{task.id}: FFmpeg обрабатывает файл...")
        output_path = await asyncio.to_thread(
            process_media,
            task_type,
            str(source_path),
            str(Path("media_storage") / "outputs" / str(message.from_user.id)),
            task.id,
        )
        service.set_output_file_path(task.id, output_path)
        service.update_media_task_status(task.id, "completed")
        await message.answer_document(
            FSInputFile(output_path),
            caption=f"Готово: {escape(TASK_TITLES[task_type])}\nЗадача #{task.id}",
        )
        await message.answer(
            "<b>Медиа-инструменты</b>\n\nВыберите следующее действие или вернитесь к Premium.",
            reply_markup=media_tools_menu(),
        )
        await progress.delete()
        await state.clear()
    except Exception as exc:
        if task is not None:
            service.update_media_task_status(task.id, "failed", str(exc))
        await progress.edit_text(
            "Не получилось обработать файл.\n"
            f"<code>{escape(str(exc)[-1500:])}</code>",
            reply_markup=media_tools_menu(),
        )
        await state.clear()
    finally:
        if output_path:
            with suppress(OSError):
                Path(output_path).unlink(missing_ok=True)
            if task is not None:
                with suppress(Exception):
                    service.set_output_file_path(task.id, None)
        service.close()
        source_path.unlink(missing_ok=True)


@router.message(F.chat.type == "private", F.text.regexp(SUPPORTED_MEDIA_URL_RE))
async def youtube_link_received(message: Message, state: FSMContext) -> None:
    url = extract_supported_media_url(message.text)
    if not url:
        return
    is_instagram = extract_instagram_url(url) is not None
    if is_instagram:
        progress = await message.answer("\u041f\u0440\u043e\u0432\u0435\u0440\u044f\u044e \u0441\u0441\u044b\u043b\u043a\u0443 Instagram...")
        await state.update_data(youtube_url=url, youtube_title="Instagram Reels", youtube_is_music=False, youtube_is_instagram=True)
        await progress.edit_text(
            "<b>Instagram Reels</b>\n\n"
            "\u0421\u0441\u044b\u043b\u043a\u0430 \u043f\u0440\u0438\u043d\u044f\u0442\u0430. \u041d\u0430\u0436\u043c\u0438\u0442\u0435 \u043a\u043d\u043e\u043f\u043a\u0443, \u0447\u0442\u043e\u0431\u044b \u0441\u043a\u0430\u0447\u0430\u0442\u044c Reels \u0432 MP4.",
            reply_markup=instagram_download_menu(),
            disable_web_page_preview=True,
        )
        return
    progress = await message.answer("Проверяю ссылку Instagram..." if is_instagram else "Проверяю ссылку YouTube...")
    try:
        info = await asyncio.to_thread(inspect_youtube, url)
    except YoutubeMediaError as exc:
        await progress.edit_text(str(exc))
        return
    await state.update_data(youtube_url=url, youtube_title=info.title, youtube_is_music=info.is_music, youtube_is_instagram=is_instagram)
    duration = f"{info.duration // 60}:{info.duration % 60:02d}" if info.duration else "неизвестна"
    await progress.edit_text(
        f"<b>{escape(info.title)}</b>\n"
        f"Длительность: <b>{duration}</b>\n\n"
        "Выберите формат. Скачивание начнётся только после нажатия кнопки.",
        reply_markup=instagram_download_menu() if is_instagram else youtube_download_menu(info.is_music),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data == "youtube:cancel")
async def cb_youtube_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(youtube_url=None, youtube_title=None, youtube_is_music=None)
    await safe_edit(callback, "\u0421\u043a\u0430\u0447\u0438\u0432\u0430\u043d\u0438\u0435 \u043e\u0442\u043c\u0435\u043d\u0435\u043d\u043e.", reply_markup=media_tools_menu())


@router.callback_query(F.data.startswith("youtube:"))
async def cb_youtube_download(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    download_type = (callback.data or "").split(":", 1)[-1]
    if download_type not in DOWNLOAD_TYPES:
        return
    if not premium_service.has_active_premium(callback.from_user.id):
        await callback.answer("Для этой функции нужен Premium.", show_alert=True)
        return
    data = await state.get_data()
    url = data.get("youtube_url")
    if not isinstance(url, str) or not url:
        await callback.answer("Ссылка устарела. Отправьте её ещё раз.", show_alert=True)
        return
    await callback.answer()
    is_instagram = bool(data.get("youtube_is_instagram"))
    if is_instagram and download_type != "video_mp4":
        await callback.answer("Instagram Reels можно скачать только как MP4.", show_alert=True)
        return
    await safe_edit(callback, "\u041f\u0440\u043e\u0432\u0435\u0440\u044f\u044e \u0440\u0430\u0437\u043c\u0435\u0440 \u0438 \u0441\u043e\u0437\u0434\u0430\u044e \u0437\u0430\u0434\u0430\u0447\u0443 \u0441\u043a\u0430\u0447\u0438\u0432\u0430\u043d\u0438\u044f...")
    service = MediaTaskService(str(premium_service.path))
    task = None
    output_path = None
    try:
        if is_instagram:
            media_title = str(data.get("youtube_title") or "Instagram Reels")
            estimated_size = 0
            duration_seconds = None
        else:
            info = await asyncio.to_thread(inspect_youtube, url, download_type)
            if download_type.startswith("music_") and not info.is_music:
                raise YoutubeMediaError("Форматы YouTube Music доступны только для ссылок music.youtube.com.")
            media_title = info.title
            estimated_size = info.estimated_size
            duration_seconds = info.duration
        plan = premium_service.check_media_limits(
            callback.from_user.id,
            estimated_size,
            duration_seconds,
            None,
        )
        task_type = {
            "video_mp4": "youtube_video",
            "audio_mp3": "youtube_audio",
            "music_mp3": "youtube_music_audio",
            "music_m4a": "youtube_music_audio",
        }[download_type]
        if is_instagram:
            task_type = "instagram_reel"
        task = service.create_media_task(
            user_id=callback.from_user.id,
            task_type=task_type,
            source_file_id=download_type,
            source_file_path=url,
            file_size_bytes=estimated_size,
            duration_seconds=duration_seconds,
        )
        service.update_media_task_status(task.id, "processing")
        premium_service.log("INFO", f"YouTube task created: id={task.id}, user={callback.from_user.id}, type={download_type}")
        await callback.message.edit_text(f"\u0417\u0430\u0434\u0430\u0447\u0430 #{task.id}: yt-dlp \u0441\u043a\u0430\u0447\u0438\u0432\u0430\u0435\u0442 \u0438 \u043e\u0431\u0440\u0430\u0431\u0430\u0442\u044b\u0432\u0430\u0435\u0442 \u0444\u0430\u0439\u043b...")
        output_path = await asyncio.to_thread(
            download_youtube, url, download_type, task.id, plan.max_file_size_bytes
        )
        actual_size = Path(output_path).stat().st_size
        if actual_size > plan.max_file_size_bytes:
            raise YoutubeMediaError(
                f"Итоговый файл превышает лимит тарифа: {plan.max_file_size_bytes // (1024 * 1024)} МБ."
            )
        service.set_output_file_path(task.id, output_path)
        service.update_media_task_status(task.id, "completed")
        premium_service.log("INFO", f"YouTube download completed: id={task.id}, bytes={actual_size}")
        await callback.message.answer_document(
            FSInputFile(output_path, filename=media_output_filename(media_title, output_path)),
            caption=f"\u0413\u043e\u0442\u043e\u0432\u043e: {escape(media_title)}",
        )
        premium_service.log("INFO", f"YouTube file sent: id={task.id}, user={callback.from_user.id}")
        await callback.message.answer(
            "<b>\u041c\u0435\u0434\u0438\u0430-\u0438\u043d\u0441\u0442\u0440\u0443\u043c\u0435\u043d\u0442\u044b</b>\n\n\u041c\u043e\u0436\u043d\u043e \u043e\u0442\u043f\u0440\u0430\u0432\u0438\u0442\u044c \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0443\u044e \u0441\u0441\u044b\u043b\u043a\u0443 \u0438\u043b\u0438 \u0432\u044b\u0431\u0440\u0430\u0442\u044c \u0434\u0440\u0443\u0433\u0443\u044e \u043e\u043f\u0435\u0440\u0430\u0446\u0438\u044e.",
            reply_markup=media_tools_menu(),
        )
        cleanup_youtube_file(output_path)
        await state.update_data(youtube_url=None, youtube_title=None, youtube_is_music=None)
    except (YoutubeMediaError, PremiumRequiredError, PremiumLimitError) as exc:
        if task is not None:
            service.update_media_task_status(task.id, "failed", str(exc))
        cleanup_youtube_file(output_path)
        premium_service.log("ERROR", f"YouTube task failed: user={callback.from_user.id}, error={exc}")
        await callback.message.edit_text(str(exc), reply_markup=instagram_download_menu() if is_instagram else media_tools_menu())
    except Exception as exc:
        if task is not None:
            service.update_media_task_status(task.id, "failed", str(exc))
        cleanup_youtube_file(output_path)
        premium_service.log("CRITICAL", f"YouTube task crashed: user={callback.from_user.id}, error={exc}")
        if staff_service:
            await staff_service.log(callback.bot, "CRITICAL", f"YouTube task crashed: {exc}", notify=True)
        await callback.message.edit_text(
            f"\u041d\u0435 \u043f\u043e\u043b\u0443\u0447\u0438\u043b\u043e\u0441\u044c \u0441\u043a\u0430\u0447\u0430\u0442\u044c \u0444\u0430\u0439\u043b.\n<code>{escape(str(exc)[-1500:])}</code>",
            reply_markup=instagram_download_menu() if is_instagram else media_tools_menu(),
        )
    finally:
        service.close()


@router.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
    pending = db.get_pending_star_message(pre_checkout_query.invoice_payload)
    if pending is None:
        premium_payment = parse_premium_payment_payload(pre_checkout_query.invoice_payload)
        if premium_payment is not None:
            plan_key, user_id = premium_payment
            plan = premium_service.get_plan_config(plan_key)
            if user_id != pre_checkout_query.from_user.id:
                await pre_checkout_query.answer(ok=False, error_message="Этот счёт создан для другого пользователя.")
                return
            if pre_checkout_query.currency != "XTR" or pre_checkout_query.total_amount != plan.price_stars:
                await pre_checkout_query.answer(ok=False, error_message="Неверная стоимость Premium.")
                return
            await pre_checkout_query.answer(ok=True)
            return
        subscription_user_id = parse_user_subscription_payload(pre_checkout_query.invoice_payload)
        if subscription_user_id is not None:
            if subscription_user_id != pre_checkout_query.from_user.id:
                await pre_checkout_query.answer(ok=False, error_message="Этот счёт создан для другого пользователя.")
                return
            if pre_checkout_query.currency != "XTR" or pre_checkout_query.total_amount != user_subscription_stars():
                await pre_checkout_query.answer(ok=False, error_message="Неверная стоимость подписки.")
                return
            await pre_checkout_query.answer(ok=True)
            return
        dig_star = parse_dig_star_payload(pre_checkout_query.invoice_payload)
        if dig_star is None:
            await pre_checkout_query.answer(
                ok=False,
                error_message="Счет устарел. Создай покупку заново.",
            )
            return

        _, user_id, chat_id = dig_star
        if user_id != pre_checkout_query.from_user.id:
            await pre_checkout_query.answer(
                ok=False,
                error_message="Этот счет создан для другого пользователя.",
            )
            return
        if db.get_dig_player(chat_id, user_id) is None and dig_star[0] != "golden_ticket":
            await pre_checkout_query.answer(
                ok=False,
                error_message="Сначала зарегистрируйся в игре.",
            )
            return
        if pre_checkout_query.currency != "XTR" or pre_checkout_query.total_amount != dig_star_price(dig_star[0]):
            await pre_checkout_query.answer(
                ok=False,
                error_message="Неверная сумма счета. Создай покупку заново.",
            )
            return

        await pre_checkout_query.answer(ok=True)
        return
    if pending.user_id != pre_checkout_query.from_user.id:
        await pre_checkout_query.answer(
            ok=False,
            error_message="Этот счет создан для другого пользователя.",
        )
        return
    if db.get_chat(pending.chat_id) is None:
        await pre_checkout_query.answer(
            ok=False,
            error_message="Группа для публикации больше не найдена.",
        )
        return
    if not await is_chat_member(pre_checkout_query.bot, pending.chat_id, pending.user_id):
        await pre_checkout_query.answer(
            ok=False,
            error_message="Публикация доступна только участникам выбранной группы.",
        )
        return
    if pre_checkout_query.currency != "XTR" or pre_checkout_query.total_amount != 1:
        await pre_checkout_query.answer(
            ok=False,
            error_message="Неверная сумма счета. Создай публикацию заново.",
        )
        return

    await pre_checkout_query.answer(ok=True)


async def handle_dig_star_payment(message: Message, payment: SuccessfulPayment) -> bool:
    parsed = parse_dig_star_payload(payment.invoice_payload)
    if parsed is None:
        return False

    action, user_id, chat_id = parsed
    if payment.currency != "XTR" or payment.total_amount != dig_star_price(action):
        await message.answer("Оплата прошла, но сумма покупки не совпала. Напиши администратору бота.")
        return True
    if not message.from_user or message.from_user.id != user_id:
        await message.answer("Оплата прошла, но пользователь покупки не совпал. Напиши администратору бота.")
        return True

    if db.has_star_payment_charge(payment.telegram_payment_charge_id):
        await message.answer("Эта оплата уже была обработана ранее.")
        return True

    player = db.get_dig_player(chat_id, user_id)
    if player is None:
        if action == "golden_ticket" and message.from_user:
            db.register_dig_player(0, message.from_user.id, message.from_user.username, message.from_user.full_name)
            player = db.get_dig_player(0, user_id)
        else:
            await message.answer("Оплата прошла, но игрок не найден. Напиши администратору бота.")
            return True

    if action == "luck":
        now = datetime.now(timezone.utc)
        purchase_action = "luck"
        item_key = None
        quantity = 1
        luck_at = now.isoformat(timespec="seconds")
        result = "Оплата прошла. Удача восстановлена до <b>100</b>/100."
    elif action == "cooldown":
        purchase_action = "cooldown"
        item_key = None
        quantity = 1
        luck_at = None
        result = "Оплата прошла. Ожидание между раскопками сброшено, можно писать <code>копай</code>."
    else:
        _, _, _, item_key, quantity = DIG_STAR_ACTIONS[action]
        if item_key is None:
            await message.answer("Оплата прошла, но пакет раскопок не найден. Напиши администратору бота.")
            return True
        purchase_action = "item"
        luck_at = None
        if item_key == "golden_ticket":
            result = "Оплата прошла. Золотой билет добавлен в шахту Mini App."
        elif item_key == "super_game_pass":
            result = "Оплата прошла. Добавлен доступ к супер-игре 9×9."
        elif item_key == "super_mute30":
            result = "Оплата прошла. Право на мут на 30 минут добавлено в сумку Mini App."
        elif item_key == "star_depth_10":
            result = "Оплата прошла. Следующая раскопка гарантированно пройдет <b>10 м</b> без ожидания."
        elif item_key == "star_lucky_dig":
            result = f"Оплата прошла. Начислено дополнительных раскопок со <b>100 удачей</b>: <b>{quantity}</b>."
        else:
            result = f"Оплата прошла. Начислено дополнительных раскопок без ожидания: <b>{quantity}</b>."

    applied = db.apply_dig_star_purchase_once(
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        chat_id=chat_id,
        amount=payment.total_amount,
        currency=payment.currency,
        charge_id=payment.telegram_payment_charge_id,
        action=purchase_action,
        item_key=item_key,
        quantity=quantity,
        luck_at=luck_at,
    )
    if not applied:
        await message.answer("Эта оплата уже была обработана ранее.")
        return True
    await message.answer(result)
    return True


async def handle_user_subscription_payment(message: Message, payment: SuccessfulPayment) -> bool:
    user_id = parse_user_subscription_payload(payment.invoice_payload)
    if user_id is None:
        return False
    if not message.from_user or message.from_user.id != user_id:
        await message.answer("Оплата подписки получена, но пользователь не совпал.")
        return True
    if payment.currency != "XTR" or payment.total_amount != user_subscription_stars():
        await message.answer("Оплата подписки получена, но сумма не совпала.")
        return True
    expiration = payment.subscription_expiration_date or (datetime.now(timezone.utc) + timedelta(days=30))
    db.set_user_subscription(user_id, "active", expiration.isoformat(timespec="seconds"), payment.telegram_payment_charge_id)
    if not db.has_star_payment_charge(payment.telegram_payment_charge_id):
        db.add_star_payment(
            user_id=user_id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
            chat_id=None,
            amount=payment.total_amount,
            currency=payment.currency,
            charge_id=payment.telegram_payment_charge_id,
        )
    await message.answer(f"Подписка MonkeyDin активна до <b>{expiration.astimezone().strftime('%d.%m.%Y %H:%M')}</b>.")
    return True


async def handle_premium_payment(message: Message, payment: SuccessfulPayment) -> bool:
    parsed = parse_premium_payment_payload(payment.invoice_payload)
    if parsed is None:
        return False
    plan_key, user_id = parsed
    plan = premium_service.get_plan_config(plan_key)
    if not message.from_user or message.from_user.id != user_id:
        await message.answer("Оплата Premium получена, но пользователь не совпал.")
        return True
    if payment.currency != "XTR" or payment.total_amount != plan.price_stars:
        await message.answer("Оплата Premium получена, но сумма не совпала.")
        return True
    if db.has_star_payment_charge(payment.telegram_payment_charge_id):
        await message.answer("Эта оплата Premium уже была обработана.")
        return True
    expiration = payment.subscription_expiration_date or (datetime.now(timezone.utc) + timedelta(days=PREMIUM_PERIOD_DAYS))
    premium_service.activate_subscription(
        user_id=user_id,
        username=message.from_user.username,
        plan=plan_key,
        expires_at=expiration,
        telegram_payment_charge_id=payment.telegram_payment_charge_id,
        provider_payment_charge_id=payment.provider_payment_charge_id,
    )
    db.add_star_payment(
        user_id=user_id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        chat_id=None,
        amount=payment.total_amount,
        currency=payment.currency,
        charge_id=payment.telegram_payment_charge_id,
    )
    await message.answer(
        f"Premium активирован: <b>{escape(plan.title)}</b>.\n"
        f"Действует до <b>{expiration.astimezone().strftime('%d.%m.%Y %H:%M')}</b>."
    )
    return True


@router.message(F.successful_payment)
async def successful_paid_message(message: Message, state: FSMContext) -> None:
    payment = message.successful_payment
    if payment is None:
        return

    pending = db.get_pending_star_message(payment.invoice_payload)
    if pending is None:
        if await handle_premium_payment(message, payment):
            await state.clear()
            return
        if await handle_user_subscription_payment(message, payment):
            await state.clear()
            return
        if await handle_dig_star_payment(message, payment):
            await state.clear()
            return
        await message.answer("Оплата прошла, но сообщение не найдено. Напиши администратору бота.")
        await state.clear()
        return

    chat_id = pending.chat_id
    text = pending.text
    if payment.currency != "XTR" or payment.total_amount != 1:
        await message.answer("Оплата прошла, но сумма публикации не совпала. Напиши администратору бота.")
        await state.clear()
        return
    if not message.from_user or not await is_chat_member(message.bot, chat_id, message.from_user.id):
        await message.answer(
            "Оплата получена, но публикация отменена: ты больше не состоишь в выбранной группе. "
            "Обратись к владельцу бота для возврата Stars."
        )
        await state.clear()
        return
    claimed_pending = db.claim_pending_star_message(payment.invoice_payload)
    if claimed_pending is None:
        await message.answer("Эта оплата уже обрабатывается или была обработана ранее.")
        await state.clear()
        return

    sender = "пользователя"
    if message.from_user:
        sender = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name

    try:
        await message.bot.send_message(
            chat_id=chat_id,
            text=f"<b>Сообщение от {escape(sender)}</b>\n\n{text}",
            disable_web_page_preview=True,
        )
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        await message.answer(
            "Оплата прошла, но бот не смог опубликовать сообщение в группу.\n"
            f"<code>{escape(str(exc))}</code>"
        )
        await state.clear()
        return

    if message.from_user and payment:
        db.add_star_payment(
            user_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
            chat_id=chat_id,
            amount=payment.total_amount,
            currency=payment.currency,
            charge_id=payment.telegram_payment_charge_id,
        )

    await state.clear()
    await message.answer("Оплата прошла. Сообщение опубликовано.", reply_markup=main_menu())


@router.message(AdminInput.feedback, F.chat.type == "private")
async def ui_feedback(message: Message, state: FSMContext) -> None:
    text = message_html_text(message)
    if not text:
        await message.answer("Отправь текстовое описание ошибки или предложения.")
        return

    if not BOT_ADMIN_IDS:
        await state.clear()
        await message.answer("Администраторы бота не настроены. Обратная связь временно недоступна.", reply_markup=main_menu())
        return

    user = message.from_user
    user_line = "Пользователь неизвестен"
    if user:
        username = f"@{user.username}" if user.username else "без username"
        user_line = f"{escape(user.full_name)} ({escape(username)}), id <code>{user.id}</code>"

    admin_text = (
        "<b>Обратная связь</b>\n"
        f"От: {user_line}\n\n"
        f"{text}"
    )

    delivered = 0
    for admin_id in BOT_ADMIN_IDS:
        try:
            await message.bot.send_message(
                admin_id,
                admin_text,
                disable_web_page_preview=True,
                reply_markup=feedback_reply_menu(user.id) if user else None,
            )
            delivered += 1
        except (TelegramBadRequest, TelegramForbiddenError):
            continue

    await state.clear()
    if delivered:
        await message.answer("Спасибо. Сообщение отправлено администратору бота.", reply_markup=main_menu())
    else:
        await message.answer(
            "Не получилось доставить сообщение администратору. Возможно, админ еще не писал боту в личку.",
            reply_markup=main_menu(),
        )


@router.message(AdminInput.feedback_reply, F.chat.type == "private")
async def ui_feedback_reply(message: Message, state: FSMContext) -> None:
    if not message.from_user or not is_bot_admin(message.from_user.id):
        await state.clear()
        await message.answer("Ответ доступен только администратору бота.", reply_markup=main_menu())
        return

    data = await state.get_data()
    user_id = data.get("feedback_user_id")
    if not isinstance(user_id, int):
        await state.clear()
        await message.answer("Пользователь для ответа не найден.", reply_markup=main_menu())
        return

    text = message_html_text(message)
    if not text:
        await message.answer("Отправь текст ответа пользователю.")
        return

    try:
        await message.bot.send_message(
            user_id,
            "<b>Ответ администратора</b>\n\n"
            f"{text}",
            disable_web_page_preview=True,
        )
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        await state.clear()
        await message.answer(
            "Не получилось отправить ответ пользователю. Возможно, он заблокировал бота.\n"
            f"<code>{escape(str(exc))}</code>",
            reply_markup=main_menu(),
        )
        return

    await state.clear()
    await message.answer("Ответ отправлен пользователю.", reply_markup=main_menu())


@router.message(AdminInput.set_roll_mute, F.chat.type == "private")
async def ui_set_roll_mute(message: Message, state: FSMContext) -> None:
    chat_id = await require_state_admin(message, state)
    if chat_id is None:
        return
    if not message.from_user or not is_bot_admin(message.from_user.id):
        await state.clear()
        await message.answer("Настройка доступна только администратору бота.", reply_markup=main_menu())
        return

    parsed = parse_roll_mute_payload(message.text)
    if not parsed:
        await message.answer("Формат: <code>60 30</code>, где 60 - мут в минутах, 30 - кулдаун в минутах.")
        return

    mute_minutes, cooldown_minutes = parsed
    db.set_roll_mute_settings(chat_id, mute_minutes, cooldown_minutes, message.from_user.id)
    await state.clear()
    await message.answer(
        f"Roll mute настроен: мут <b>{mute_minutes}</b> мин, кулдаун <b>{cooldown_minutes}</b> мин.",
        reply_markup=back_to_chat_menu(chat_id),
    )


def is_single_emoji_message(message: Message) -> bool:
    text = message.text
    if not text:
        return False

    stripped = text.strip()
    if SINGLE_EMOJI_RE.fullmatch(stripped):
        return True

    entities = message.entities or []
    if stripped != text or len(entities) != 1:
        return False
    entity = entities[0]
    entity_type = getattr(entity.type, "value", entity.type)
    utf16_length = len(text.encode("utf-16-le")) // 2
    return entity_type == "custom_emoji" and entity.offset == 0 and entity.length == utf16_length


def is_alarm_restricted_message(message: Message) -> bool:
    return bool(message.sticker) or is_single_emoji_message(message)


async def delete_alarm_restricted_message(message: Message) -> bool:
    restrictions_enabled, api_enabled, last_status, has_saved_permissions = cached_alarm_runtime(message.chat.id)
    if not restrictions_enabled or not api_enabled or last_status not in {"A", "P"} or not has_saved_permissions:
        return False
    user_id = message.from_user.id if message.from_user else None
    if await is_alarm_restriction_exempt(message.bot, message.chat.id, user_id):
        return False

    return await delete_message_now_or_later(message)


async def delete_single_emoji_during_alarm(message: Message) -> bool:
    return await delete_alarm_restricted_message(message)


@router.edited_message(F.chat.type.in_(SUPPORTED_CHAT_TYPES))
async def delete_edited_single_emoji_during_alarm(message: Message) -> None:
    if is_single_emoji_message(message):
        await delete_single_emoji_during_alarm(message)


async def fetch_alerts_location_status() -> str:
    if not ALERTS_API_TOKEN:
        raise RuntimeError("ALERTS_API_TOKEN не настроен")
    url = f"https://api.alerts.in.ua/v1/iot/active_air_raid_alerts/{ALERTS_LOCATION_UID}.json"
    timeout = aiohttp.ClientTimeout(total=15)
    headers = {"Authorization": f"Bearer {ALERTS_API_TOKEN}"}
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, headers=headers) as response:
            if response.status != 200:
                body = await response.text()
                raise RuntimeError(f"Alerts.in.ua HTTP {response.status}: {body[:200]}")
            status = str(await response.json(content_type=None)).strip().upper()
            if status not in {"A", "P", "N"}:
                raise RuntimeError(f"Неизвестный статус Alerts.in.ua: {status!r}")
            return status


async def apply_alarm_restrictions(bot: Bot, chat_id: int) -> None:
    settings = db.get_alarm_settings(chat_id)
    try:
        if not settings.permissions_json:
            chat = await bot.get_chat(chat_id)
            db.save_alarm_permissions(chat_id, permissions_to_dict(getattr(chat, "permissions", None)))
        await bot.set_chat_permissions(
            chat_id=chat_id,
            permissions=media_locked_permissions(),
            use_independent_chat_permissions=True,
        )
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        logging.warning("Could not apply alarm permissions in chat %s: %s", chat_id, exc)

    # Reactions are not disabled globally: Telegram applies that to admins too.
    # Regular users' reactions are removed by delete_reactions_during_alarm instead.


async def send_alarm_notification(bot: Bot, chat_id: int, text: str) -> Message | None:
    thread_id = db.get_alarm_settings(chat_id).alarm_thread_id
    try:
        kwargs = {"chat_id": chat_id, "text": text}
        if thread_id is not None:
            kwargs["message_thread_id"] = thread_id
        return await bot.send_message(**kwargs)
    except (TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter) as exc:
        logging.warning(
            "Could not send alarm notification in chat %s, thread %s: %s",
            chat_id,
            thread_id,
            exc,
        )
        return None


async def delete_previous_alarm_status_message(bot: Bot, chat_id: int, status: str) -> None:
    message_ids = db.alarm_api_status_message_ids(chat_id, status)
    if not message_ids:
        return
    for message_id in message_ids:
        with suppress(TelegramBadRequest, TelegramForbiddenError, TelegramNotFound, TelegramRetryAfter):
            await bot.delete_message(chat_id, message_id)
    db.clear_alarm_api_status_message_ids(chat_id, status)


async def activate_alarm_from_api(bot: Bot, chat_id: int) -> bool:
    settings = db.get_alarm_settings(chat_id)
    restrictions_enabled = db.alarm_restrictions_enabled(chat_id)
    if restrictions_enabled:
        await apply_alarm_restrictions(bot, chat_id)

    await delete_previous_alarm_status_message(bot, chat_id, "N")
    alert_message = await send_alarm_notification(
        bot,
        chat_id,
        f"Alerts.in.ua сообщает: объявлена воздушная тревога — <b>{ALERTS_LOCATION_TITLE}</b>.",
    )
    if alert_message is not None:
        db.set_alarm_api_status_message_id(chat_id, "A", alert_message.message_id)
    if not restrictions_enabled:
        return alert_message is not None
    action_text = settings.alarm_text or (
        "Режим тревоги применен: медиа, реакции и одиночные эмодзи ограничены для участников. "
        "Админы не ограничиваются."
    )
    action_message = await send_alarm_notification(bot, chat_id, action_text)
    if action_message is not None:
        db.set_alarm_api_action_message_id(chat_id, "A", action_message.message_id)
    return alert_message is not None and action_message is not None


async def restore_alarm_restrictions(bot: Bot, chat_id: int) -> None:
    settings = db.get_alarm_settings(chat_id)
    try:
        saved = json.loads(settings.permissions_json) if settings.permissions_json else None
        await bot.set_chat_permissions(
            chat_id=chat_id,
            permissions=ChatPermissions(**saved) if saved else default_open_permissions(),
            use_independent_chat_permissions=True,
        )
        if settings.permissions_json:
            db.pop_alarm_permissions(chat_id)
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        logging.warning("Could not restore alarm permissions in chat %s: %s", chat_id, exc)

    if settings.reactions_json is None:
        return

    try:
        saved_reactions = json.loads(settings.reactions_json)
        await set_chat_available_reactions(bot, chat_id, saved_reactions)
        if settings.reactions_json is not None:
            db.pop_alarm_reactions(chat_id)
    except TelegramNotFound:
        if settings.reactions_json is not None:
            db.pop_alarm_reactions(chat_id)
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        if "not found" in str(exc).casefold():
            if settings.reactions_json is not None:
                db.pop_alarm_reactions(chat_id)
        else:
            logging.warning("Could not restore alarm reactions in chat %s: %s", chat_id, exc)


async def deactivate_alarm_from_api(bot: Bot, chat_id: int) -> bool:
    settings = db.get_alarm_settings(chat_id)
    had_restrictions = bool(settings.permissions_json or settings.reactions_json is not None)
    await restore_alarm_restrictions(bot, chat_id)

    await delete_previous_alarm_status_message(bot, chat_id, "A")
    clear_message = await send_alarm_notification(
        bot,
        chat_id,
        f"Alerts.in.ua сообщает: отбой воздушной тревоги — <b>{ALERTS_LOCATION_TITLE}</b>.",
    )
    if clear_message is not None:
        db.set_alarm_api_status_message_id(chat_id, "N", clear_message.message_id)
    if not had_restrictions:
        return clear_message is not None
    action_text = settings.clear_text or "Отбой применен: медиа, реакции и одиночные эмодзи снова включены."
    action_message = await send_alarm_notification(bot, chat_id, action_text)
    if action_message is not None:
        db.set_alarm_api_action_message_id(chat_id, "N", action_message.message_id)
    return clear_message is not None and action_message is not None


async def alerts_monitor_loop(bot: Bot) -> None:
    initial_sync = True
    while True:
        try:
            chat_ids = db.list_alarm_api_chats()
            if chat_ids and ALERTS_API_TOKEN:
                status = await fetch_alerts_location_status()
                active = status in {"A", "P"}
                if initial_sync:
                    baseline = "A" if active else "N"
                    for chat_id in chat_ids:
                        db.set_alarm_api_last_status(chat_id, status)
                        db.set_alarm_api_last_notified_status(chat_id, baseline)
                    initial_sync = False
                    await asyncio.sleep(ALERTS_POLL_INTERVAL_SECONDS)
                    continue
                for chat_id in chat_ids:
                    previous = db.alarm_api_last_status(chat_id)
                    notified = db.alarm_api_last_notified_status(chat_id)
                    if previous != status:
                        db.set_alarm_api_last_status(chat_id, status)
                    if active and notified != "A":
                        if await activate_alarm_from_api(bot, chat_id):
                            db.set_alarm_api_last_notified_status(chat_id, "A")
                    elif not active and notified != "N":
                        if previous is None and notified is None:
                            db.set_alarm_api_last_notified_status(chat_id, "N")
                        elif await deactivate_alarm_from_api(bot, chat_id):
                            db.set_alarm_api_last_notified_status(chat_id, "N")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logging.warning("Alerts.in.ua monitor error: %s", exc)
        await asyncio.sleep(ALERTS_POLL_INTERVAL_SECONDS)


def alarm_status_text(chat_id: int) -> str:
    settings = db.get_alarm_settings(chat_id)
    destination = (
        "основной чат"
        if settings.alarm_thread_id is None
        else f"тема <code>{settings.alarm_thread_id}</code>"
    )
    if not db.alarm_api_enabled(chat_id):
        return (
            "Автоматическое отслеживание тревоги для этой группы не включено.\n"
            f"Тревожные оповещения: {destination}."
        )

    status = db.alarm_api_last_status(chat_id)
    if status == "A":
        return f"В <b>{ALERTS_LOCATION_TITLE}</b> сейчас воздушная тревога.\nОповещения: {destination}."
    if status == "P":
        return f"В <b>{ALERTS_LOCATION_TITLE}</b> сейчас частичная воздушная тревога.\nОповещения: {destination}."
    if status == "N":
        return f"В <b>{ALERTS_LOCATION_TITLE}</b> сейчас нет воздушной тревоги.\nОповещения: {destination}."
    return f"Статус тревоги еще не получен. Попробуй снова через минуту.\nОповещения: {destination}."


async def handle_alarm_mode(message: Message) -> bool:
    if not message.text:
        return False

    topic_match = ALARM_TOPIC_COMMAND_RE.fullmatch(message.text)
    if topic_match:
        if message.chat.type not in SUPPORTED_CHAT_TYPES:
            return True
        if not message.from_user or not await is_chat_admin(
            message.bot, message.chat.id, message.from_user.id
        ):
            await safe_reply(
                message,
                "Тему для тревожных оповещений может назначить только администратор группы.",
            )
            return True

        reset = topic_match.group(1) in {"основной", "сброс", "сбросить"}
        thread_id = None if reset else message.message_thread_id
        if thread_id is None and not reset:
            await safe_reply(
                message,
                "Выполни команду внутри нужной темы. Для основного чата: "
                "<code>тревога тема основной</code>.",
            )
            return True

        db.set_alarm_thread(message.chat.id, thread_id, message.from_user.id)
        if thread_id is None:
            await safe_reply(message, "Тревожные оповещения снова будут приходить в основной чат.")
        else:
            await safe_reply(
                message,
                f"Тема для тревожных оповещений закреплена: <code>{thread_id}</code>.",
            )
        return True

    if ALARM_STATUS_COMMAND_RE.fullmatch(message.text):
        await safe_reply(message, alarm_status_text(message.chat.id))
        return True

    if ALARM_STATUS_QUERY_RE.fullmatch(message.text) or ALARM_CLEAR_QUERY_RE.fullmatch(message.text):
        return True

    return False


@router.message_reaction()
async def delete_reactions_during_alarm(event: MessageReactionUpdated, bot: Bot) -> None:
    if event.chat.type not in SUPPORTED_CHAT_TYPES:
        return

    user_id = event.user.id if event.user else None
    actor_chat_id = event.actor_chat.id if event.actor_chat else None
    if user_id is not None and event.new_reaction and db.get_active_quiet_admin(
        event.chat.id,
        user_id,
        datetime.now(timezone.utc).isoformat(timespec="seconds"),
    ):
        try:
            await bot.delete_message_reaction(
                chat_id=event.chat.id,
                message_id=event.message_id,
                user_id=user_id,
            )
        except (TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter):
            return
        return

    restrictions_enabled, api_enabled, last_status, has_saved_permissions = cached_alarm_runtime(event.chat.id)
    if (
        not restrictions_enabled
        or not api_enabled
        or last_status not in {"A", "P"}
        or not has_saved_permissions
        or not event.new_reaction
    ):
        return

    if user_id is None and actor_chat_id is None:
        return
    if await is_alarm_restriction_exempt(bot, event.chat.id, user_id):
        return

    try:
        await bot.delete_message_reaction(
            chat_id=event.chat.id,
            message_id=event.message_id,
            user_id=user_id,
            actor_chat_id=actor_chat_id,
        )
    except (TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter):
        return


async def handle_birthdays(message: Message) -> None:
    today = datetime.now().date()
    sent_date = today.isoformat()
    cache_key = (message.chat.id, sent_date)
    now = time.monotonic()
    if now - BIRTHDAY_CHECK_CACHE.get(cache_key, 0) < 1800:
        return
    BIRTHDAY_CHECK_CACHE[cache_key] = now

    birthdays = db.birthdays_for_date(message.chat.id, today.day, today.month, sent_date)
    for birthday in birthdays:
        await safe_reply(message, f"Сегодня праздник: <b>{escape(birthday.text)}</b> 🎉")
        db.mark_birthday_sent(message.chat.id, birthday.id, sent_date)


async def handle_blacklist(message: Message) -> bool:
    content = message.text or message.caption
    if not content:
        return False

    text = normalize_trigger(content)
    for item in cached_blacklist_words(message.chat.id):
        if has_trigger(text, item.word):
            try:
                await message.delete()
            except (TelegramBadRequest, TelegramForbiddenError):
                pass

            await message.answer("Данные выражения запрещены в чате.")
            return True

    return False


@router.message(Command("setreply"))
async def set_reply(message: Message) -> None:
    if not await require_admin(message):
        return

    payload = split_command_payload(message_html_content(message))
    media = reply_media_from_message(message)
    username, reply_text = split_reply_payload(payload)
    if not username.startswith("@") or (not reply_text and not media):
        await message.answer("Формат: <code>/setreply @username - текст автоответа</code>")
        return

    await remember_sender(message)
    media_type, media_file_id = media if media else (None, None)
    db.set_reply(message.chat.id, username, reply_text, message.from_user.id if message.from_user else None, media_type, media_file_id)
    invalidate_chat_runtime_cache(message.chat.id)
    await notify_staff_autoreply_change(message.bot, f"@ответ @{normalize_username(username)} изменён для чата {message.chat.id}.")
    await message.answer(f"Готово. Автоответ для <b>@{escape(normalize_username(username))}</b> сохранен.")


@router.message(F.text.regexp(re.compile(r"^/ответ(\s|$)", re.IGNORECASE)))
async def set_reply_ru(message: Message) -> None:
    command, payload = split_text_command(message_html_content(message))
    if command != "/ответ":
        return

    if not await require_admin(message):
        return

    media = reply_media_from_message(message)
    username, reply_text = split_reply_payload(payload)
    if not username.startswith("@") or (not reply_text and not media):
        await message.answer("Формат: <code>/ответ @username - текст автоответа</code>")
        return

    await remember_sender(message)
    media_type, media_file_id = media if media else (None, None)
    db.set_reply(message.chat.id, username, reply_text, message.from_user.id if message.from_user else None, media_type, media_file_id)
    invalidate_chat_runtime_cache(message.chat.id)
    await notify_staff_autoreply_change(message.bot, f"@ответ @{normalize_username(username)} изменён для чата {message.chat.id}.")
    await message.answer(f"Готово. Автоответ для <b>@{escape(normalize_username(username))}</b> сохранен.")


@router.message(F.text.regexp(re.compile(r"^/мойответ(\s|$)", re.IGNORECASE)))
async def my_reply_ru(message: Message) -> None:
    command, payload = split_text_command(message_html_content(message))
    if command != "/мойответ":
        return

    if not await require_admin(message):
        return

    if not message.from_user or not message.from_user.username:
        await message.answer("У вашего аккаунта нет username. Добавьте username в Telegram или используйте /ответ.")
        return

    media = reply_media_from_message(message)
    if not payload and not media:
        await message.answer("Формат: <code>/мойответ текст автоответа</code>")
        return

    await remember_sender(message)
    media_type, media_file_id = media if media else (None, None)
    db.set_reply(message.chat.id, message.from_user.username, payload, message.from_user.id, media_type, media_file_id)
    invalidate_chat_runtime_cache(message.chat.id)
    await notify_staff_autoreply_change(message.bot, f"@ответ @{message.from_user.username.lower()} изменён для чата {message.chat.id}.")
    await message.answer(f"Готово. Автоответ для <b>@{escape(message.from_user.username.lower())}</b> сохранен.")


@router.message(F.text.regexp(re.compile(r"^/удалитьответ(\s|$)", re.IGNORECASE)))
async def del_reply_ru(message: Message) -> None:
    command, payload = split_text_command(message.text)
    if command != "/удалитьответ":
        return

    if not await require_admin(message):
        return

    if not payload.startswith("@"):
        await message.answer("Формат: <code>/удалитьответ @username</code>")
        return

    deleted = db.delete_reply(message.chat.id, payload)
    invalidate_chat_runtime_cache(message.chat.id)
    if deleted:
        await notify_staff_autoreply_change(message.bot, f"@ответ @{normalize_username(payload)} удалён из чата {message.chat.id}.")
    await message.answer("Автоответ удален." if deleted else "Для этого username автоответ не найден.")


@router.message(F.text.casefold() == "/списокответов")
async def list_replies_ru(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        await message.answer("Открой /старт в личке и выбери группу.")
        return
    if not await require_admin(message):
        return

    await message.answer(replies_text(message.chat.id))


@router.message(Command("settrigger"))
async def set_trigger(message: Message) -> None:
    if not await require_admin(message):
        return

    payload = split_command_payload(message_html_content(message))
    media = reply_media_from_message(message)
    trigger, reply_text = split_trigger_payload(payload)
    if not trigger or (not reply_text and not media):
        await message.answer("Формат: <code>/settrigger слово - текст ответа</code>")
        return

    await remember_sender(message)
    media_type, media_file_id = media if media else (None, None)
    db.set_trigger(message.chat.id, trigger, reply_text, message.from_user.id if message.from_user else None, media_type, media_file_id)
    invalidate_chat_runtime_cache(message.chat.id)
    await notify_staff_autoreply_change(message.bot, f"Триггер «{normalize_trigger(trigger)}» изменён для чата {message.chat.id}.")
    await message.answer(f"Фиксированный ответ на <b>{escape(normalize_trigger(trigger))}</b> сохранен.")


@router.message(F.text.regexp(re.compile(r"^/(тригер|триггер)(\s|$)", re.IGNORECASE)))
async def set_trigger_ru(message: Message) -> None:
    command, payload = split_text_command(message_html_content(message))
    if command not in {"/тригер", "/триггер"}:
        return

    if not await require_admin(message):
        return

    media = reply_media_from_message(message)
    trigger, reply_text = split_trigger_payload(payload)
    if not trigger or (not reply_text and not media):
        await message.answer("Формат: <code>/тригер слово - текст ответа</code>")
        return

    await remember_sender(message)
    media_type, media_file_id = media if media else (None, None)
    db.set_trigger(message.chat.id, trigger, reply_text, message.from_user.id if message.from_user else None, media_type, media_file_id)
    invalidate_chat_runtime_cache(message.chat.id)
    await notify_staff_autoreply_change(message.bot, f"Триггер «{normalize_trigger(trigger)}» изменён для чата {message.chat.id}.")
    await message.answer(f"Фиксированный ответ на <b>{escape(normalize_trigger(trigger))}</b> сохранен.")


@router.message(F.text.regexp(re.compile(r"^/удалитьтригер(\s|$)", re.IGNORECASE)))
async def del_trigger_ru(message: Message) -> None:
    command, payload = split_text_command(message.text)
    if command != "/удалитьтригер":
        return

    if not await require_admin(message):
        return

    if not payload:
        await message.answer("Формат: <code>/удалитьтригер слово</code>")
        return

    deleted = db.delete_trigger(message.chat.id, payload)
    invalidate_chat_runtime_cache(message.chat.id)
    if deleted:
        await notify_staff_autoreply_change(message.bot, f"Триггер «{normalize_trigger(payload)}» удалён из чата {message.chat.id}.")
    await message.answer("Фиксированный ответ удален." if deleted else "Такой фиксированный ответ не найден.")


@router.message(F.text.casefold() == "/списоктригеров")
async def list_triggers_ru(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        await message.answer("Открой /старт в личке и выбери группу.")
        return
    if not await require_admin(message):
        return

    triggers = db.list_triggers(message.chat.id)
    if not triggers:
        await message.answer("В этой группе пока нет фиксированных ответов.")
        return

    lines = ["<b>Фиксированные ответы:</b>"]
    for item in triggers:
        media = f" [{escape(item.media_type)}]" if item.media_type else ""
        lines.append(f"{escape(item.trigger)}{media} - {preview_html(item.text)}")
    await message.answer("\n".join(lines))


@router.message(Command("participants"))
async def participants(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        await message.answer("Открой /start в личке и выбери группу.")
        return

    await remember_sender(message)
    users = db.list_pickable_users(message.chat.id)
    await message.answer(
        f"Бот запомнил участников с @username для розыгрышей: <b>{len(users)}</b>.\n\n"
        "В список попадают только те, кто уже писал в этой группе после запуска бота."
    )


@router.message(F.text.casefold() == "/участники")
async def participants_ru(message: Message) -> None:
    await participants(message)


@router.message(F.text.casefold() == "/каналы")
async def channels_ru(message: Message) -> None:
    if not message.from_user:
        await message.answer("Не могу определить пользователя.")
        return

    chats = await admin_chats_for_user(message.bot, message.from_user.id)
    if not chats:
        await message.answer("Нет доступных групп, где ты админ.")
        return

    bot_user = await message.bot.me()
    lines = ["<b>Проверка групп:</b>"]
    for item in chats:
        try:
            member = await message.bot.get_chat_member(item.chat_id, bot_user.id)
            status = member_status_text(member.status)
        except (TelegramBadRequest, TelegramForbiddenError):
            status = "нет доступа"
        lines.append(f"{mention_chat_link(item)} - {escape(status)}")

    await message.answer("\n".join(lines))


@router.message(F.text.casefold() == "/помощь")
async def help_ru(message: Message) -> None:
    await message.answer(
        "Русские команды:\n"
        "/старт\n"
        "/настройки\n"
        "/регистрация\n"
        "/ответ @username текст\n"
        "/мойответ текст\n"
        "/удалитьответ @username\n"
        "/списокответов\n"
        "/тригер слово - текст\n"
        "/удалитьтригер слово\n"
        "/списоктригеров\n"
        "/участники\n"
        "/каналы\n"
        "копай\n"
        "сумка\n"
        "достижения\n"
        "топ копания\n"
        "топ монет",
        reply_markup=main_menu() if message.chat.type == "private" else None,
    )


async def handle_day_pick(message: Message) -> bool:
    settings = db.get_giveaway_settings(message.chat.id)
    if not message.text:
        return False

    incoming = normalize_trigger(message.text).strip(" ?!.")
    if incoming != settings.trigger:
        return False

    await remember_sender(message)
    today = datetime.now().date().isoformat()
    pick_key = settings.trigger
    picked = db.get_giveaway_picks(message.chat.id, pick_key, today)
    if picked:
        active_picked = []
        for user in picked:
            if await is_valid_giveaway_user(message.bot, message.chat.id, user.user_id):
                active_picked.append(user)
        picked = active_picked

    if len(picked) != settings.winners_count:
        users = db.list_pickable_users(message.chat.id)
        if not users:
            await safe_reply(message, "Пока некого выбрать: бот еще не видел участников с username.")
            return True

        random.shuffle(users)
        picked = []
        for user in users:
            if await is_valid_giveaway_user(message.bot, message.chat.id, user.user_id):
                picked.append(user)
                if len(picked) >= settings.winners_count:
                    break
        if not picked:
            await safe_reply(message, "Пока некого выбрать: из запомненных пользователей с username никто не найден в этом чате.")
            return True

        picked_ids = [user.user_id for user in picked]
        db.set_giveaway_picks(message.chat.id, pick_key, today, picked_ids)

    db.award_giveaway_stats_once(message.chat.id, pick_key, today, [user.user_id for user in picked])

    lines = [f"<b>{escape(settings.title)}:</b>"]
    for index, user in enumerate(picked, start=1):
        link = await current_profile_link(
            message.bot,
            message.chat.id,
            user.user_id,
            user.username,
            user.full_name,
        )
        lines.append(f"{index}. {link}")
    await safe_reply(message, "\n".join(lines))
    return True


async def chat_top_page_text(bot: Bot, chat_id: int, kind: str, page: int) -> tuple[str, int, int]:
    if kind == "giveaway":
        items = db.top_giveaway_stats(chat_id, limit=None)
        title = "Топ пидоров"
    elif kind == "roll":
        items = db.top_roll_mute_stats(chat_id, limit=None)
        title = "Топ roll mute"
    elif kind == "depth":
        items = db.top_dig_depth(chat_id, limit=None)
        title = "Топ копания"
    elif kind == "coins":
        items = db.top_dig_coins(chat_id, limit=None)
        title = "Топ монет"
    else:
        return "Неизвестный топ.", 0, 0

    total = len(items)
    max_page = max(0, (total - 1) // TOP_PAGE_SIZE)
    page = max(0, min(page, max_page))
    start = page * TOP_PAGE_SIZE
    lines = [f"<b>{title}:</b>"]
    for index, item in enumerate(items[start : start + TOP_PAGE_SIZE], start=start + 1):
        suffix = dig_title_suffix(dig_items_map(item.chat_id, item.user_id)) if kind in {"depth", "coins"} else ""
        link = await current_profile_link(bot, chat_id, item.user_id, item.username, item.full_name, suffix)
        if kind == "giveaway":
            value = f"<b>{item.wins_count}</b>"
        elif kind == "roll":
            value = f"<b>{item.unlucky_count}</b>"
        elif kind == "depth":
            value = f"<b>{item.total_depth}</b> м"
        else:
            value = f"<b>{item.coins}</b> котоинов"
        lines.append(f"{index}. {link} - {value}")
    return "\n".join(lines), page, total


async def send_chat_top(message: Message, kind: str, empty_text: str) -> None:
    text, page, total = await chat_top_page_text(message.bot, message.chat.id, kind, 0)
    if not total:
        await temporary_reply(message, empty_text)
        return
    await temporary_reply(
        message,
        text,
        reply_markup=chat_top_page_menu(kind, message.chat.id, page, total),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("top:"))
async def cb_chat_top_page(callback: CallbackQuery) -> None:
    _, kind, chat_id_raw, page_raw = callback.data.split(":", 3)
    chat_id = int(chat_id_raw)
    if callback.message.chat.id != chat_id:
        await callback.answer("Эта страница относится к другому чату.", show_alert=True)
        return
    text, page, total = await chat_top_page_text(callback.bot, chat_id, kind, int(page_raw))
    if not total:
        await callback.answer("Топ пока пуст.", show_alert=True)
        return
    await safe_edit(
        callback,
        text,
        reply_markup=chat_top_page_menu(kind, chat_id, page, total),
        disable_web_page_preview=True,
    )
    await callback.answer()


@router.message(F.text.regexp(re.compile(r"^топ\s+пидоров[?!.]?$", re.IGNORECASE)))
async def giveaway_top(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return

    await remember_sender(message)
    await send_chat_top(message, "giveaway", "Топ пока пуст. Сначала вызови дневной розыгрыш: кто пидор")


@router.message(F.text.regexp(re.compile(r"^профиль(?:\s+@[A-Za-z0-9_]{5,32})?[?!.]?$", re.IGNORECASE)))
async def chat_profile(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES or not message.from_user:
        return

    await remember_sender(message)
    target_id = message.from_user.id
    target_username = message.from_user.username
    target_name = message.from_user.full_name
    match = re.match(r"^профиль(?:\s+@([A-Za-z0-9_]{5,32}))?", message.text or "", flags=re.IGNORECASE)
    if match and match.group(1):
        seen = db.get_seen_user_by_username(message.chat.id, match.group(1))
        if not seen:
            await temporary_reply(message, "Я еще не видел этого пользователя в чате. Ответь командой <code>профиль</code> на его сообщение.")
            return
        target_id = seen.user_id
        target_username = seen.username
        target_name = seen.full_name
    elif message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.id != message.from_user.id:
        user = message.reply_to_message.from_user
        target_id = user.id
        target_username = user.username
        target_name = user.full_name
        db.upsert_seen_user(message.chat.id, user.id, user.username, user.full_name, user.is_bot)

    member = await get_active_chat_member(message.bot, message.chat.id, target_id)
    if member is None or is_deleted_or_empty_user(member.user):
        await temporary_reply(message, "Этот пользователь больше не состоит в группе или его аккаунт удалён.")
        return
    target_username = member.user.username
    target_name = member.user.full_name
    db.upsert_seen_user(
        message.chat.id,
        member.user.id,
        member.user.username,
        member.user.full_name,
        member.user.is_bot,
    )

    await temporary_reply(
        message,
        telegram_user_profile_text(target_id, target_username, target_name, chat_id=message.chat.id, short=True),
        reply_markup=social_profile_markup(message.chat.id, message.from_user.id, target_id),
        disable_web_page_preview=True,
    )


@router.message(F.text.casefold() == "копай")
async def dig_command(message: Message) -> None:
    if not message.from_user:
        return
    block = db.get_dig_block(message.from_user.id)
    if block:
        reason = str(block.get("reason") or "").strip()
        await temporary_reply(
            message,
            "Доступ к шахте заблокирован." + (f" Причина: {escape(reason)}" if reason else ""),
        )
        return
    if message.chat.type == "private":
        player = db.get_dig_player(0, message.from_user.id)
        registered_text = ""
        if player is None:
            db.register_dig_player(0, message.from_user.id, message.from_user.username, message.from_user.full_name)
            registered_text = "Ты зарегистрирован в шахте.\n\n"
        await message.answer(
            registered_text
            + "Выбери способ раскопки:\n\n"
            "• <b>Автоматически</b> — быстрый результат, добыча ниже, без ручных событий и ресурсов.\n"
            "• <b>Вручную</b> — Mini App: клетки, события, ресурсы и выборы по ходу вылазки. Торговец ждёт снаружи в сумке.",
            reply_markup=user_dig_mode_menu(0, message.from_user.id),
        )
        return
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return

    await remember_sender(message)
    player = db.get_dig_player(message.chat.id, message.from_user.id)
    if player is None:
        await temporary_reply(
            message,
            "Ты еще не зарегистрирован в раскопках. Нажми кнопку регистрации, потом снова напиши <code>копай</code>.",
            reply_markup=dig_register_menu(message.from_user.id),
        )
        await send_matching_trigger_after_command(message)
        return

    await temporary_reply(
        message,
        "Выбери способ раскопки:\n\n"
        "• <b>Автоматически</b> — быстрый результат, добыча ниже, без ручных событий и ресурсов.\n"
        "• <b>Вручную</b> — Mini App: клетки, события, ресурсы и выборы по ходу вылазки. Торговец ждёт снаружи в сумке.",
        reply_markup=user_dig_mode_menu(message.chat.id, message.from_user.id),
    )
    await send_matching_trigger_after_command(message)
    return

@router.message(F.text.casefold() == "сумка")
async def dig_bag(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return
    if not message.from_user:
        return

    await remember_sender(message)
    player = db.get_dig_player(message.chat.id, message.from_user.id)
    if player is None:
        await temporary_reply(
            message,
            "Ты еще не зарегистрирован в раскопках. Нажми кнопку регистрации, потом снова напиши <code>сумка</code>.",
            delay_seconds=30,
            reply_markup=dig_register_menu(message.from_user.id),
        )
        return

    text = dig_bag_text(message.chat.id, message.from_user.id)
    if text is None:
        await temporary_reply(
            message,
            "Сначала зарегистрируйся в шахте.",
            delay_seconds=30,
            reply_markup=dig_register_menu(message.from_user.id),
        )
        return
    await temporary_reply(
        message,
        text,
        delay_seconds=30,
        reply_markup=dig_bag_menu(message.from_user.id),
    )


@router.message(F.text.casefold() == "маршруты")
async def dig_routes_command(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES or not message.from_user:
        return
    if db.get_dig_player(message.chat.id, message.from_user.id) is None:
        await temporary_reply(message, "Сначала зарегистрируйся в шахте.", reply_markup=dig_register_menu(message.from_user.id))
        return
    progress = db.get_dig_progress(message.from_user.id)
    routes = [(key, data[0], key == progress["selected_route"]) for key, data in DIG_ROUTES.items()]
    await temporary_reply(message, dig_routes_text(message.from_user.id), reply_markup=dig_routes_menu(message.from_user.id, routes))


@router.message(F.text.casefold() == "контракты")
async def dig_contracts_command(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES or not message.from_user:
        return
    if db.get_dig_player(message.chat.id, message.from_user.id) is None:
        await temporary_reply(message, "Сначала зарегистрируйся в шахте.", reply_markup=dig_register_menu(message.from_user.id))
        return
    await temporary_reply(message, dig_contracts_text(message.from_user.id), reply_markup=dig_bag_menu(message.from_user.id))


@router.message(F.text.casefold() == "экспедиция")
async def dig_expedition_command(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES or not message.from_user:
        return
    await temporary_reply(message, dig_expedition_text(message.chat.id), reply_markup=dig_bag_menu(message.from_user.id))


@router.message(F.text.casefold() == "достижения")
async def dig_achievements_command(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return
    if not message.from_user:
        return

    await remember_sender(message)
    player = db.get_dig_player(message.chat.id, message.from_user.id)
    if player is None:
        await temporary_reply(
            message,
            "Ты еще не зарегистрирован в раскопках. Нажми кнопку регистрации.",
            reply_markup=dig_register_menu(message.from_user.id),
        )
        return

    await temporary_reply(
        message,
        dig_achievements_text(message.chat.id, message.from_user.id),
        reply_markup=dig_bag_menu(message.from_user.id),
    )


@router.message(F.text.regexp(re.compile(r"^топ\s+(копания|комания)$", re.IGNORECASE)))
async def dig_depth_top(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return

    await remember_sender(message)
    await send_chat_top(message, "depth", "Топ копания пока пуст. Сначала зарегистрируйтесь и напишите: копай")


@router.message(F.text.casefold() == "топ монет")
async def dig_coins_top(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return

    await remember_sender(message)
    await send_chat_top(message, "coins", "Топ монет пока пуст. Сначала зарегистрируйтесь и напишите: копай")


@router.message(F.text.regexp(re.compile(r"^топ\s+рангов?$", re.IGNORECASE)))
async def dig_weekly_rank_top(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return

    await remember_sender(message)
    await temporary_reply(message, dig_weekly_rank_top_text())


@router.message(F.text.regexp(re.compile(r"^\+кличка(?:\s+.+)?$", re.IGNORECASE)))
async def set_super_tag(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES or not message.from_user:
        return

    await remember_sender(message)
    player = db.get_dig_player(0, message.from_user.id)
    if not player:
        await safe_reply(message, "Сначала зарегистрируйся в шахте: <code>копай</code>.")
        return

    raw_tag = re.sub(r"^\+кличка", "", message.text or "", flags=re.IGNORECASE).strip()
    tag = normalize_dig_tag(raw_tag)
    if not tag:
        await safe_reply(message, "Формат: <code>+кличка Твой тег</code>. До 16 символов.")
        return
    if db.get_dig_item_quantity(0, message.from_user.id, "super_tag") <= 0:
        await safe_reply(message, "В сумке нет права выбрать тег. Его можно выбить в сундуке супер-игры 9×9.")
        return
    if not db.consume_dig_item(0, message.from_user.id, "super_tag"):
        await safe_reply(message, "Право на тег уже использовано или закончилось.")
        return

    db.set_dig_player_tag(message.from_user.id, tag)
    await safe_reply(message, f"Кличка сохранена: <b>{escape(tag)}</b>. Теперь она видна в имени шахты.")


@router.message(F.text.regexp(re.compile(r"^(/?супермут(?:\s+@[A-Za-z0-9_]{5,32})?(?:\s+.*)?|@[A-Za-z0-9_]{5,32}\s+/?супермут(?:\s+.*)?)$", re.IGNORECASE)))
async def super_mute_user(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES or not message.from_user:
        return

    await remember_sender(message)
    parsed = parse_super_mute_payload(message.text)
    if not parsed:
        await safe_reply(message, "Формат: ответом на сообщение <code>супермут причина</code> или <code>супермут @username причина</code>.")
        return
    username, reason = parsed
    if db.get_dig_item_quantity(0, message.from_user.id, "super_mute30") <= 0:
        await safe_reply(message, "В сумке нет права на супер-мут. Его можно выбить в сундуке супер-игры 9×9.")
        return

    target_id, target_name, error = await resolve_command_target(message, username)
    if error:
        await safe_reply(message, error)
        return
    if not target_id or not target_name:
        return
    if target_id == message.from_user.id:
        await safe_reply(message, "Себя супер-мутить нельзя. Даже ради науки.")
        return
    target_member = await get_active_chat_member(message.bot, message.chat.id, target_id)
    if target_member is None or is_deleted_or_empty_user(target_member.user):
        await safe_reply(message, "Этого пользователя нельзя замутить: он не активен в чате, бот или администратор.")
        return
    target_status = member_status_text(target_member.status)
    if target_member.status in ADMIN_STATUSES or target_status in ADMIN_STATUS_TEXTS:
        await safe_reply(message, "Этого пользователя нельзя замутить: он не активен в чате, бот или администратор.")
        return
    mute_remaining = active_mute_remaining_text(target_member)
    if mute_remaining:
        await safe_reply(
            message,
            f"У данного пользователя уже есть мут. До окончания: <b>{escape(mute_remaining)}</b>.",
        )
        return

    if not db.consume_dig_item(0, message.from_user.id, "super_mute30"):
        await safe_reply(message, "Право на супер-мут уже использовано или закончилось.")
        return

    until_date = datetime.now(timezone.utc) + timedelta(minutes=30)
    try:
        await message.bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target_id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_audios=False,
                can_send_documents=False,
                can_send_photos=False,
                can_send_videos=False,
                can_send_video_notes=False,
                can_send_voice_notes=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
                can_react_to_messages=False,
            ),
            until_date=until_date,
            use_independent_chat_permissions=True,
        )
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        db.add_dig_item(0, message.from_user.id, "super_mute30", 1)
        await safe_reply(
            message,
            "Не получилось выдать супер-мут. Право вернулось в сумку.\n"
            f"<code>{escape(str(exc))}</code>",
        )
        return

    reason_line = f"\nПричина: {escape(reason)}" if reason else ""
    await safe_reply(message, f"{escape(target_name)} получает супер-мут на <b>30</b> мин.{reason_line}")


@router.message(F.text.regexp(re.compile(r"^roll\s+mute$", re.IGNORECASE)))
async def roll_mute(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return
    if not message.from_user:
        return

    await remember_sender(message)
    settings = db.get_roll_mute_settings(message.chat.id)
    now = datetime.now(timezone.utc)

    if settings.last_used_at:
        last_used = datetime.fromisoformat(settings.last_used_at)
        next_allowed = last_used + timedelta(minutes=settings.cooldown_minutes)
        if now < next_allowed:
            remaining = int((next_allowed - now).total_seconds() // 60) + 1
            await safe_reply(message, f"Roll mute на перезарядке. Осталось примерно <b>{remaining}</b> мин.")
            return

    candidates = db.list_pickable_users(message.chat.id)
    if not candidates:
        await safe_reply(message, "Некого мутить: бот еще не видел участников с @username.")
        return

    random.shuffle(candidates)
    cutoff_at = (now - timedelta(minutes=settings.cooldown_minutes)).isoformat(timespec="seconds")
    if not db.claim_roll_mute(message.chat.id, now.isoformat(timespec="seconds"), cutoff_at):
        await safe_reply(message, "Roll mute уже запустил другой участник. Дождись окончания перезарядки.")
        return
    until_date = now + timedelta(minutes=settings.mute_minutes)
    picked = None
    picked_member = None
    protected = False
    last_error = None
    for candidate in candidates:
        member = await current_roll_mute_target_member(message.bot, message.chat.id, candidate.user_id)
        if member is None:
            continue

        if db.consume_dig_item(message.chat.id, candidate.user_id, "cursed_pick"):
            picked = candidate
            picked_member = member
            protected = True
            break

        try:
            await message.bot.restrict_chat_member(
                chat_id=message.chat.id,
                user_id=candidate.user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until_date,
                use_independent_chat_permissions=True,
            )
            picked = candidate
            picked_member = member
            break
        except TelegramBadRequest as exc:
            last_error = exc
            description = str(exc).casefold()
            if "member not found" in description or "participant_id_invalid" in description:
                continue
            await safe_reply(
                message,
                "Не получилось замутить участника. Проверь, что бот админ и может ограничивать участников.\n"
                f"<code>{escape(str(exc))}</code>",
            )
            return
        except TelegramForbiddenError as exc:
            last_error = exc
            await safe_reply(
                message,
                "Не получилось замутить участника. Проверь, что бот админ и может ограничивать участников.\n"
                f"<code>{escape(str(exc))}</code>",
            )
            return

    if picked is None or picked_member is None:
        detail = f"\nПоследняя ошибка: <code>{escape(str(last_error))}</code>" if last_error else ""
        await safe_reply(
            message,
            "Не нашел подходящего участника для roll mute: запомненные пользователи могли выйти из чата или оказаться админами."
            f"{detail}",
        )
        return

    current_user = picked_member.user
    name = profile_link(current_user.id, current_user.username, current_user.full_name)
    if protected:
        await safe_reply(
            message,
            f"У пользователя {name} сработала <b>Защита от сглаза</b>. Roll mute отменен.",
        )
        return

    db.increment_roll_mute_stat(message.chat.id, current_user.id)
    await safe_reply(message, f"Roll mute выбрал {name}. Мут на <b>{settings.mute_minutes}</b> мин.")


@router.message(F.text.regexp(re.compile(r"^топ\s+roll\s+mute[?!.]?$", re.IGNORECASE)))
async def roll_mute_top(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return

    await remember_sender(message)
    await send_chat_top(
        message,
        "roll",
        "Топ roll mute пока пуст. Статистика считается только для успешных <code>roll mute</code> после обновления бота.",
    )


@router.message(F.chat.type.in_(SUPPORTED_CHAT_TYPES), F.text.regexp(re.compile(r"^\+админ(?:\s|$)", re.IGNORECASE)))
async def assign_miniapp_admin_role(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES or not message.from_user:
        return
    owner_id = load_config().owner_id
    if owner_id is None or int(message.from_user.id) != int(owner_id):
        await safe_reply(message, "Назначать админов Mini App может только владелец.")
        return

    await remember_sender(message)
    role, username, payload = parse_moderator_role_payload(message.text, MODERATOR_ASSIGN_COMMANDS)
    if role != "app_admin":
        return
    target_hint, _expires_at = parse_moderator_duration(payload)
    if username is None and target_hint.startswith("@"):
        first, _, rest = target_hint.partition(" ")
        username = normalize_username(first)
        target_hint, _expires_at = parse_moderator_duration(rest)

    target_id, target_name, error = await resolve_command_target(message, username)
    if error:
        await safe_reply(message, error)
        return
    if not target_id or not target_name:
        return

    member = await get_active_chat_member(message.bot, message.chat.id, target_id)
    if member is None:
        await safe_reply(message, "Не нашел этого пользователя среди активных участников чата.")
        return

    db.set_miniapp_profile_role(target_id, "Админ", message.from_user.id)
    await safe_reply(message, f"{escape(target_name)} назначен: <b>Админ Mini App</b>.")
    await notify_staff_moderation(
        message.bot,
        (
            "🛡 <b>Назначение админа Mini App</b>\n"
            f"Кто: {escape(render_moderation_actor(message, 'admin'))}\n"
            f"Кому: {escape(target_name)}"
        ),
    )


@router.message(F.chat.type.in_(SUPPORTED_CHAT_TYPES), F.text.regexp(re.compile(r"^\+(помощник|модератор|стмодератор)(?:\s|$)", re.IGNORECASE)))
async def assign_chat_moderator_role(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES or not message.from_user:
        return
    if not await actor_can_manage_moderators(message.bot, message.chat.id, message.from_user.id):
        return

    await remember_sender(message)
    role, username, payload = parse_moderator_role_payload(message.text, MODERATOR_ASSIGN_COMMANDS)
    if not role:
        return

    target_hint, expires_at = parse_moderator_duration(payload)
    if username is None and target_hint.startswith("@"):
        first, _, rest = target_hint.partition(" ")
        username = normalize_username(first)
        target_hint, expires_at = parse_moderator_duration(rest)

    target_id, target_name, error = await resolve_command_target(message, username)
    if error:
        await safe_reply(message, error)
        return
    if not target_id or not target_name:
        return

    member = await get_active_chat_member(message.bot, message.chat.id, target_id)
    if member is None:
        await safe_reply(message, "Не нашел этого пользователя среди активных участников чата.")
        return

    db.set_chat_moderator_role(message.chat.id, target_id, role, message.from_user.id, expires_at)
    until_line = f"\nСрок: до <b>{escape(expires_at)}</b>" if expires_at else "\nСрок: бессрочно"
    await safe_reply(message, f"{escape(target_name)} назначен: <b>{moderator_role_title(role)}</b>.{until_line}")
    await notify_staff_moderation(
        message.bot,
        (
            "🛡 <b>Назначение модератора</b>\n"
            f"Кто: {escape(render_moderation_actor(message, 'admin'))}\n"
            f"Кому: {escape(target_name)}\n"
            f"Должность: <b>{moderator_role_title(role)}</b>{until_line}"
        ),
    )


@router.message(F.chat.type.in_(SUPPORTED_CHAT_TYPES), F.text.regexp(re.compile(r"^\-(помощник|модератор|стмодератор)(?:\s|$)", re.IGNORECASE)))
async def remove_chat_moderator_role(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES or not message.from_user:
        return
    if not await actor_can_manage_moderators(message.bot, message.chat.id, message.from_user.id):
        return

    await remember_sender(message)
    _role, username, payload = parse_moderator_role_payload(message.text, MODERATOR_REMOVE_COMMANDS)
    if username is None and payload.startswith("@"):
        username = normalize_username(payload.split(maxsplit=1)[0])
    target_id, target_name, error = await resolve_command_target(message, username)
    if error:
        await safe_reply(message, error)
        return
    if not target_id or not target_name:
        return

    if not db.clear_chat_moderator_role(message.chat.id, target_id):
        await safe_reply(message, f"{escape(target_name)} не числится в модераторах.")
        return
    await safe_reply(message, f"С {escape(target_name)} снята модераторская должность.")
    await notify_staff_moderation(
        message.bot,
        (
            "🛡 <b>Снятие модератора</b>\n"
            f"Кто: {escape(render_moderation_actor(message, 'admin'))}\n"
            f"С кого: {escape(target_name)}"
        ),
    )


@router.message(F.text.regexp(re.compile(r"^косяк(?:\s|$)", re.IGNORECASE)))
async def warn_user_for_misconduct(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES or not message.from_user:
        return
    actor_role = await actor_moderation_role(message.bot, message.chat.id, message.from_user.id)
    if actor_role is None:
        return

    await remember_sender(message)
    parsed = parse_warn_payload(message.text)
    if not parsed:
        return
    username, reason = parsed
    target_id, target_name, error = await resolve_command_target(message, username)
    if error:
        await safe_reply(message, error)
        return
    if not target_id or not target_name:
        return
    if target_id == message.from_user.id:
        await safe_reply(message, "Себе косяк не выдаём. Самокритика принята, но без записи.")
        return
    if await is_chat_admin(message.bot, message.chat.id, target_id):
        await safe_reply(message, "Администраторам косяки этой командой не выдаём.")
        return

    warning_id = db.add_moderation_warning(message.chat.id, target_id, message.from_user.id, reason)
    reason_line = f"\nПричина: {escape(reason)}" if reason else ""
    await safe_reply(message, f"Косяк #{warning_id} для {escape(target_name)} записан.{reason_line}")
    await notify_staff_moderation(
        message.bot,
        (
            "⚠️ <b>Косяк</b>\n"
            f"Кто: {escape(render_moderation_actor(message, actor_role))}\n"
            f"Кому: {escape(target_name)}"
            f"{reason_line}"
        ),
    )


@router.message(F.text.regexp(re.compile(r"^(модеры|рейтинг\s+модеров|модрейтинг)[?!.]?$", re.IGNORECASE)))
async def moderator_rating(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return

    await remember_sender(message)
    rows = db.list_chat_moderators(message.chat.id)
    if not rows:
        await safe_reply(message, "В этом чате пока нет назначенных модераторов.")
        return

    rows.sort(key=lambda row: (-int(row["votes_count"]), -moderator_role_rank(str(row["role"])), str(row["full_name"]).casefold()))
    lines = ["<b>Рейтинг модераторов</b>", "Голос: <code>голос @ник</code> — один активный голос от пользователя."]
    for index, row in enumerate(rows[:20], start=1):
        name = f"@{row['username']}" if row["username"] else row["full_name"]
        lines.append(
            f"{index}. {escape(str(name))} — {moderator_role_title(str(row['role']), short=True)}, "
            f"голосов: <b>{int(row['votes_count'])}</b>"
        )
    await safe_reply(message, "\n".join(lines))


@router.message(F.text.regexp(re.compile(r"^голос\s+@[A-Za-z0-9_]{5,32}(?:\s|$)", re.IGNORECASE)))
async def vote_for_moderator(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES or not message.from_user:
        return

    await remember_sender(message)
    username = parse_moderator_vote_payload(message.text)
    if not username:
        await safe_reply(message, "Формат: <code>голос @username</code>.")
        return
    target = db.get_seen_user_by_username(message.chat.id, username)
    if not target:
        await safe_reply(message, f"Я еще не видел @{escape(username)} в этом чате.")
        return
    role = db.get_chat_moderator_role(message.chat.id, target.user_id)
    if not role:
        await safe_reply(message, f"@{escape(username)} сейчас не числится в модераторах.")
        return
    if target.user_id == message.from_user.id:
        await safe_reply(message, "За себя голос не считаем. Скромность — тоже инструмент модерации.")
        return

    today = datetime.now(timezone.utc).date().isoformat()
    previous = db.moderator_vote_for_user(message.chat.id, message.from_user.id)
    db.save_moderator_vote(message.chat.id, message.from_user.id, target.user_id, today)
    changed = previous is not None and int(previous["moderator_id"]) != target.user_id
    suffix = " Голос перенесён." if changed else ""
    await safe_reply(message, f"Голос за @{escape(username)} принят.{suffix}")


@router.message(F.text.regexp(re.compile(r"^-сооб[?!.]?$", re.IGNORECASE)))
async def delete_replied_message_by_moderator(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES or not message.from_user:
        return
    actor_role = await actor_moderation_role(message.bot, message.chat.id, message.from_user.id)
    if actor_role is None:
        return
    if not moderator_can_delete_messages(actor_role):
        await safe_reply(message, "Помощник не может удалять сообщения.")
        return
    if not message.reply_to_message:
        await safe_reply(message, "Команду <code>-сооб</code> нужно отправлять ответом на сообщение, которое надо удалить.")
        return

    await remember_sender(message)
    source = message.reply_to_message
    source_author = source.from_user.full_name if source.from_user else "unknown"
    source_username = f"@{source.from_user.username}" if source.from_user and source.from_user.username else source_author
    header = (
        "🗑 <b>Удаление сообщения</b>\n"
        f"Кто: {escape(render_moderation_actor(message, actor_role))}\n"
        f"Автор сообщения: {escape(source_username)}\n"
        f"Тип: <b>{escape(message_content_label(source))}</b>\n"
        f"Чат: {escape(chat_title(message.chat))}"
    )
    await copy_deleted_message_to_staff(message.bot, source, header)
    db.add_moderator_action(message.chat.id, message.from_user.id, source.from_user.id if source.from_user else 0, "delete_message", None, message_content_label(source))
    with suppress(TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter):
        await source.delete()
    with suppress(TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter):
        await message.delete()


@router.message(F.text.regexp(re.compile(r"^подтвердить(?:\s|$)", re.IGNORECASE)))
async def confirm_helper_action(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES or not message.from_user:
        return
    actor_role = await actor_moderation_role(message.bot, message.chat.id, message.from_user.id)
    if actor_role is None:
        return
    if actor_role != "admin" and moderator_role_rank(actor_role) < moderator_role_rank("senior"):
        await safe_reply(message, "Подтверждать спорные действия помощников может только старший модератор или админ.")
        return

    await remember_sender(message)
    reason = split_command_payload(message.text).strip()
    source_line = ""
    if message.reply_to_message:
        source_line = f"\nПо сообщению: <code>{message.reply_to_message.message_id}</code>"
    reason_line = f"\nКомментарий: {escape(reason)}" if reason else ""
    await safe_reply(message, "✅ Подтверждение старшего записано.")
    await notify_staff_moderation(
        message.bot,
        (
            "✅ <b>Подтверждение спорного действия</b>\n"
            f"Кто: {escape(render_moderation_actor(message, actor_role))}\n"
            f"Чат: {escape(chat_title(message.chat))}"
            f"{source_line}"
            f"{reason_line}"
        ),
    )


@router.message(F.text.regexp(re.compile(r"^чат\s+стоп(?:\s|$)", re.IGNORECASE)))
async def stop_chat_messages(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES or not message.from_user:
        return
    actor_role = await actor_moderation_role(message.bot, message.chat.id, message.from_user.id)
    if actor_role is None:
        return

    await remember_sender(message)
    parsed = parse_chat_stop_payload(message.text)
    if parsed is None:
        return
    seconds, reason = parsed
    if not moderator_can_stop_chat(actor_role, seconds):
        if actor_role == "assistant":
            await safe_reply(message, "Помощник не может останавливать чат.")
        else:
            limit = moderator_chat_lock_limit_seconds(actor_role)
            limit_text = f"{int(limit / 60)} мин" if limit else "0 мин"
            await safe_reply(message, f"Лимит этой должности на остановку чата: <b>{limit_text}</b>. Укажи срок, например <code>чат стоп 10м причина</code>.")
        return
    until_at = None
    until_line = "до команды <code>чат старт</code>"
    if seconds is not None:
        until_dt = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        until_at = until_dt.isoformat(timespec="seconds")
        until_line = f"до <b>{escape(until_at)}</b>"

    db.set_chat_lock(message.chat.id, True, message.from_user.id, reason, until_at)
    invalidate_chat_lock_cache(message.chat.id)
    reason_line = f"\nПричина: {escape(reason)}" if reason else ""
    await safe_reply(
        message,
        (
            "🔒 <b>Чат остановлен</b>\n"
            f"Обычные участники временно не смогут писать: их сообщения будут удаляться.\n"
            "Писать могут админы Telegram и назначенные модераторы бота.\n"
            f"Срок: {until_line}"
            f"{reason_line}"
        ),
    )
    await notify_staff_moderation(
        message.bot,
        (
            "🔒 <b>Чат стоп</b>\n"
            f"Кто: {escape(render_moderation_actor(message, actor_role))}\n"
            f"Чат: {escape(chat_title(message.chat))}\n"
            f"Срок: {until_line}"
            f"{reason_line}"
        ),
    )


@router.message(F.text.regexp(re.compile(r"^чат\s+старт[?!.]?$", re.IGNORECASE)))
async def start_chat_messages(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES or not message.from_user:
        return
    actor_role = await actor_moderation_role(message.bot, message.chat.id, message.from_user.id)
    if actor_role is None:
        return
    if not moderator_can_stop_chat(actor_role, 1):
        await safe_reply(message, "Помощник не может управлять остановкой чата.")
        return

    await remember_sender(message)
    db.set_chat_lock(message.chat.id, False, message.from_user.id)
    invalidate_chat_lock_cache(message.chat.id)
    await safe_reply(message, "🔓 Чат снова открыт.")
    await notify_staff_moderation(
        message.bot,
        (
            "🔓 <b>Чат старт</b>\n"
            f"Кто: {escape(render_moderation_actor(message, actor_role))}\n"
            f"Чат: {escape(chat_title(message.chat))}"
        ),
    )


@router.message(F.text.regexp(re.compile(r"^медленно\s+(.+)$", re.IGNORECASE)))
async def set_chat_slow_mode(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES or not message.from_user:
        return
    actor_role = await actor_moderation_role(message.bot, message.chat.id, message.from_user.id)
    if actor_role is None:
        return
    if actor_role == "assistant":
        await safe_reply(message, "Помощник не может включать медленный режим.")
        return

    await remember_sender(message)
    delay = parse_slow_mode_payload(message.text)
    if delay is None:
        await safe_reply(message, "Формат: <code>медленно 30с</code>, <code>медленно 5м</code> или <code>медленно выкл</code>.")
        return
    try:
        await telegram_api_call(message.bot, "setChatSlowModeDelay", {"chat_id": message.chat.id, "slow_mode_delay": delay})
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        await safe_reply(
            message,
            "Не получилось изменить медленный режим. Проверь, что бот админ и может управлять группой.\n"
            f"<code>{escape(str(exc))}</code>",
        )
        return

    text = "🐢 Медленный режим выключен." if delay == 0 else f"🐢 Медленный режим: <b>{delay}</b> сек."
    await safe_reply(message, text)
    await notify_staff_moderation(
        message.bot,
        (
            "🐢 <b>Медленный режим</b>\n"
            f"Кто: {escape(render_moderation_actor(message, actor_role))}\n"
            f"Чат: {escape(chat_title(message.chat))}\n"
            f"Задержка: <b>{delay}</b> сек."
        ),
    )


@router.message(F.text.regexp(re.compile(r"^(@[A-Za-z0-9_]{5,32}\s+)?затихни\s+админ(?:\s+\d+)?(\s+-\s+.*)?$", re.IGNORECASE)))
async def quiet_admin_user(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return
    if not message.from_user or not await has_chat_admin_permission(
        message.bot, message.chat.id, message.from_user.id, "can_delete_messages"
    ):
        return

    await remember_sender(message)
    parsed = parse_quiet_admin_payload(message.text)
    if not parsed:
        await safe_reply(message, "Формат: ответом на сообщение <code>затихни админ 60 - причина</code> или <code>@username затихни админ 60 - причина</code>")
        return
    username, minutes, reason = parsed
    target_id, target_name, error = await resolve_command_target(message, username)
    if error:
        await safe_reply(message, error)
        return
    if not target_id or not target_name:
        return
    member = await get_active_chat_member(message.bot, message.chat.id, target_id)
    if member is None:
        await safe_reply(message, "Не нашел этого пользователя среди активных участников чата.")
        return
    if member.status not in ADMIN_STATUSES and member_status_text(member.status) not in ADMIN_STATUS_TEXTS:
        await safe_reply(message, "Команда <code>затихни админ</code> нужна только для администраторов. Для обычных участников используй <code>затихни 10 - причина</code>.")
        return
    if member_status_text(member.status) == "creator":
        await safe_reply(message, "Владельца группы переводить в тихий режим нельзя.")
        return

    until_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    db.set_quiet_admin(
        chat_id=message.chat.id,
        user_id=member.user.id,
        username=member.user.username,
        full_name=member.user.full_name,
        reason=reason,
        until_at=until_at.isoformat(timespec="seconds"),
        created_by=message.from_user.id,
    )
    reason_line = f"\nПричина: {escape(reason)}" if reason else ""
    await safe_reply(
        message,
        f"{escape(target_name)} отправлен в тихий режим на <b>{minutes}</b> мин. "
        "Новые сообщения и реакции будут удаляться."
        f"{reason_line}",
    )


@router.message(F.text.regexp(re.compile(r"^(@[A-Za-z0-9_]{5,32}\s+)?затихни\s+\d+(\s+-\s+.*)?$", re.IGNORECASE)))
async def quiet_user(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return
    if not message.from_user:
        return
    actor_role = await actor_moderation_role(message.bot, message.chat.id, message.from_user.id)
    if actor_role is None:
        return
    if (
        actor_role == "admin"
        and not is_bot_admin(message.from_user.id)
        and not is_miniapp_admin_user(message.from_user.id)
        and not await has_chat_admin_permission(
            message.bot, message.chat.id, message.from_user.id, "can_restrict_members"
        )
    ):
        return

    await remember_sender(message)
    username, minutes, reason = parse_quiet_payload(message.text)
    if not minutes:
        await safe_reply(message, "Формат: ответом на сообщение <code>затихни 10 - причина</code> или <code>@username затихни 10 - причина</code>")
        return

    target_id, target_name, error = await resolve_command_target(message, username)
    if error:
        await safe_reply(message, error)
        return
    if not target_id or not target_name:
        return
    if await is_chat_admin(message.bot, message.chat.id, target_id):
        await safe_reply(message, "Администратора этой командой ограничивать нельзя.")
        return

    requested_minutes = minutes
    if actor_role == "admin":
        minutes = max(1, min(10080, minutes))
    else:
        role_limit = moderator_max_mute_minutes(actor_role)
        minutes = max(1, min(role_limit, minutes))
    until_date = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    try:
        await message.bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target_id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_audios=False,
                can_send_documents=False,
                can_send_photos=False,
                can_send_videos=False,
                can_send_video_notes=False,
                can_send_voice_notes=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
                can_react_to_messages=False,
            ),
            until_date=until_date,
            use_independent_chat_permissions=True,
        )
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        await safe_reply(
            message,
            "Не получилось ограничить пользователя. Проверь, что бот админ и может ограничивать участников.\n"
            f"<code>{escape(str(exc))}</code>",
        )
        return

    settings = db.get_quiet_settings(message.chat.id)
    cap_line = ""
    if actor_role != "admin" and requested_minutes > minutes:
        cap_line = f"\nЗапрошено {requested_minutes} мин, но лимит роли: <b>{minutes}</b> мин."
    await safe_reply(message, render_quiet_reply(settings.reply_text, target_name, minutes, reason) + cap_line)
    await send_quiet_media(message, settings.media_type, settings.media_file_id)
    db.add_moderator_action(message.chat.id, message.from_user.id, target_id, "mute", minutes, reason)
    reason_line = f"\nПричина: {escape(reason)}" if reason else ""
    await notify_staff_moderation(
        message.bot,
        (
            "🔇 <b>Мут</b>\n"
            f"Кто: {escape(render_moderation_actor(message, actor_role))}\n"
            f"Кому: {escape(target_name)}\n"
            f"Срок: <b>{minutes}</b> мин"
            f"{reason_line}"
        ),
    )
    since_at = (datetime.now(timezone.utc) - timedelta(hours=MODERATOR_MUTE_ALERT_WINDOW_HOURS)).isoformat(timespec="seconds")
    target_mutes = db.count_moderator_mutes_for_target(message.chat.id, target_id, since_at)
    if target_mutes >= MODERATOR_MUTE_ALERT_THRESHOLD:
        seniors = [
            f"@{row['username']}" if row["username"] else str(row["full_name"])
            for row in db.list_chat_moderators(message.chat.id)
            if str(row["role"]) == "senior"
        ]
        senior_line = "\nСтаршие: " + escape(", ".join(seniors[:10])) if seniors else ""
        await notify_staff_moderation(
            message.bot,
            (
                "🚨 <b>Нужна проверка админов/старших</b>\n"
                f"Пользователь {escape(target_name)} получил уже <b>{target_mutes}</b> мут(а) за последние "
                f"{MODERATOR_MUTE_ALERT_WINDOW_HOURS} ч."
                f"{senior_line}"
            ),
        )


@router.message(F.text.regexp(re.compile(r"^(@[A-Za-z0-9_]{5,32}\s+)?ударить\s+словар[её]м$", re.IGNORECASE)))
async def dictionary_hit_user(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return
    if not message.from_user:
        return

    actor_role = await actor_moderation_role(message.bot, message.chat.id, message.from_user.id)
    if actor_role is None:
        return
    if (
        actor_role == "admin"
        and not is_bot_admin(message.from_user.id)
        and not is_miniapp_admin_user(message.from_user.id)
        and not await has_chat_admin_permission(
            message.bot, message.chat.id, message.from_user.id, "can_restrict_members"
        )
    ):
        return

    await remember_sender(message)
    username = parse_dictionary_hit_payload(message.text)
    if username == "":
        await safe_reply(message, "Формат: ответом на сообщение <code>ударить словарём</code> или <code>@username ударить словарём</code>.")
        return

    target_id, target_name, error = await resolve_command_target(message, username)
    if error:
        await safe_reply(message, error)
        return
    if not target_id or not target_name:
        return
    if target_id == message.from_user.id:
        await safe_reply(message, "Словарём себя не бьём. Самообразование — добровольно.")
        return
    if await is_chat_admin(message.bot, message.chat.id, target_id):
        await safe_reply(message, "Администраторов словарём не бьём: у них броня из прав.")
        return

    until_date = datetime.now(timezone.utc) + timedelta(minutes=DICTIONARY_HIT_MUTE_MINUTES)
    try:
        await message.bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target_id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_audios=False,
                can_send_documents=False,
                can_send_photos=False,
                can_send_videos=False,
                can_send_video_notes=False,
                can_send_voice_notes=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
                can_react_to_messages=False,
            ),
            until_date=until_date,
            use_independent_chat_permissions=True,
        )
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        await safe_reply(
            message,
            "Не получилось ограничить пользователя. Проверь, что бот админ и может ограничивать участников.\n"
            f"<code>{escape(str(exc))}</code>",
        )
        return

    db.add_moderator_action(
        message.chat.id,
        message.from_user.id,
        target_id,
        "mute",
        DICTIONARY_HIT_MUTE_MINUTES,
        "удар словарём",
    )
    reply_to_message_id = (
        message.reply_to_message.message_id
        if username is None and message.reply_to_message
        else message.message_id
    )
    caption = f"Мут на <b>{DICTIONARY_HIT_MUTE_MINUTES}</b> мин."
    if DICTIONARY_HIT_PHOTO_PATH.exists():
        try:
            await message.bot.send_photo(
                chat_id=message.chat.id,
                photo=FSInputFile(DICTIONARY_HIT_PHOTO_PATH),
                caption=caption,
                reply_to_message_id=reply_to_message_id,
            )
        except TelegramRetryAfter as exc:
            await asyncio.sleep(int(getattr(exc, "retry_after", 3)) + 1)
            with suppress(TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter):
                await message.bot.send_photo(
                    chat_id=message.chat.id,
                    photo=FSInputFile(DICTIONARY_HIT_PHOTO_PATH),
                    caption=caption,
                    reply_to_message_id=reply_to_message_id,
                )
        except (TelegramBadRequest, TelegramForbiddenError):
            await safe_reply(message, caption)
    else:
        await safe_reply(message, caption)

    await notify_staff_moderation(
        message.bot,
        (
            "📚 <b>Удар словарём</b>\n"
            f"Кто: {escape(render_moderation_actor(message, actor_role))}\n"
            f"Кому: {escape(target_name)}\n"
            f"Срок: <b>{DICTIONARY_HIT_MUTE_MINUTES}</b> мин"
        ),
    )


@router.message(F.text.regexp(re.compile(r"^(@[A-Za-z0-9_]{5,32}\s+)?трещи$", re.IGNORECASE)))
async def unquiet_user(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return
    if not message.from_user:
        return
    actor_role = await actor_moderation_role(message.bot, message.chat.id, message.from_user.id)
    if actor_role is None:
        return
    if (
        actor_role == "admin"
        and not is_bot_admin(message.from_user.id)
        and not is_miniapp_admin_user(message.from_user.id)
        and not await has_chat_admin_permission(
            message.bot, message.chat.id, message.from_user.id, "can_restrict_members"
        )
    ):
        return

    await remember_sender(message)
    username = parse_unquiet_payload(message.text)
    if username == "":
        await safe_reply(message, "Формат: ответом на сообщение <code>трещи</code> или <code>@username трещи</code>")
        return

    target_id, target_name, error = await resolve_command_target(message, username)
    if error:
        await safe_reply(message, error)
        return
    if not target_id or not target_name:
        return

    active_mute = db.latest_active_moderator_mute(message.chat.id, target_id)
    if not moderator_can_unmute(actor_role, message.from_user.id, active_mute):
        await safe_reply(message, "Этой должностью можно снять только свой активный мут. Все муты снимает старший модератор или админ.")
        return

    quiet_admin_cleared = db.clear_quiet_admin(message.chat.id, target_id)
    if await is_chat_admin(message.bot, message.chat.id, target_id):
        await safe_reply(
            message,
            (
                f"{escape(target_name)} снова может трещать."
                if quiet_admin_cleared
                else f"{escape(target_name)} не был в тихом админ-режиме."
            ),
        )
        return

    try:
        await message.bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target_id,
            permissions=default_open_permissions(),
            use_independent_chat_permissions=True,
        )
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        await safe_reply(
            message,
            "Не получилось вернуть права пользователю. Проверь права бота на ограничение участников.\n"
            f"<code>{escape(str(exc))}</code>",
        )
        return

    suffix = " Тихий админ-режим тоже снят." if quiet_admin_cleared else ""
    await safe_reply(message, f"{escape(target_name)} снова может трещать.{suffix}")
    db.add_moderator_action(message.chat.id, message.from_user.id, target_id, "unmute", None, "")
    await notify_staff_moderation(
        message.bot,
        (
            "🔊 <b>Мут снят</b>\n"
            f"Кто: {escape(render_moderation_actor(message, actor_role))}\n"
            f"Кому: {escape(target_name)}"
        ),
    )


@router.message(F.text.casefold() == "в цитаты")
async def add_quote(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES or not message.reply_to_message:
        return

    await remember_sender(message)
    source = message.reply_to_message
    quote_text = source.html_text or getattr(source, "html_caption", None) or source.text or source.caption
    if not quote_text:
        await safe_reply(message, "В цитату можно добавить только текстовое сообщение.")
        return

    author = source.from_user.full_name if source.from_user else None
    db.add_quote(message.chat.id, quote_text, author, message.from_user.id if message.from_user else None)
    await safe_reply(message, "Цитата сохранена.")


@router.message(F.text.casefold() == "цитата")
async def random_quote(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return

    await remember_sender(message)
    quote = db.random_quote(message.chat.id)
    if quote is None:
        await safe_reply(message, "Цитат пока нет. Ответь на сообщение фразой: в цитаты")
        return

    author = f"\n\n— {escape(quote.author_name)}" if quote.author_name else ""
    await safe_reply(message, f"<b>Цитата #{quote.id}</b>\n{quote.text}{author}")


@router.message(F.text.casefold() == "все цитаты")
async def all_quotes(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return

    await remember_sender(message)
    quotes = db.list_quotes(message.chat.id)
    if not quotes:
        await safe_reply(message, "Цитат пока нет. Ответь на сообщение фразой: в цитаты")
        return

    lines = [f"<b>Все цитаты:</b> {len(quotes)}"]
    for index, quote in enumerate(quotes, start=1):
        author = f" — {escape(quote.author_name)}" if quote.author_name else ""
        lines.append(f"{index}. {preview_html(quote.text, limit=180)}{author}")

    await safe_reply_chunks(message, lines, disable_web_page_preview=True)


@router.message(F.text.regexp(re.compile(r"^цитата\s+\d+$", re.IGNORECASE)))
async def quote_by_number(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return

    await remember_sender(message)
    match = re.search(r"\d+", message.text or "")
    if not match:
        return

    index = int(match.group(0))
    quotes = db.list_quotes(message.chat.id)
    if index < 1 or index > len(quotes):
        await safe_reply(message, f"Цитаты с номером {index} нет. Напиши <code>все цитаты</code>, чтобы увидеть список.")
        return

    quote = quotes[index - 1]
    author = f"\n\n— {escape(quote.author_name)}" if quote.author_name else ""
    await safe_reply(message, f"<b>Цитата №{index}</b>\n{quote.text}{author}")


@router.message(F.text.regexp(re.compile(r"^удалить\s+цитату\s+\d+$", re.IGNORECASE)))
async def delete_quote(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return
    if not message.from_user or not is_bot_admin(message.from_user.id):
        return

    await remember_sender(message)
    match = re.search(r"\d+", message.text or "")
    if not match:
        return

    index = int(match.group(0))
    quotes = db.list_quotes(message.chat.id)
    if index < 1 or index > len(quotes):
        await safe_reply(message, f"Цитаты с номером {index} нет. Напиши <code>все цитаты</code>, чтобы увидеть список.")
        return

    quote = quotes[index - 1]
    deleted = db.delete_quote(message.chat.id, quote.id)
    if not deleted:
        await safe_reply(message, "Не получилось удалить цитату: она уже удалена.")
        return

    await safe_reply(message, f"Удалена цитата №{index}.")


@router.message(F.text.regexp(re.compile(r"^опрос\s+.+", re.IGNORECASE)))
async def quick_poll(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return

    parsed = parse_poll_payload(message.text)
    if not parsed:
        await safe_reply(message, "Формат: <code>опрос Вопрос | вариант 1 | вариант 2</code>")
        return

    question, options = parsed
    await message.answer_poll(question=question, options=options, is_anonymous=False)


@router.message(F.text.regexp(re.compile(r"^др\s+.+", re.IGNORECASE)))
async def add_birthday(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return

    parsed = parse_birthday_payload(message.text)
    if not parsed:
        await safe_reply(message, "Формат: <code>др 31.12 Имя или событие</code>")
        return

    day, month, label = parsed
    db.add_birthday(message.chat.id, day, month, label, message.from_user.id if message.from_user else None)
    await safe_reply(message, f"Дата добавлена: <b>{day:02d}.{month:02d}</b> — {escape(label)}")


@router.message(F.text.regexp(re.compile(r"^(дни рождения|список др)$", re.IGNORECASE)))
async def list_birthdays(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return

    birthdays = db.list_birthdays(message.chat.id)
    if not birthdays:
        await safe_reply(message, "Даты пока не добавлены. Формат: др 31.12 Имя")
        return

    lines = ["<b>Дни рождения и события:</b>"]
    for item in birthdays[:50]:
        lines.append(f"{item.day:02d}.{item.month:02d} — {escape(item.text)}")
    await safe_reply(message, "\n".join(lines))


@router.message(F.text.regexp(re.compile(r"^запрет\s+.+", re.IGNORECASE)))
async def add_blacklist_word(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return
    if not await require_admin(message):
        return

    word = split_command_payload(message.text)
    db.add_blacklist_word(message.chat.id, word, message.from_user.id if message.from_user else None)
    invalidate_chat_runtime_cache(message.chat.id)
    await safe_reply(message, f"Слово добавлено в черный список: <b>{escape(normalize_trigger(word))}</b>")


@router.message(F.text.regexp(re.compile(r"^разрешить\s+.+", re.IGNORECASE)))
async def delete_blacklist_word(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return
    if not await require_admin(message):
        return

    word = split_command_payload(message.text)
    deleted = db.delete_blacklist_word(message.chat.id, word)
    invalidate_chat_runtime_cache(message.chat.id)
    await safe_reply(message, "Слово удалено из черного списка." if deleted else "Такого слова в черном списке нет.")


@router.message(F.text.casefold() == "черный список")
async def list_blacklist_words(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return
    if not await require_admin(message):
        return

    words = db.list_blacklist_words(message.chat.id)
    if not words:
        await safe_reply(message, "Черный список пуст.")
        return

    lines = ["<b>Черный список:</b>"]
    lines.extend(f"{index}. {escape(item.word)}" for index, item in enumerate(words, start=1))
    await safe_reply(message, "\n".join(lines))


@router.message(F.text.regexp(re.compile(r"^погода\s+.+", re.IGNORECASE)))
async def weather(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return

    await remember_sender(message)
    request = parse_weather_request(message.text)
    if not request:
        return
    city, period = request

    try:
        forecast = await fetch_weather(city, period)
    except Exception:
        await safe_reply(message, "Не получилось получить погоду. Проверь название города и попробуй еще раз.")
        return

    await safe_reply(message, forecast, disable_web_page_preview=True)


async def handle_auto_reply(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return

    if message.text and message.text.startswith("/") and not ALARM_TOPIC_COMMAND_RE.fullmatch(message.text):
        await remember_sender(message)
        return

    text = message.text or message.caption
    if not text:
        return

    await remember_sender(message)
    await handle_birthdays(message)

    if await handle_alarm_mode(message):
        return

    if message.text and await handle_day_pick(message):
        return

    answers = []
    normalized_text = normalize_trigger(text)
    if not auto_trigger_was_sent(message):
        trigger_answers = [
            item
            for item in cached_triggers(message.chat.id)
            if trigger_item_matches(normalized_text, item)
        ]
        if trigger_answers:
            answers.append(random.choice(trigger_answers))
            mark_auto_trigger_sent(message)

    mentions = extract_mentions(text)
    if mentions:
        replies = cached_replies_map(message.chat.id)
        answers.extend(replies[normalize_username(username)] for username in mentions if normalize_username(username) in replies)

    if not answers:
        return

    for item in answers:
        await send_auto_reply_item(message, item)


def advertisement_due(advertisement, now: datetime) -> bool:
    if not advertisement.enabled:
        return False
    if not advertisement.first_sent_at and advertisement.scheduled_at:
        try:
            scheduled_at = datetime.fromisoformat(advertisement.scheduled_at)
            if scheduled_at.tzinfo is None:
                scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
            if now < scheduled_at.astimezone(now.tzinfo):
                return False
        except ValueError:
            return False
    if advertisement.duration_type == "once" and advertisement.last_sent_at:
        return False
    if advertisement.duration_type == "day" and advertisement.first_sent_at:
        try:
            first_sent = datetime.fromisoformat(advertisement.first_sent_at)
            if first_sent.tzinfo is None:
                first_sent = first_sent.replace(tzinfo=timezone.utc)
            if (now - first_sent.astimezone(now.tzinfo)).total_seconds() >= 24 * 60 * 60:
                return False
        except ValueError:
            pass
    if not advertisement.last_sent_at:
        return True
    try:
        last_sent = datetime.fromisoformat(advertisement.last_sent_at)
        if last_sent.tzinfo is None:
            last_sent = last_sent.replace(tzinfo=timezone.utc)
        last_sent = last_sent.astimezone(now.tzinfo)
    except ValueError:
        return True
    return (now - last_sent).total_seconds() >= max(1, advertisement.interval_minutes) * 60


async def advertisement_loop(bot: Bot) -> None:
    while True:
        now = datetime.now().astimezone()
        for chat in db.list_chats():
            ads = db.list_advertisements(chat.chat_id)
            for ad in ads:
                if not advertisement_due(ad, now):
                    continue
                try:
                    thread_kwargs = {"message_thread_id": ad.topic_thread_id} if ad.topic_thread_id else {}
                    attachments = db.list_advertisement_attachments(ad.id)
                    if attachments:
                        caption = ad.text if len(ad.text) <= 1024 else None
                        media = [
                            (
                                InputMediaPhoto(media=item.file_id, caption=caption if position == 0 else None, parse_mode=None)
                                if item.media_type == "photo"
                                else InputMediaVideo(media=item.file_id, caption=caption if position == 0 else None, parse_mode=None)
                            )
                            for position, item in enumerate(attachments)
                        ]
                        if len(media) == 1:
                            item = attachments[0]
                            if item.media_type == "photo":
                                await bot.send_photo(chat.chat_id, item.file_id, caption=caption, parse_mode=None, **thread_kwargs)
                            else:
                                await bot.send_video(chat.chat_id, item.file_id, caption=caption, parse_mode=None, **thread_kwargs)
                        else:
                            await bot.send_media_group(chat.chat_id, media=media, **thread_kwargs)
                        if caption is None:
                            await bot.send_message(chat.chat_id, ad.text, parse_mode=None, disable_web_page_preview=False, **thread_kwargs)
                    else:
                        await bot.send_message(chat.chat_id, ad.text, parse_mode=None, disable_web_page_preview=False, **thread_kwargs)
                    db.mark_advertisement_sent(ad.id, now.isoformat(timespec="seconds"))
                except Exception as exc:
                    db.mark_advertisement_failed(ad.id, str(exc))
                    logging.exception("Advertisement %s send failed for chat %s: %s", ad.id, chat.chat_id, exc)
        await asyncio.sleep(30)


@router.message(F.chat.type == "private")
async def private_fallback(message: Message) -> None:
    await message.answer(
        "Выбери группу и действие кнопками.",
        reply_markup=await main_menu_for_user(message.bot, message.from_user.id if message.from_user else None),
    )


@router.message(F.text | F.caption)
async def auto_reply_message(message: Message) -> None:
    await handle_auto_reply(message)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = load_config()

    global db
    global BOT_ADMIN_IDS
    global ALERTS_API_TOKEN
    global staff_service
    global premium_service
    BOT_ADMIN_IDS = config.bot_admin_ids
    ALERTS_API_TOKEN = config.alerts_api_token
    db = Database(config.db_path)
    db.init()
    premium_service = PremiumService(config.db_path)
    staff_service = StaffService(config.db_path, config.owner_id)
    configure_staff(staff_service)
    awarded = backfill_dig_achievements()
    if awarded:
        logging.info("Backfilled dig achievements: %s", awarded)

    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher()
    staff_router.message.middleware(StaffTopicMiddleware())
    router.message.middleware(DropStaleMessagesMiddleware())
    router.message.middleware(StaffTopicMiddleware())
    router.message.middleware(AuditAdminStateMiddleware())
    router.message.middleware(QuietAdminMiddleware())
    router.message.middleware(ChatLockMiddleware())
    router.message.middleware(AlarmRestrictedMessageMiddleware())
    router.message.middleware(BlacklistMiddleware())
    router.callback_query.middleware(StaleCallbackQueryMiddleware())
    router.callback_query.middleware(AuditCallbackMiddleware())
    dispatcher.include_router(staff_router)
    dispatcher.include_router(router)
    dispatcher.errors.register(staff_error_handler)

    try:
        await configure_miniapp_menu_button(bot)
        await bot.get_me()
        if staff_service.chat_id is not None:
            # Startup is not an owner-authorized binding action. Never rewrite
            # staff routing from the general topic cache here.
            missing_topics = staff_service.missing_topics()
            for topic in missing_topics:
                await staff_service.log(bot, "WARNING", f"Staff-тема не найдена: {topic}")
        await staff_service.send(bot, "status", "🟢 Бот запущен")
        await send_restart_panel_if_needed(bot)
        advertisement_task = asyncio.create_task(advertisement_loop(bot))
        alerts_task = asyncio.create_task(alerts_monitor_loop(bot))
        await dispatcher.start_polling(
            bot,
            allowed_updates=["message", "callback_query", "message_reaction", "pre_checkout_query", "my_chat_member"],
        )
    except TelegramNotFound as exc:
        raise RuntimeError("Telegram rejected BOT_TOKEN. Check .env and paste the real token from BotFather.") from exc
    finally:
        if "advertisement_task" in locals():
            advertisement_task.cancel()
            with suppress(asyncio.CancelledError):
                await advertisement_task
        if "alerts_task" in locals():
            alerts_task.cancel()
            with suppress(asyncio.CancelledError):
                await alerts_task
        if staff_service:
            await staff_service.send(bot, "status", "🔴 Бот остановлен")
        await bot.session.close()
        if staff_service:
            staff_service.close()
        premium_service.close()
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
