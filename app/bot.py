import asyncio
import logging
import os
import random
import re
import sys
from datetime import datetime, timezone
from datetime import timedelta
from html import escape, unescape
from urllib.parse import quote

import aiohttp
from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatMemberStatus, ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNotFound, TelegramRetryAfter
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Chat, ChatPermissions, LabeledPrice, Message, PreCheckoutQuery

from .config import load_config
from .db import Database, RegisteredChat, normalize_trigger, normalize_username
from .keyboards import (
    TRIGGERS_PAGE_SIZE,
    alarm_menu,
    back_to_chat_menu,
    chat_admin_menu,
    chat_select_menu,
    feedback_reply_menu,
    leave_confirm_menu,
    main_menu,
    paid_chat_select_menu,
    quiet_menu,
    restart_confirm_menu,
    stars_menu,
    topic_select_menu,
    trigger_list_menu,
)


MENTION_RE = re.compile(r"(?<![\w@])@([A-Za-z0-9_]{5,32})")
ADMIN_STATUSES = {ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR}
ADMIN_STATUS_TEXTS = {"creator", "administrator"}
SUPPORTED_CHAT_TYPES = {"group", "supergroup"}
DAY_PICK_KEY = "day_pick"
DAY_QUERY_TEXT = "кто пидор"
DAY_REPLY_TEMPLATE = "Пидор дня: {user}"
WEATHER_RE = re.compile(r"^погода\s+(.+)$", re.IGNORECASE)
ALARM_ON_RE = re.compile(r"(?<!\w)тревога(?!\w)", re.IGNORECASE)
ALARM_OFF_RE = re.compile(r"(?<!\w)отбой(?!\w)", re.IGNORECASE)
GIVEAWAY_TOP_RE = re.compile(r"^топ\s+пидоров[?!.]?$", re.IGNORECASE)
DEFAULT_AVAILABLE_REACTIONS = [
    {"type": "emoji", "emoji": emoji}
    for emoji in ["👍", "👎", "❤", "🔥", "🥰", "👏", "😁", "🤔", "🤯", "😱", "🤬", "😢", "🎉", "🤩", "🤮", "💩"]
]

router = Router()
db: Database
BOT_ADMIN_IDS: set[int] = set()
OPENAI_API_KEY: str | None = None
OPENAI_MODEL = "gpt-4.1-mini"
BOT_STARTED_AT = datetime.now(timezone.utc)
LOCK_HANDLE = None


class DropStaleMessagesMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, Message) and event.date < BOT_STARTED_AT:
            return None
        return await handler(event, data)


class AdminInput(StatesGroup):
    set_reply = State()
    del_reply = State()
    set_trigger = State()
    del_trigger = State()
    send_message = State()
    set_giveaway = State()
    set_alarm_text = State()
    set_clear_text = State()
    paid_message = State()
    feedback = State()
    set_roll_mute = State()
    set_quiet_text = State()
    set_quiet_media = State()
    feedback_reply = State()


def chat_title(chat: Chat) -> str:
    return chat.title or chat.full_name or chat.username or str(chat.id)


def extract_mentions(text: str | None) -> set[str]:
    if not text:
        return set()
    return {normalize_username(match.group(1)) for match in MENTION_RE.finditer(text)}


def has_trigger(text: str, trigger: str) -> bool:
    normalized_text = normalize_trigger(text)
    normalized_trigger = normalize_trigger(trigger)
    if not normalized_text or not normalized_trigger:
        return False

    pattern = rf"(?<!\w){re.escape(normalized_trigger)}(?!\w)"
    return re.search(pattern, normalized_text, flags=re.IGNORECASE) is not None


def split_command_payload(text: str | None) -> str:
    if not text:
        return ""
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def message_html_text(message: Message) -> str:
    return (message.html_text or message.text or "").strip()


def strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value)


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


def split_trigger_payload(payload: str) -> tuple[str, str]:
    trigger, sep, reply_text = payload.partition(" - ")
    if not sep:
        return "", ""
    return trigger.strip(), reply_text.strip()


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


def parse_unquiet_payload(text: str | None) -> str | None:
    if not text:
        return None
    parts = text.strip().split()
    if len(parts) == 1 and parts[0].casefold() == "трещи":
        return None
    if len(parts) == 2 and parts[0].startswith("@") and parts[1].casefold() == "трещи":
        return normalize_username(parts[0])
    return ""


def extract_ai_prompt(text: str | None) -> str | None:
    if not text:
        return None
    stripped = text.strip()
    lowered = stripped.casefold()
    prefixes = ["бот, ", "бот "]
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return stripped[len(prefix) :].strip() or None
    return None


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


def weather_description(code: int | None) -> str:
    if code is None:
        return "Нет данных"
    return WEATHER_CODES.get(code, f"Код погоды {code}")


async def fetch_weather(city: str, period: str) -> str:
    timeout = aiohttp.ClientTimeout(total=8)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        geocode_url = (
            "https://geocoding-api.open-meteo.com/v1/search"
            f"?name={quote(city)}&count=1&language=ru&format=json"
        )
        async with session.get(geocode_url, headers={"User-Agent": "telegram-autoreply-bot"}) as response:
            if response.status != 200:
                raise RuntimeError(f"geocoding service returned {response.status}")
            data = await response.json(content_type=None)

        results = data.get("results") or []
        if not results:
            raise RuntimeError("city not found")

        place = results[0]
        latitude = place["latitude"]
        longitude = place["longitude"]
        location = place.get("name", city)
        country = place.get("country")
        admin = place.get("admin1")
        if admin and admin != location:
            location = f"{location}, {admin}"
        if country:
            location = f"{location}, {country}"

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


async def fetch_ai_answer(prompt: str) -> str:
    if not OPENAI_API_KEY:
        return "AI-ответчик не настроен. Добавь OPENAI_API_KEY в .env."

    timeout = aiohttp.ClientTimeout(total=20)
    payload = {
        "model": OPENAI_MODEL,
        "input": [
            {
                "role": "system",
                "content": "Отвечай кратко, по-русски, в стиле дружелюбного Telegram-бота для группового чата.",
            },
            {"role": "user", "content": prompt},
        ],
        "max_output_tokens": 300,
    }
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post("https://api.openai.com/v1/responses", json=payload, headers=headers) as response:
            data = await response.json(content_type=None)
            if response.status >= 400:
                raise RuntimeError(data.get("error", {}).get("message", "OpenAI API error"))

    if data.get("output_text"):
        return str(data["output_text"]).strip()

    chunks: list[str] = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                chunks.append(content["text"])
    return "\n".join(chunks).strip() or "AI не вернул текстовый ответ."


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


async def raw_chat_available_reactions(bot: Bot, chat_id: int) -> list | None:
    result = await telegram_api_call(bot, "getChat", {"chat_id": chat_id})
    return result.get("available_reactions")


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
    try:
        await callback.message.edit_text(text, **kwargs)
    except TelegramBadRequest as exc:
        error = str(exc).lower()
        if "message is not modified" in error:
            return
        if "can't parse entities" in error:
            await callback.message.edit_text(escape(unescape(strip_html(text))), **kwargs)
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


async def restart_process(delay_seconds: float = 1.0) -> None:
    await asyncio.sleep(delay_seconds)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)
    os.execv(sys.executable, [sys.executable, "-m", "app.bot"])


def acquire_single_instance_lock() -> None:
    global LOCK_HANDLE

    import msvcrt

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    lock_path = os.path.join(project_root, "bot.lock")
    LOCK_HANDLE = open(lock_path, "w", encoding="utf-8")
    try:
        msvcrt.locking(LOCK_HANDLE.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError as exc:
        raise RuntimeError(
            "Bot is already running. Close the other PowerShell window or stop the previous bot process first."
        ) from exc
    LOCK_HANDLE.write(str(os.getpid()))
    LOCK_HANDLE.flush()


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


def is_bot_admin(user_id: int | None) -> bool:
    return user_id is not None and user_id in BOT_ADMIN_IDS


async def admin_chats_for_user(bot: Bot, user_id: int) -> list[RegisteredChat]:
    if is_bot_admin(user_id):
        return db.list_chats()

    chats: list[RegisteredChat] = []
    for chat in db.list_chats():
        if await is_chat_admin(bot, chat.chat_id, user_id):
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

    if not await is_chat_admin(message.bot, message.chat.id, message.from_user.id):
        await message.answer("Настройки может менять только администрация этого чата.")
        return False

    return True


async def require_selected_admin(callback: CallbackQuery, chat_id: int) -> RegisteredChat | None:
    chat = db.get_chat(chat_id)
    if chat is None:
        await callback.answer("Группа не найдена. Сначала зарегистрируйте ее.", show_alert=True)
        return None

    if not is_bot_admin(callback.from_user.id) and not await is_chat_admin(callback.bot, chat_id, callback.from_user.id):
        await callback.answer("Ты не админ в этой группе.", show_alert=True)
        return None

    return chat


async def require_state_admin(message: Message, state: FSMContext) -> int | None:
    data = await state.get_data()
    chat_id = data.get("chat_id")
    if not isinstance(chat_id, int):
        await state.clear()
        await message.answer("Группа не выбрана. Открой /start и выбери группу.", reply_markup=main_menu())
        return None

    if not message.from_user or (
        not is_bot_admin(message.from_user.id)
        and not await is_chat_admin(message.bot, chat_id, message.from_user.id)
    ):
        await state.clear()
        await message.answer("Настройка отменена: у тебя нет прав администратора в выбранной группе.")
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

    await register_current_chat(message)
    db.upsert_seen_user(
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        is_bot=message.from_user.is_bot,
    )

    thread_id = message.message_thread_id
    is_real_topic = bool(getattr(message.chat, "is_forum", False) and getattr(message, "is_topic_message", False))
    if thread_id is not None and is_real_topic:
        topic_name = "Тема"
        if message.reply_to_message and message.reply_to_message.forum_topic_created:
            topic_name = message.reply_to_message.forum_topic_created.name
        elif message.forum_topic_created:
            topic_name = message.forum_topic_created.name
        db.upsert_topic(message.chat.id, thread_id, f"{topic_name} #{thread_id}")


def replies_text(chat_id: int) -> str:
    replies = db.list_replies(chat_id)
    triggers = db.list_triggers(chat_id)
    lines = ["<b>Настроенные ответы:</b>"]
    if not replies and not triggers:
        lines.append("Пока ничего не настроено.")

    if replies:
        lines.append("\n<b>Ответы на @username:</b>")
        for item in replies:
            lines.append(f"@{escape(item.username)} - {preview_html(item.text)}")

    if triggers:
        lines.append("\n<b>Фиксированные ответы:</b>")
        for item in triggers:
            lines.append(f"{escape(item.trigger)} - {preview_html(item.text)}")

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
            lines.append(f"{offset}. <b>{escape(item.trigger)}</b> - {preview_html(item.text)}")

    return "\n".join(lines), page, total


@router.message(CommandStart())
async def start(message: Message) -> None:
    if message.chat.type == "private":
        await message.answer(
            "Панель управления ботом. Выбери группу, где ты админ, и настраивай ответы кнопками.",
            reply_markup=main_menu(),
        )
        return

    await remember_sender(message)
    await message.answer(
        "Группа зарегистрирована. Настройки теперь удобнее делать в личке со мной через /start."
    )


@router.message(Command("settings"))
async def settings(message: Message) -> None:
    if message.chat.type == "private":
        await show_chat_select(message)
        return

    await remember_sender(message)
    await message.answer("Открой личку с ботом и нажми /start, чтобы настроить эту группу кнопками.")


@router.message(Command("id"))
async def show_user_id(message: Message) -> None:
    if not message.from_user:
        await message.answer("Не могу определить твой Telegram id.")
        return

    await message.answer(f"Твой Telegram id: <code>{message.from_user.id}</code>")


@router.message(F.text.casefold() == "/старт")
async def start_ru(message: Message) -> None:
    await start(message)


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
            "Нет доступных групп. Добавь бота в группу, отправь там /register_chat и убедись, что ты админ этой группы.",
            reply_markup=main_menu(),
        )
        return

    await message.answer("Выбери группу для настройки:", reply_markup=chat_select_menu(chats))


@router.callback_query(F.data == "ui:home")
async def cb_home(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_edit(callback, "Панель управления ботом.", reply_markup=main_menu())
    await callback.answer()


@router.callback_query(F.data == "ui:chats")
async def cb_chats(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    chats = await admin_chats_for_user(callback.bot, callback.from_user.id)
    if not chats:
        await safe_edit(
            callback,
            "Нет доступных групп. Добавь бота в группу, отправь там /register_chat и убедись, что ты админ этой группы.",
            reply_markup=main_menu(),
        )
        await callback.answer()
        return

    await safe_edit(callback, "Выбери группу для настройки:", reply_markup=chat_select_menu(chats))
    await callback.answer()


@router.callback_query(F.data == "ui:help")
async def cb_help(callback: CallbackQuery) -> None:
    await safe_edit(
        callback,
        "Как пользоваться:\n"
        "1. Добавь бота в группу или чат обсуждений.\n"
        "2. Один раз отправь в группе /register_chat.\n"
        "3. Вернись сюда, выбери группу кнопкой и настраивай ответы.\n\n"
        "В группе бот отвечает на упоминания @username, фиксированные слова и фразу 'кто пидор'.",
        reply_markup=main_menu(),
    )
    await callback.answer()


@router.callback_query(F.data == "ui:clear_chat")
async def cb_clear_chat(callback: CallbackQuery, state: FSMContext) -> None:
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
        reply_markup=main_menu(),
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
        await safe_edit(callback, "Нет доступных групп, где ты админ.", reply_markup=main_menu())
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

    await safe_edit(callback, "\n".join(lines), reply_markup=main_menu())
    await callback.answer()


@router.callback_query(F.data == "ui:whoami")
async def cb_whoami(callback: CallbackQuery) -> None:
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

    await safe_edit(callback, "\n".join(lines), reply_markup=main_menu())
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
    chats = db.list_chats()
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
                f"{payment.id}. {escape(username)} - <b>{payment.amount} ⭐</b> "
                f"в {escape(chat_title_text)} · {escape(payment.created_at)}"
            )

    await safe_edit(callback, "\n".join(lines), reply_markup=stars_menu())
    await callback.answer()


@router.callback_query(F.data.startswith("chat:"))
async def cb_select_chat(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    chat_id = int(callback.data.split(":", 1)[1])
    chat = await require_selected_admin(callback, chat_id)
    if chat is None:
        return

    await safe_edit(
        callback,
        f"Выбрана группа: <b>{mention_chat(chat)}</b>\nЧто настроим?",
        reply_markup=chat_admin_menu(chat_id),
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

    text, page, total = trigger_page_text(chat_id, page)
    await safe_edit(callback, text, reply_markup=trigger_list_menu(chat_id, page, total))
    await callback.answer()


@router.callback_query(F.data.startswith("act:"))
async def cb_action(callback: CallbackQuery, state: FSMContext) -> None:
    _, action, chat_id_raw = callback.data.split(":", 2)
    chat_id = int(chat_id_raw)
    chat = await require_selected_admin(callback, chat_id)
    if chat is None:
        return

    if action == "set_reply":
        await state.set_state(AdminInput.set_reply)
        await state.update_data(chat_id=chat_id)
        await safe_edit(
            callback,
            f"Группа: <b>{mention_chat(chat)}</b>\n\n"
            "Отправь автоответ в формате:\n"
            "<code>@username текст ответа</code>",
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
            "<code>слово - текст ответа</code>",
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
        users = db.list_pickable_users(chat_id)
        await safe_edit(
            callback,
            f"Бот запомнил участников с @username для розыгрышей: <b>{len(users)}</b>.\n\n"
            "В список попадают только те, кто уже писал в этой группе после запуска бота.",
            reply_markup=back_to_chat_menu(chat_id),
        )
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
            f"Текст тревоги: {preview_html(settings.alarm_text or 'Тревога включена: медиа и реакции отключены.')}\n"
            f"Текст отбоя: {preview_html(settings.clear_text or 'Отбой: медиа и реакции снова включены.')}",
            reply_markup=alarm_menu(chat_id, bool(settings.enabled)),
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
        if not is_bot_admin(callback.from_user.id):
            await callback.answer("Настройка доступна только администратору бота.", show_alert=True)
            return

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
        reply_markup=main_menu(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("alarm:"))
async def cb_alarm(callback: CallbackQuery, state: FSMContext) -> None:
    _, action, chat_id_raw = callback.data.split(":", 2)
    chat_id = int(chat_id_raw)
    chat = await require_selected_admin(callback, chat_id)
    if chat is None:
        return

    settings = db.get_alarm_settings(chat_id)
    if action == "toggle":
        enabled = not bool(settings.enabled)
        db.set_alarm_enabled(chat_id, enabled, callback.from_user.id)
        settings = db.get_alarm_settings(chat_id)
        await safe_edit(
            callback,
            f"Группа: <b>{mention_chat(chat)}</b>\n\n"
            f"Режим тревоги: <b>{'включен' if settings.enabled else 'выключен'}</b>\n\n"
            f"Текст тревоги: {preview_html(settings.alarm_text or 'Тревога включена: медиа и реакции отключены.')}\n"
            f"Текст отбоя: {preview_html(settings.clear_text or 'Отбой: медиа и реакции снова включены.')}",
            reply_markup=alarm_menu(chat_id, bool(settings.enabled)),
        )
    elif action == "text_on":
        await state.set_state(AdminInput.set_alarm_text)
        await state.update_data(chat_id=chat_id)
        await safe_edit(
            callback,
            f"Группа: <b>{mention_chat(chat)}</b>\n\n"
            "Отправь текст оповещения для слова <code>тревога</code>.",
            reply_markup=back_to_chat_menu(chat_id),
        )
    elif action == "text_off":
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
    if not is_bot_admin(callback.from_user.id):
        await callback.answer("Настройка доступна только администратору бота.", show_alert=True)
        return

    if action == "text":
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
        await state.set_state(AdminInput.set_quiet_media)
        await state.update_data(chat_id=chat_id)
        await safe_edit(
            callback,
            f"Группа: <b>{mention_chat(chat)}</b>\n\n"
            "Отправь сюда гиф, голосовое или аудио. Бот сохранит его и будет отправлять после команды затихни.",
            reply_markup=back_to_chat_menu(chat_id),
        )
    elif action == "clear_media":
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
    target = "основной чат" if thread_id == 0 else f"тему #{thread_id}"
    await safe_edit(
        callback,
        f"Группа: <b>{mention_chat(chat)}</b>\n"
        f"Цель: <b>{escape(target)}</b>\n\n"
        "Отправь текст или стикер, который бот должен написать.",
        reply_markup=back_to_chat_menu(chat_id),
    )
    await callback.answer()


@router.message(AdminInput.set_reply, F.chat.type == "private")
async def ui_set_reply(message: Message, state: FSMContext) -> None:
    chat_id = await require_state_admin(message, state)
    if chat_id is None:
        return

    payload = message_html_text(message)
    username, sep, reply_text = payload.partition(" ")
    if not username.startswith("@") or not sep or not reply_text.strip():
        await message.answer("Формат: <code>@username текст ответа</code>")
        return

    db.set_reply(chat_id, username, reply_text, message.from_user.id if message.from_user else None)
    await state.clear()
    await message.answer(
        f"Готово. Автоответ для <b>@{escape(normalize_username(username))}</b> сохранен.",
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

    payload = message_html_text(message)
    trigger, reply_text = split_trigger_payload(payload)
    if not trigger or not reply_text:
        await message.answer("Формат: <code>слово - текст ответа</code>")
        return

    db.set_trigger(chat_id, trigger, reply_text, message.from_user.id if message.from_user else None)
    await state.clear()
    await message.answer(
        f"Фиксированный ответ на <b>{escape(normalize_trigger(trigger))}</b> сохранен.",
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
    await state.clear()
    text, page, total = trigger_page_text(chat_id, (index - 1) // TRIGGERS_PAGE_SIZE)
    result = f"Удалено слово №{index}: <b>{escape(trigger)}</b>" if deleted else "Такой фиксированный ответ не найден."
    await message.answer(f"{result}\n\n{text}", reply_markup=trigger_list_menu(chat_id, page, total))


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
        reply_markup=alarm_menu(chat_id, bool(settings.enabled)),
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
        reply_markup=alarm_menu(chat_id, bool(settings.enabled)),
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


@router.message(AdminInput.paid_message, F.chat.type == "private")
async def ui_paid_message(message: Message, state: FSMContext) -> None:
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

    await state.update_data(paid_text=text)
    payload = f"paid_message:{message.from_user.id if message.from_user else 0}:{chat_id}"
    await message.bot.send_invoice(
        chat_id=message.chat.id,
        title="Сообщение за звезды",
        description=f"Публикация сообщения в группе {chat.title}",
        payload=payload,
        currency="XTR",
        prices=[LabeledPrice(label="Публикация сообщения", amount=1)],
        provider_token="",
    )


@router.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_paid_message(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    chat_id = data.get("chat_id")
    text = data.get("paid_text")
    if not isinstance(chat_id, int) or not isinstance(text, str):
        await message.answer("Оплата прошла, но сообщение не найдено. Напиши администратору бота.")
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

    payment = message.successful_payment
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


async def handle_alarm_mode(message: Message) -> bool:
    if not message.text:
        return False

    settings = db.get_alarm_settings(message.chat.id)
    if not settings.enabled:
        return False

    is_admin_message = bool(
        message.from_user and await is_chat_admin(message.bot, message.chat.id, message.from_user.id)
    )
    is_linked_channel_message = bool(
        getattr(message, "is_automatic_forward", False)
        or (message.sender_chat and message.sender_chat.type == "channel")
    )
    if not is_admin_message and not is_linked_channel_message:
        return False

    if ALARM_ON_RE.search(message.text):
        reaction_warning = ""
        try:
            if not settings.permissions_json:
                chat = await message.bot.get_chat(message.chat.id)
                db.save_alarm_permissions(message.chat.id, permissions_to_dict(getattr(chat, "permissions", None)))

            await message.bot.set_chat_permissions(
                chat_id=message.chat.id,
                permissions=media_locked_permissions(),
                use_independent_chat_permissions=True,
            )
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            await safe_reply(
                message,
                "Не получилось включить тревогу. Проверь, что бот админ и у него есть право ограничивать участников.\n"
                f"<code>{escape(str(exc))}</code>"
            )
            return True

        try:
            if settings.reactions_json is None:
                current_reactions = await raw_chat_available_reactions(message.bot, message.chat.id)
                if current_reactions is not None:
                    db.save_alarm_reactions(message.chat.id, current_reactions)
            await set_chat_available_reactions(message.bot, message.chat.id, [])
        except (TelegramBadRequest, TelegramForbiddenError):
            reaction_warning = "\n\nРеакции не удалось отключить. Проверь, что бот админ с правом менять настройки группы."

        await safe_reply(message, (settings.alarm_text or "Тревога включена: медиа и реакции отключены.") + reaction_warning)
        return True

    if ALARM_OFF_RE.search(message.text):
        reaction_warning = ""
        try:
            saved = db.pop_alarm_permissions(message.chat.id)
            permissions = ChatPermissions(**saved) if saved else default_open_permissions()
            await message.bot.set_chat_permissions(
                chat_id=message.chat.id,
                permissions=permissions,
                use_independent_chat_permissions=True,
            )
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            await safe_reply(
                message,
                "Не получилось сделать отбой. Проверь права бота на ограничение участников.\n"
                f"<code>{escape(str(exc))}</code>"
            )
            return True

        try:
            saved_reactions = db.pop_alarm_reactions(message.chat.id)
            await set_chat_available_reactions(
                message.bot,
                message.chat.id,
                saved_reactions if saved_reactions is not None else DEFAULT_AVAILABLE_REACTIONS,
            )
        except (TelegramBadRequest, TelegramForbiddenError):
            reaction_warning = "\n\nРеакции не удалось включить. Проверь права бота на изменение настроек группы."

        await safe_reply(message, (settings.clear_text or "Отбой: медиа и реакции снова включены.") + reaction_warning)
        return True

    return False


async def handle_birthdays(message: Message) -> None:
    today = datetime.now().date()
    sent_date = today.isoformat()
    birthdays = db.birthdays_for_date(message.chat.id, today.day, today.month, sent_date)
    for birthday in birthdays:
        await safe_reply(message, f"Сегодня праздник: <b>{escape(birthday.text)}</b> 🎉")
        db.mark_birthday_sent(message.chat.id, birthday.id, sent_date)


async def handle_blacklist(message: Message) -> bool:
    if not message.text:
        return False

    text = normalize_trigger(message.text)
    for item in db.list_blacklist_words(message.chat.id):
        if has_trigger(text, item.word):
            try:
                await message.delete()
            except (TelegramBadRequest, TelegramForbiddenError):
                pass

            user_name = message.from_user.full_name if message.from_user else "Пользователь"
            await safe_reply(message, f"{escape(user_name)}, сообщение удалено: слово в черном списке.")
            return True

    return False


@router.message(Command("setreply"))
async def set_reply(message: Message) -> None:
    if not await require_admin(message):
        return

    payload = split_command_payload(message_html_text(message))
    username, sep, reply_text = payload.partition(" ")
    if not username.startswith("@") or not sep or not reply_text.strip():
        await message.answer("Формат: <code>/setreply @username текст автоответа</code>")
        return

    await remember_sender(message)
    db.set_reply(message.chat.id, username, reply_text, message.from_user.id if message.from_user else None)
    await message.answer(f"Готово. Автоответ для <b>@{escape(normalize_username(username))}</b> сохранен.")


@router.message(F.text.regexp(re.compile(r"^/ответ(\s|$)", re.IGNORECASE)))
async def set_reply_ru(message: Message) -> None:
    command, payload = split_text_command(message_html_text(message))
    if command != "/ответ":
        return

    if not await require_admin(message):
        return

    username, sep, reply_text = payload.partition(" ")
    if not username.startswith("@") or not sep or not reply_text.strip():
        await message.answer("Формат: <code>/ответ @username текст автоответа</code>")
        return

    await remember_sender(message)
    db.set_reply(message.chat.id, username, reply_text, message.from_user.id if message.from_user else None)
    await message.answer(f"Готово. Автоответ для <b>@{escape(normalize_username(username))}</b> сохранен.")


@router.message(F.text.regexp(re.compile(r"^/мойответ(\s|$)", re.IGNORECASE)))
async def my_reply_ru(message: Message) -> None:
    command, payload = split_text_command(message_html_text(message))
    if command != "/мойответ":
        return

    if not await require_admin(message):
        return

    if not message.from_user or not message.from_user.username:
        await message.answer("У вашего аккаунта нет username. Добавьте username в Telegram или используйте /ответ.")
        return

    if not payload:
        await message.answer("Формат: <code>/мойответ текст автоответа</code>")
        return

    await remember_sender(message)
    db.set_reply(message.chat.id, message.from_user.username, payload, message.from_user.id)
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
    await message.answer("Автоответ удален." if deleted else "Для этого username автоответ не найден.")


@router.message(F.text.casefold() == "/списокответов")
async def list_replies_ru(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        await message.answer("Открой /старт в личке и выбери группу.")
        return

    await message.answer(replies_text(message.chat.id))


@router.message(Command("settrigger"))
async def set_trigger(message: Message) -> None:
    if not await require_admin(message):
        return

    payload = split_command_payload(message_html_text(message))
    trigger, reply_text = split_trigger_payload(payload)
    if not trigger or not reply_text:
        await message.answer("Формат: <code>/settrigger слово - текст ответа</code>")
        return

    await remember_sender(message)
    db.set_trigger(message.chat.id, trigger, reply_text, message.from_user.id if message.from_user else None)
    await message.answer(f"Фиксированный ответ на <b>{escape(normalize_trigger(trigger))}</b> сохранен.")


@router.message(F.text.regexp(re.compile(r"^/(тригер|триггер)(\s|$)", re.IGNORECASE)))
async def set_trigger_ru(message: Message) -> None:
    command, payload = split_text_command(message_html_text(message))
    if command not in {"/тригер", "/триггер"}:
        return

    if not await require_admin(message):
        return

    trigger, reply_text = split_trigger_payload(payload)
    if not trigger or not reply_text:
        await message.answer("Формат: <code>/тригер слово - текст ответа</code>")
        return

    await remember_sender(message)
    db.set_trigger(message.chat.id, trigger, reply_text, message.from_user.id if message.from_user else None)
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
    await message.answer("Фиксированный ответ удален." if deleted else "Такой фиксированный ответ не найден.")


@router.message(F.text.casefold() == "/списоктригеров")
async def list_triggers_ru(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        await message.answer("Открой /старт в личке и выбери группу.")
        return

    triggers = db.list_triggers(message.chat.id)
    if not triggers:
        await message.answer("В этой группе пока нет фиксированных ответов.")
        return

    lines = ["<b>Фиксированные ответы:</b>"]
    for item in triggers:
        lines.append(f"{escape(item.trigger)} - {preview_html(item.text)}")
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
        "/каналы",
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
    if len(picked) != settings.winners_count:
        users = db.list_pickable_users(message.chat.id)
        if not users:
            await safe_reply(message, "Пока некого выбрать: бот еще не видел участников с username.")
            return True

        count = min(settings.winners_count, len(users))
        picked = random.sample(users, count)
        picked_ids = [user.user_id for user in picked]
        db.set_giveaway_picks(message.chat.id, pick_key, today, picked_ids)

    db.award_giveaway_stats_once(message.chat.id, pick_key, today, [user.user_id for user in picked])

    lines = [f"<b>{escape(settings.title)}:</b>"]
    for index, user in enumerate(picked, start=1):
        lines.append(f"{index}. @{escape(user.username or user.full_name)}")
    await safe_reply(message, "\n".join(lines))
    return True


@router.message(F.text.regexp(re.compile(r"^топ\s+пидоров[?!.]?$", re.IGNORECASE)))
async def giveaway_top(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return

    await remember_sender(message)
    stats = db.top_giveaway_stats(message.chat.id, limit=10)
    if not stats:
        await safe_reply(message, "Топ пока пуст. Сначала вызови дневной розыгрыш: кто пидор")
        return

    lines = ["<b>Топ пидоров:</b>"]
    for index, item in enumerate(stats, start=1):
        name = f"@{item.username}" if item.username else item.full_name
        lines.append(f"{index}. {escape(name)} - <b>{item.wins_count}</b>")

    await safe_reply(message, "\n".join(lines))


@router.message(F.text.regexp(re.compile(r"^roll\s+mute$", re.IGNORECASE)))
async def roll_mute(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return
    if not message.from_user or not await is_chat_admin(message.bot, message.chat.id, message.from_user.id):
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

    picked = random.choice(candidates)
    until_date = now + timedelta(minutes=settings.mute_minutes)
    try:
        await message.bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=picked.user_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date,
            use_independent_chat_permissions=True,
        )
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        await safe_reply(
            message,
            "Не получилось замутить участника. Проверь, что бот админ и может ограничивать участников.\n"
            f"<code>{escape(str(exc))}</code>",
        )
        return

    db.set_roll_mute_last_used(message.chat.id, now.isoformat(timespec="seconds"))
    db.increment_roll_mute_stat(message.chat.id, picked.user_id)
    name = f"@{picked.username}" if picked.username else picked.full_name
    await safe_reply(message, f"Roll mute выбрал {escape(name)}. Мут на <b>{settings.mute_minutes}</b> мин.")


@router.message(F.text.regexp(re.compile(r"^топ\s+roll\s+mute[?!.]?$", re.IGNORECASE)))
async def roll_mute_top(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return

    await remember_sender(message)
    stats = db.top_roll_mute_stats(message.chat.id, limit=10)
    if not stats:
        await safe_reply(
            message,
            "Топ roll mute пока пуст. Статистика считается только для успешных <code>roll mute</code> после обновления бота.",
        )
        return

    lines = ["<b>Топ roll mute:</b>"]
    for index, item in enumerate(stats, start=1):
        name = f"@{item.username}" if item.username else item.full_name
        lines.append(f"{index}. {escape(name)} - <b>{item.unlucky_count}</b>")

    await safe_reply(message, "\n".join(lines))


@router.message(F.text.regexp(re.compile(r"^(@[A-Za-z0-9_]{5,32}\s+)?затихни\s+\d+(\s+-\s+.*)?$", re.IGNORECASE)))
async def quiet_user(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return
    if not message.from_user or not await is_chat_admin(message.bot, message.chat.id, message.from_user.id):
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

    minutes = max(1, min(10080, minutes))
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
    await safe_reply(message, render_quiet_reply(settings.reply_text, target_name, minutes, reason))
    await send_quiet_media(message, settings.media_type, settings.media_file_id)


@router.message(F.text.regexp(re.compile(r"^(@[A-Za-z0-9_]{5,32}\s+)?трещи$", re.IGNORECASE)))
async def unquiet_user(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return
    if not message.from_user or not await is_chat_admin(message.bot, message.chat.id, message.from_user.id):
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

    await safe_reply(message, f"{escape(target_name)} снова может трещать.")


@router.message(F.text.casefold() == "в цитаты")
async def add_quote(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES or not message.reply_to_message:
        return

    await remember_sender(message)
    source = message.reply_to_message
    quote_text = source.html_text or source.text or source.caption or source.html_caption
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
    await safe_reply(message, f"Слово добавлено в черный список: <b>{escape(normalize_trigger(word))}</b>")


@router.message(F.text.regexp(re.compile(r"^разрешить\s+.+", re.IGNORECASE)))
async def delete_blacklist_word(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return
    if not await require_admin(message):
        return

    word = split_command_payload(message.text)
    deleted = db.delete_blacklist_word(message.chat.id, word)
    await safe_reply(message, "Слово удалено из черного списка." if deleted else "Такого слова в черном списке нет.")


@router.message(F.text.casefold() == "черный список")
async def list_blacklist_words(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return

    words = db.list_blacklist_words(message.chat.id)
    if not words:
        await safe_reply(message, "Черный список пуст.")
        return

    lines = ["<b>Черный список:</b>"]
    lines.extend(f"{index}. {escape(item.word)}" for index, item in enumerate(words, start=1))
    await safe_reply(message, "\n".join(lines))


@router.message(F.text.regexp(re.compile(r"^бот[, ]\s*.+", re.IGNORECASE)))
async def ai_answer(message: Message) -> None:
    if message.chat.type not in SUPPORTED_CHAT_TYPES:
        return

    prompt = extract_ai_prompt(message.text)
    if not prompt:
        return

    await remember_sender(message)
    try:
        answer = await fetch_ai_answer(prompt)
    except Exception as exc:
        await safe_reply(message, f"AI не ответил: <code>{escape(str(exc))}</code>")
        return
    await safe_reply(message, answer)


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

    if message.text and message.text.startswith("/"):
        await remember_sender(message)
        return

    text = message.text or message.caption
    if not text:
        return

    await remember_sender(message)
    await handle_birthdays(message)
    if await handle_blacklist(message):
        return

    if await handle_alarm_mode(message):
        return

    if message.text and await handle_day_pick(message):
        return

    answers: list[str] = []
    trigger_answers = [
        item.text
        for item in db.list_triggers(message.chat.id)
        if has_trigger(text, item.trigger)
    ]
    if trigger_answers:
        answers.append(random.choice(trigger_answers))

    mentions = extract_mentions(text)
    if mentions:
        answers.extend(item.text for item in db.replies_for_mentions(message.chat.id, mentions))

    if not answers:
        return

    await safe_reply(message, "\n\n".join(answers), disable_web_page_preview=True)


@router.message(F.chat.type == "private")
async def private_fallback(message: Message) -> None:
    await message.answer("Выбери группу и действие кнопками.", reply_markup=main_menu())


@router.message(F.text | F.caption)
async def auto_reply_message(message: Message) -> None:
    await handle_auto_reply(message)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    acquire_single_instance_lock()
    config = load_config()

    global db
    global BOT_ADMIN_IDS
    BOT_ADMIN_IDS = config.bot_admin_ids
    db = Database(config.db_path)
    db.init()

    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher()
    router.message.middleware(DropStaleMessagesMiddleware())
    dispatcher.include_router(router)

    try:
        await bot.get_me()
        await dispatcher.start_polling(bot, allowed_updates=["message", "callback_query"])
    except TelegramNotFound as exc:
        raise RuntimeError("Telegram rejected BOT_TOKEN. Check .env and paste the real token from BotFather.") from exc
    finally:
        await bot.session.close()
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
