import os
from urllib.parse import urlencode

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from .db import ChatTopic, RegisteredChat

TRIGGERS_PAGE_SIZE = 25
QUOTES_PAGE_SIZE = 25
TOP_PAGE_SIZE = 20
DEFAULT_BOT_USERNAME = "ypominanieBot"
MINI_APP_SHOP_START_PARAM = "shop"


def miniapp_deep_link(start_param: str) -> str:
    bot_username = os.getenv("BOT_USERNAME", DEFAULT_BOT_USERNAME).strip().lstrip("@") or DEFAULT_BOT_USERNAME
    return f"https://t.me/{bot_username}?startapp={start_param}"


def miniapp_deep_link_button(label: str, start_param: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=label, url=miniapp_deep_link(start_param))


def miniapp_button() -> InlineKeyboardButton | None:
    url = os.getenv("MINI_APP_URL", "").strip().rstrip("/")
    if not url:
        base = os.getenv("ADMIN_PUBLIC_URL", "").strip().rstrip("/")
        url = f"{base}/miniapp" if base else ""
    if not url:
        return InlineKeyboardButton(text="Шахта Mini App", callback_data="miniapp:open")
    return InlineKeyboardButton(text="Шахта Mini App", web_app=WebAppInfo(url=url)) if url else None


def miniapp_private_button(label: str = "Шахта Mini App", view: str | None = None) -> InlineKeyboardButton:
    url = os.getenv("MINI_APP_URL", "").strip().rstrip("/")
    if not url:
        base = os.getenv("ADMIN_PUBLIC_URL", "").strip().rstrip("/")
        url = f"{base}/miniapp" if base else ""
    if view and url:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{urlencode({'view': view})}"
    if not url or not url.lower().startswith("https://"):
        return InlineKeyboardButton(text=label, callback_data="miniapp:open")
    return InlineKeyboardButton(text=label, web_app=WebAppInfo(url=url))


def miniapp_private_menu(label: str = "Шахта Mini App", view: str | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[miniapp_private_button(label, view)]])


def main_menu() -> InlineKeyboardMarkup:
    rows = [
        [miniapp_button()],
        [InlineKeyboardButton(text="Панель владельца", callback_data="ui:chats")],
        [InlineKeyboardButton(text="Я пользователь", callback_data="user:chats")],
    ]
    rows.extend(
        [
            [InlineKeyboardButton(text="Premium", callback_data="premium:menu")],
            [InlineKeyboardButton(text="Обратная связь", callback_data="feedback:start")],
        ]
    )
    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def admin_back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Назад", callback_data="ui:chats")],
        ]
    )


def admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Выбор группы", callback_data="ui:chat_select")],
            [
                InlineKeyboardButton(text="Проверка групп", callback_data="ui:status"),
                InlineKeyboardButton(text="Кто я", callback_data="ui:whoami"),
            ],
            [InlineKeyboardButton(text="Перезагрузка", callback_data="ui:restart")],
            [InlineKeyboardButton(text="Звезды", callback_data="stars:menu")],
            [InlineKeyboardButton(text="Адрес сервера", callback_data="server:ip")],
            [InlineKeyboardButton(text="Очистить чат", callback_data="ui:clear_chat")],
            [InlineKeyboardButton(text="Помощь", callback_data="ui:help")],
            [InlineKeyboardButton(text="Назад", callback_data="ui:home")],
        ]
    )


def chat_select_menu(chats: list[RegisteredChat]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for chat in chats[:45]:
        title = chat.title
        if len(title) > 38:
            title = title[:35] + "..."
        rows.append([InlineKeyboardButton(text=title, callback_data=f"chat:{chat.chat_id}")])

    rows.append([InlineKeyboardButton(text="Назад", callback_data="ui:chats")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_chat_select_menu(chats: list[RegisteredChat]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for chat in chats[:45]:
        title = chat.title
        if len(title) > 38:
            title = title[:35] + "..."
        rows.append([InlineKeyboardButton(text=title, callback_data=f"user:chat:{chat.chat_id}")])

    rows.append([InlineKeyboardButton(text="Назад", callback_data="ui:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _base_user_menu(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Сообщение за звезды", callback_data=f"paid:chat:{chat_id}")],
            [InlineKeyboardButton(text="Шахта", callback_data=f"user:mine:{chat_id}")],
            [InlineKeyboardButton(text="\u041f\u0440\u043e\u0444\u0438\u043b\u044c", callback_data=f"profile:chat:{chat_id}")],
            [InlineKeyboardButton(text="Premium", callback_data="premium:menu")],
            [InlineKeyboardButton(text="Выбрать другую группу", callback_data="user:chats")],
            [InlineKeyboardButton(text="Назад", callback_data="ui:home")],
        ]
    )


def user_menu(chat_id: int) -> InlineKeyboardMarkup:
    markup = _base_user_menu(chat_id)
    button = miniapp_button()
    if button:
        markup.inline_keyboard.insert(2, [button])
    return markup


def social_profile_menu(
    chat_id: int,
    viewer_id: int,
    target_id: int,
    friendship: str,
    couple: str,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if viewer_id == target_id:
        rows.append(
            [InlineKeyboardButton(text="Мои друзья", callback_data=f"soc:fl:{chat_id}:{viewer_id}")]
        )
    else:
        if friendship == "friends":
            rows.append(
                [
                    InlineKeyboardButton(
                        text="Удалить из друзей",
                        callback_data=f"soc:fr:{chat_id}:{viewer_id}:{target_id}",
                    )
                ]
            )
        elif friendship == "none":
            rows.append(
                [
                    InlineKeyboardButton(
                        text="Добавить в друзья",
                        callback_data=f"soc:fq:{chat_id}:{viewer_id}:{target_id}",
                    )
                ]
            )
        elif friendship == "outgoing":
            rows.append([InlineKeyboardButton(text="Заявка в друзья отправлена", callback_data="soc:noop")])
        elif friendship == "incoming":
            rows.append([InlineKeyboardButton(text="У тебя есть входящая заявка", callback_data="soc:noop")])

        if couple == "couple":
            rows.append(
                [
                    InlineKeyboardButton(
                        text="Расстаться",
                        callback_data=f"soc:pe:{chat_id}:{viewer_id}:{target_id}",
                    )
                ]
            )
        elif couple == "none":
            rows.append(
                [
                    InlineKeyboardButton(
                        text="Предложить стать парой",
                        callback_data=f"soc:pq:{chat_id}:{viewer_id}:{target_id}",
                    )
                ]
            )
        elif couple == "outgoing":
            rows.append([InlineKeyboardButton(text="Предложение уже отправлено", callback_data="soc:noop")])
        elif couple == "incoming":
            rows.append([InlineKeyboardButton(text="У тебя есть входящее предложение", callback_data="soc:noop")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def social_request_menu(kind: str, chat_id: int, requester_id: int, target_id: int) -> InlineKeyboardMarkup:
    prefix = "f" if kind == "friend" else "p"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Принять",
                    callback_data=f"soc:{prefix}a:{chat_id}:{requester_id}:{target_id}",
                ),
                InlineKeyboardButton(
                    text="Отклонить",
                    callback_data=f"soc:{prefix}d:{chat_id}:{requester_id}:{target_id}",
                ),
            ]
        ]
    )


def social_couple_end_menu(chat_id: int, user_id: int, partner_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, расстаться",
                    callback_data=f"soc:px:{chat_id}:{user_id}:{partner_id}",
                ),
                InlineKeyboardButton(text="Отмена", callback_data="soc:noop"),
            ]
        ]
    )


def premium_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Медиа-инструменты", callback_data="media:menu")],
            [InlineKeyboardButton(text="Купить Базовый - 50 ⭐", callback_data="premium:buy:basic")],
            [InlineKeyboardButton(text="Купить Расширенный - 100 ⭐", callback_data="premium:buy:extended")],
            [InlineKeyboardButton(text="Обновить статус", callback_data="premium:menu")],
            [InlineKeyboardButton(text="Назад", callback_data="ui:home")],
        ]
    )


def media_tools_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Извлечь аудио из видео", callback_data="media:tool:extract_audio")],
            [InlineKeyboardButton(text="Конвертировать аудио в MP3", callback_data="media:tool:audio_convert")],
            [InlineKeyboardButton(text="Конвертировать видео в MP4", callback_data="media:tool:video_convert")],
            [InlineKeyboardButton(text="Сжать видео", callback_data="media:tool:compress_video")],
            [InlineKeyboardButton(text="Сжать аудио", callback_data="media:tool:compress_audio")],
            [InlineKeyboardButton(text="Сделать GIF из видео", callback_data="media:tool:gif_create")],
            [InlineKeyboardButton(text="Расшифровать аудио в текст", callback_data="media:tool:transcription")],
            [InlineKeyboardButton(text="Расшифровать с таймкодами", callback_data="media:tool:transcription_timestamps")],
            [InlineKeyboardButton(text="Мои задачи", callback_data="media:history")],
            [InlineKeyboardButton(text="Назад к Premium", callback_data="premium:menu")],
        ]
    )


def media_cancel_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="media:menu")]]
    )


def youtube_download_menu(is_music: bool) -> InlineKeyboardMarkup:
    rows = (
        [
            [InlineKeyboardButton(text="Скачать MP3", callback_data="youtube:music_mp3")],
            [InlineKeyboardButton(text="Скачать M4A", callback_data="youtube:music_m4a")],
        ]
        if is_music
        else [
            [InlineKeyboardButton(text="Скачать видео MP4", callback_data="youtube:video_mp4")],
            [InlineKeyboardButton(text="Скачать аудио MP3", callback_data="youtube:audio_mp3")],
        ]
    )
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="youtube:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def instagram_download_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Скачать Reels MP4", callback_data="youtube:video_mp4")],
            [InlineKeyboardButton(text="Отмена", callback_data="youtube:cancel")],
        ]
    )


def _legacy_user_mine_menu(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Копать", callback_data=f"user:dig:{chat_id}")],
            [InlineKeyboardButton(text="Сумка", callback_data=f"user:bag:{chat_id}")],
            [InlineKeyboardButton(text="Донат", callback_data=f"user:donate:{chat_id}")],
            [InlineKeyboardButton(text="Назад", callback_data=f"user:chat:{chat_id}")],
        ]
    )


def user_dig_mode_menu(chat_id: int, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="\u0410\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438", callback_data=f"user:dig:auto:{chat_id}:{user_id}")],
            [miniapp_deep_link_button("\u0412\u0440\u0443\u0447\u043d\u0443\u044e", f"mine_{user_id}")],
        ]
    )


def interactive_dig_menu(
    session_id: str,
    depth: int,
    cells: list[dict] | dict,
    used_cells: list[int] | None = None,
    tools: list[str] | None = None,
) -> InlineKeyboardMarkup:
    if isinstance(cells, dict) and cells.get("type") in {"event", "final"}:
        rows = [
            [
                InlineKeyboardButton(
                    text=str(choice.get("label") or "Выбрать"),
                    callback_data=f"digevent:{session_id}:{int(depth)}:{choice.get('key')}",
                )
            ]
            for choice in cells.get("choices", [])[:3]
        ]
        rows.append([InlineKeyboardButton(text="💰 Забрать добычу и выйти", callback_data=f"digexit:{session_id}")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    if isinstance(cells, dict):
        cells = cells.get("cells", [])
    emojis = {
        "normal": "🟫",
        "ore": "✨",
        "hard": "🪨",
        "roots": "🌿",
        "unknown": "❓",
    }
    used = {int(item) for item in (used_cells or [])}
    cell_rows = []
    cell_row = []
    for index, cell in enumerate(cells[:7]):
        kind = str(cell.get("kind") or "unknown")
        revealed = cell.get("revealed")
        prefix = "▫️" if index in used else emojis.get(kind, "❓")
        text = f"{prefix}{index + 1}" if not revealed else f"👁{emojis.get(str(revealed), '❓')}"
        cell_row.append(
            InlineKeyboardButton(
                text=text,
                callback_data=f"digcell:{session_id}:{int(depth)}:{index}",
            )
        )
        if len(cell_row) == 4:
            cell_rows.append(cell_row)
            cell_row = []
    if cell_row:
        cell_rows.append(cell_row)
    tool_labels = {
        "flashlight": "🔦 Фонарь",
        "map": "🗺 Карта",
        "dynamite": "🧨 Динамит",
        "miner_hearing": "👂 Слух",
        "magnet": "🧲 Магнит",
        "cat_companion": "🐈 Компаньон",
    }
    tool_rows = [
        [InlineKeyboardButton(text=tool_labels[key], callback_data=f"digtool:{session_id}:{int(depth)}:{key}")]
        for key in (tools or [])
        if key in tool_labels
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            *cell_rows,
            *tool_rows,
            [InlineKeyboardButton(text="💰 Забрать добычу и выйти", callback_data=f"digexit:{session_id}")],
        ]
    )


def user_mine_menu(chat_id: int, user_id: int, show_back: bool = True) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="\u041a\u043e\u043f\u0430\u0442\u044c", callback_data=f"user:dig:mode:{chat_id}:{user_id}")],
        [InlineKeyboardButton(text="\u0421\u0443\u043c\u043a\u0430", callback_data=f"user:bag:{chat_id}:{user_id}")],
        [InlineKeyboardButton(text="\u0414\u043e\u043d\u0430\u0442", callback_data=f"user:donate:{chat_id}:{user_id}")],
    ]
    if show_back:
        rows.append([InlineKeyboardButton(text="\u041d\u0430\u0437\u0430\u0434", callback_data=f"user:chat:{chat_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_bag_menu(chat_id: int, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [miniapp_deep_link_button("Магазин", f"{MINI_APP_SHOP_START_PARAM}_{user_id}")],
            [InlineKeyboardButton(text="Маршруты", callback_data=f"user:routes:{chat_id}:{user_id}")],
            [InlineKeyboardButton(text="Контракты", callback_data=f"user:contracts:{chat_id}:{user_id}")],
            [InlineKeyboardButton(text="Экспедиция", callback_data=f"user:expedition:{chat_id}:{user_id}")],
            [InlineKeyboardButton(text="Донат", callback_data=f"user:donate:{chat_id}:{user_id}")],
            [InlineKeyboardButton(text="Назад", callback_data=f"user:mine:{chat_id}:{user_id}")],
        ]
    )


def user_shift_contract_menu(chat_id: int, user_id: int, contract_keys: list[str] | None = None) -> InlineKeyboardMarkup:
    labels = {
        "shift_depth_4": "Пройти 4 м",
        "shift_coins_60": "Добыть 60 котоинов",
        "shift_artifact": "Найти артефакт",
    }
    rows = [
        [InlineKeyboardButton(text=labels[key], callback_data=f"user:shiftpick:{chat_id}:{user_id}:{key}")]
        for key in (contract_keys or [])
        if key in labels
    ]
    rows.append([InlineKeyboardButton(text="Назад к сумке", callback_data=f"user:bag:{chat_id}:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_shop_menu(chat_id: int, user_id: int, items: list[tuple[str, str, int]]) -> InlineKeyboardMarkup:
    rows = []
    for key, name, price in items:
        buy_name = name[0].lower() + name[1:] if name else name
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"Купить {buy_name} - {price}",
                    callback_data=f"user:buy:{chat_id}:{user_id}:{key}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="Назад к сумке", callback_data=f"user:bag:{chat_id}:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_shop_categories_menu(chat_id: int, user_id: int, categories: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=title, callback_data=f"user:shop:{chat_id}:{user_id}:{key}:0")]
        for key, title in categories
    ]
    rows.append([InlineKeyboardButton(text="Назад к сумке", callback_data=f"user:bag:{chat_id}:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_shop_items_menu(
    chat_id: int,
    user_id: int,
    category: str,
    page: int,
    total_pages: int,
    items: list[tuple[str, str, int]],
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{name} - {price}", callback_data=f"user:buy:{chat_id}:{user_id}:{key}")]
        for key, name, price in items
    ]
    if total_pages > 1:
        prev_page = max(0, page - 1)
        next_page = min(total_pages - 1, page + 1)
        rows.append(
            [
                InlineKeyboardButton(text="<", callback_data=f"user:shop:{chat_id}:{user_id}:{category}:{prev_page}"),
                InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data=f"user:shop:{chat_id}:{user_id}:{category}:{page}"),
                InlineKeyboardButton(text=">", callback_data=f"user:shop:{chat_id}:{user_id}:{category}:{next_page}"),
            ]
        )
    rows.append([InlineKeyboardButton(text="Категории", callback_data=f"user:shop:{chat_id}:{user_id}")])
    rows.append([InlineKeyboardButton(text="Назад к сумке", callback_data=f"user:bag:{chat_id}:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_buy_confirm_menu(chat_id: int, user_id: int, item_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Купить",
                    callback_data=f"user:confirm:{chat_id}:{user_id}:{item_key}",
                )
            ],
            [InlineKeyboardButton(text="Назад в магазин", callback_data=f"user:shop:{chat_id}:{user_id}")],
        ]
    )


def user_donate_menu(chat_id: int, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Восстановить удачу - 3 ⭐", callback_data=f"user:star:luck:{chat_id}:{user_id}")],
            [InlineKeyboardButton(text="Сбросить ожидание копай - 1 ⭐", callback_data=f"user:star:cooldown:{chat_id}:{user_id}")],
            [InlineKeyboardButton(text="Копать 3 раза - 3 ⭐", callback_data=f"user:star:digs3:{chat_id}:{user_id}")],
            [InlineKeyboardButton(text="Копать 3 раза со 100 удачей - 10 ⭐", callback_data=f"user:star:lucky_digs3:{chat_id}:{user_id}")],
            [InlineKeyboardButton(text="Копать 5 раз - 5 ⭐", callback_data=f"user:star:digs5:{chat_id}:{user_id}")],
            [InlineKeyboardButton(text="Копать 5 раз со 100 удачей - 15 ⭐", callback_data=f"user:star:lucky_digs5:{chat_id}:{user_id}")],
            [InlineKeyboardButton(text="Прокопать 10 м - 50 ⭐", callback_data=f"user:star:depth10:{chat_id}:{user_id}")],
            [InlineKeyboardButton(text="Супер-игра 9×9 - 10 ⭐", callback_data=f"user:star:super_game:{chat_id}:{user_id}")],
            [InlineKeyboardButton(text="Назад", callback_data=f"user:mine:{chat_id}")],
        ]
    )


def paid_chat_select_menu(chats: list[RegisteredChat]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for chat in chats[:45]:
        title = chat.title
        if len(title) > 38:
            title = title[:35] + "..."
        rows.append([InlineKeyboardButton(text=title, callback_data=f"paid:chat:{chat.chat_id}")])

    rows.append([InlineKeyboardButton(text="Назад", callback_data="ui:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def chat_admin_menu(chat_id: int, include_access: bool = False, allowed_features: set[str] | None = None) -> InlineKeyboardMarkup:
    rows = [
            [
                InlineKeyboardButton(text="Добавить @ответ", callback_data=f"act:set_reply:{chat_id}"),
                InlineKeyboardButton(text="Удалить @ответ", callback_data=f"act:del_reply:{chat_id}"),
            ],
            [
                InlineKeyboardButton(text="Список тригеров", callback_data=f"act:list:{chat_id}"),
                InlineKeyboardButton(text="Топ участников", callback_data=f"act:participants:{chat_id}"),
            ],
            [
                InlineKeyboardButton(text="Настроить розыгрыш", callback_data=f"act:giveaway:{chat_id}"),
                InlineKeyboardButton(text="Режим тревоги", callback_data=f"act:alarm:{chat_id}"),
            ],
            [
                InlineKeyboardButton(text="Roll mute", callback_data=f"act:roll_mute:{chat_id}"),
                InlineKeyboardButton(text="Затихни", callback_data=f"act:quiet:{chat_id}"),
            ],
            [InlineKeyboardButton(text="Черный список слов", callback_data=f"act:blacklist:{chat_id}")],
            [InlineKeyboardButton(text="Цитаты", callback_data=f"act:quotes:{chat_id}")],
            [InlineKeyboardButton(text="Написать в чат", callback_data=f"act:send_message:{chat_id}")],
            [InlineKeyboardButton(text="Логи", callback_data=f"act:logs:{chat_id}")],
            [
                InlineKeyboardButton(text="Проверить доступ", callback_data=f"act:check:{chat_id}"),
                InlineKeyboardButton(text="Назад к группам", callback_data="ui:chat_select"),
            ],
            [InlineKeyboardButton(text="Выйти из группы", callback_data=f"act:leave:{chat_id}")],
    ]
    if allowed_features is not None:
        action_features = {
            "set_reply": "addReply",
            "del_reply": "deleteReply",
            "list": "triggers",
            "participants": "participants",
            "giveaway": "giveaway",
            "alarm": "alarm",
            "roll_mute": "rollMute",
            "quiet": "quiet",
            "blacklist": "blacklist",
            "quotes": "quotes",
            "send_message": "send",
            "logs": "logs",
            "check": "checkAccess",
        }
        filtered_rows: list[list[InlineKeyboardButton]] = []
        for row in rows:
            filtered_row: list[InlineKeyboardButton] = []
            for button in row:
                data = button.callback_data or ""
                parts = data.split(":")
                action = parts[1] if len(parts) >= 3 and parts[0] == "act" else ""
                feature = action_features.get(action)
                if feature is None or feature in allowed_features:
                    filtered_row.append(button)
            if filtered_row:
                filtered_rows.append(filtered_row)
        rows = filtered_rows
    if include_access:
        rows.insert(-1, [InlineKeyboardButton(text="Доступ", callback_data=f"act:access:{chat_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_to_chat_menu(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Назад к настройкам", callback_data=f"chat:{chat_id}")],
            [InlineKeyboardButton(text="Выбрать другую группу", callback_data="ui:chat_select")],
        ]
    )


def participant_top_menu(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="День", callback_data=f"participants:top:{chat_id}:day"),
                InlineKeyboardButton(text="Неделя", callback_data=f"participants:top:{chat_id}:week"),
            ],
            [
                InlineKeyboardButton(text="Месяц", callback_data=f"participants:top:{chat_id}:month"),
                InlineKeyboardButton(text="Все время", callback_data=f"participants:top:{chat_id}:all"),
            ],
            [InlineKeyboardButton(text="Назад к настройкам", callback_data=f"chat:{chat_id}")],
        ]
    )


def chat_top_page_menu(kind: str, chat_id: int, page: int, total: int) -> InlineKeyboardMarkup:
    max_page = max(0, (total - 1) // TOP_PAGE_SIZE)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="←", callback_data=f"top:{kind}:{chat_id}:{max(0, page - 1)}"),
                InlineKeyboardButton(text=f"{page + 1}/{max_page + 1}", callback_data=f"top:{kind}:{chat_id}:{page}"),
                InlineKeyboardButton(text="→", callback_data=f"top:{kind}:{chat_id}:{min(max_page, page + 1)}"),
            ]
        ]
    )


def blacklist_menu(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Добавить слово", callback_data=f"blacklist:add:{chat_id}"),
                InlineKeyboardButton(text="Удалить слово", callback_data=f"blacklist:delete:{chat_id}"),
            ],
            [InlineKeyboardButton(text="Назад к настройкам", callback_data=f"chat:{chat_id}")],
        ]
    )


def quotes_menu(chat_id: int, page: int, total: int) -> InlineKeyboardMarkup:
    max_page = max(0, (total - 1) // QUOTES_PAGE_SIZE)
    rows: list[list[InlineKeyboardButton]] = []

    if max_page > 0:
        rows.append(
            [
                InlineKeyboardButton(text="←", callback_data=f"quotes:page:{chat_id}:{max(0, page - 1)}"),
                InlineKeyboardButton(text=f"{page + 1}/{max_page + 1}", callback_data=f"quotes:page:{chat_id}:{page}"),
                InlineKeyboardButton(text="→", callback_data=f"quotes:page:{chat_id}:{min(max_page, page + 1)}"),
            ]
        )

    rows.append([InlineKeyboardButton(text="Удалить цитату", callback_data=f"quotes:delete:{chat_id}")])
    rows.append([InlineKeyboardButton(text="Назад к настройкам", callback_data=f"chat:{chat_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def trigger_list_menu(chat_id: int, page: int, total: int) -> InlineKeyboardMarkup:
    max_page = max(0, (total - 1) // TRIGGERS_PAGE_SIZE)
    rows: list[list[InlineKeyboardButton]] = []

    if max_page > 0:
        rows.append(
            [
                InlineKeyboardButton(text="←", callback_data=f"list:{chat_id}:{max(0, page - 1)}"),
                InlineKeyboardButton(text=f"{page + 1}/{max_page + 1}", callback_data=f"list:{chat_id}:{page}"),
                InlineKeyboardButton(text="→", callback_data=f"list:{chat_id}:{min(max_page, page + 1)}"),
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(text="Добавить слово", callback_data=f"act:set_trigger:{chat_id}"),
            InlineKeyboardButton(text="Удалить слово", callback_data=f"act:del_trigger:{chat_id}"),
        ]
    )
    rows.append([InlineKeyboardButton(text="Назад к настройкам", callback_data=f"chat:{chat_id}")])
    rows.append([InlineKeyboardButton(text="Выбрать другую группу", callback_data="ui:chat_select")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def leave_confirm_menu(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Да, выйти", callback_data=f"leave:yes:{chat_id}")],
            [InlineKeyboardButton(text="Отмена", callback_data=f"chat:{chat_id}")],
        ]
    )


def restart_confirm_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Да, перезапустить", callback_data="restart:yes")],
            [InlineKeyboardButton(text="Отмена", callback_data="ui:chats")],
        ]
    )


def stars_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Баланс звезд", callback_data="stars:balance")],
            [InlineKeyboardButton(text="Кто платил", callback_data="stars:payers")],
            [InlineKeyboardButton(text="Назад", callback_data="ui:chats")],
        ]
    )


def feedback_reply_menu(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Ответить", callback_data=f"feedback:reply:{user_id}")],
            [InlineKeyboardButton(text="В меню", callback_data="ui:home")],
        ]
    )


def dig_register_menu(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Зарегистрироваться в игре", callback_data=f"dig:register:{user_id}")],
        ]
    )


def dig_bag_menu(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [miniapp_deep_link_button("Магазин", f"{MINI_APP_SHOP_START_PARAM}_{user_id}")],
            [InlineKeyboardButton(text="Маршруты", callback_data=f"dig:routes:{user_id}")],
            [InlineKeyboardButton(text="Контракты", callback_data=f"dig:contracts:{user_id}")],
            [InlineKeyboardButton(text="Экспедиция", callback_data=f"dig:expedition:{user_id}")],
            [InlineKeyboardButton(text="Достижения", callback_data=f"dig:achievements:{user_id}")],
            [InlineKeyboardButton(text="Донат", callback_data=f"dig:donate:{user_id}")],
        ]
    )


def dig_routes_menu(user_id: int, routes: list[tuple[str, str, bool]]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=("✓ " if selected else "") + name, callback_data=f"dig:route:{user_id}:{key}")]
        for key, name, selected in routes
    ]
    rows.append([InlineKeyboardButton(text="Назад к сумке", callback_data=f"dig:bag:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def dig_section_back_menu(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Назад к сумке", callback_data=f"dig:bag:{user_id}")]]
    )


def dig_shift_contract_menu(user_id: int, contract_keys: list[str] | None = None) -> InlineKeyboardMarkup:
    labels = {
        "shift_depth_4": "Пройти 4 м",
        "shift_coins_60": "Добыть 60 котоинов",
        "shift_artifact": "Найти артефакт",
    }
    rows = [
        [InlineKeyboardButton(text=labels[key], callback_data=f"dig:shiftpick:{user_id}:{key}")]
        for key in (contract_keys or [])
        if key in labels
    ]
    rows.append([InlineKeyboardButton(text="Назад к сумке", callback_data=f"dig:bag:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_routes_menu(chat_id: int, user_id: int, routes: list[tuple[str, str, bool]]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=("✓ " if selected else "") + name, callback_data=f"user:route:{chat_id}:{user_id}:{key}")]
        for key, name, selected in routes
    ]
    rows.append([InlineKeyboardButton(text="Назад к сумке", callback_data=f"user:bag:{chat_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def dig_shop_menu(user_id: int, items: list[tuple[str, str, int]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for key, name, price in items:
        buy_name = name[:1].lower() + name[1:] if name else name
        rows.append([InlineKeyboardButton(text=f"Купить {buy_name} - {price}", callback_data=f"dig:buy:{user_id}:{key}")])
    rows.append([InlineKeyboardButton(text="Назад к сумке", callback_data=f"dig:bag:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def dig_shop_categories_menu(user_id: int, categories: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=title, callback_data=f"dig:shop:{user_id}:{key}:0")] for key, title in categories]
    rows.append([InlineKeyboardButton(text="Назад к сумке", callback_data=f"dig:bag:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def dig_shop_items_menu(
    user_id: int,
    category: str,
    page: int,
    total_pages: int,
    items: list[tuple[str, str, int]],
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{name} - {price}", callback_data=f"dig:buy:{user_id}:{key}")]
        for key, name, price in items
    ]
    if total_pages > 1:
        prev_page = max(0, page - 1)
        next_page = min(total_pages - 1, page + 1)
        rows.append(
            [
                InlineKeyboardButton(text="<", callback_data=f"dig:shop:{user_id}:{category}:{prev_page}"),
                InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data=f"dig:shop:{user_id}:{category}:{page}"),
                InlineKeyboardButton(text=">", callback_data=f"dig:shop:{user_id}:{category}:{next_page}"),
            ]
        )
    rows.append([InlineKeyboardButton(text="Категории", callback_data=f"dig:shop:{user_id}")])
    rows.append([InlineKeyboardButton(text="Назад к сумке", callback_data=f"dig:bag:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def dig_buy_confirm_menu(user_id: int, item_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Купить", callback_data=f"dig:confirm:{user_id}:{item_key}")],
            [InlineKeyboardButton(text="Назад в магазин", callback_data=f"dig:shop:{user_id}")],
        ]
    )


def alarm_menu(
    chat_id: int,
    enabled: bool,
    api_enabled: bool = False,
    restrictions_enabled: bool = True,
) -> InlineKeyboardMarkup:
    toggle_text = "Выключить режим" if enabled else "Включить режим"
    api_text = "Выключить автотревогу" if api_enabled else "Включить автотревогу"
    restrictions_text = "Выключить ограничения" if restrictions_enabled else "Включить ограничения"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=toggle_text, callback_data=f"alarm:toggle:{chat_id}")],
            [InlineKeyboardButton(text=api_text, callback_data=f"alarm:api:{chat_id}")],
            [InlineKeyboardButton(text=restrictions_text, callback_data=f"alarm:restrictions:{chat_id}")],
            [InlineKeyboardButton(text="Текст тревоги", callback_data=f"alarm:text_on:{chat_id}")],
            [InlineKeyboardButton(text="Текст отбоя", callback_data=f"alarm:text_off:{chat_id}")],
            [InlineKeyboardButton(text="Назад к настройкам", callback_data=f"chat:{chat_id}")],
        ]
    )


def giveaway_menu(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Настройки розыгрыша", callback_data=f"giveaway:settings:{chat_id}")],
            [InlineKeyboardButton(text="Дни рождения", callback_data=f"giveaway:birthdays:{chat_id}")],
            [InlineKeyboardButton(text="Добавить день рождения", callback_data=f"giveaway:add_birthday:{chat_id}")],
            [InlineKeyboardButton(text="Назад к настройкам", callback_data=f"chat:{chat_id}")],
        ]
    )


def birthday_menu(chat_id: int, birthdays) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in birthdays[:30]:
        title = f"{item.day:02d}.{item.month:02d} {item.text}"
        rows.append([InlineKeyboardButton(text=f"Удалить {title[:40]}", callback_data=f"giveaway:delete_birthday:{chat_id}:{item.id}")])
    rows.append([InlineKeyboardButton(text="Добавить день рождения", callback_data=f"giveaway:add_birthday:{chat_id}")])
    rows.append([InlineKeyboardButton(text="Назад к розыгрышам", callback_data=f"act:giveaway:{chat_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def quiet_menu(chat_id: int, has_media: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Замуть того", callback_data=f"quiet:manual:{chat_id}")],
        [InlineKeyboardButton(text="Текст ответа", callback_data=f"quiet:text:{chat_id}")],
        [InlineKeyboardButton(text="Гиф/голос/аудио", callback_data=f"quiet:media:{chat_id}")],
    ]
    if has_media:
        rows.append([InlineKeyboardButton(text="Удалить медиа", callback_data=f"quiet:clear_media:{chat_id}")])
    rows.append([InlineKeyboardButton(text="Назад к настройкам", callback_data=f"chat:{chat_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def topic_select_menu(chat_id: int, topics: list[ChatTopic]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="Без темы / основной чат", callback_data=f"topic:{chat_id}:0")]
    ]

    for topic in topics[:40]:
        title = topic.title
        if len(title) > 38:
            title = title[:35] + "..."
        rows.append([InlineKeyboardButton(text=title, callback_data=f"topic:{chat_id}:{topic.thread_id}")])

    rows.append([InlineKeyboardButton(text="Назад к настройкам", callback_data=f"chat:{chat_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
