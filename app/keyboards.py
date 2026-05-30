from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .db import ChatTopic, RegisteredChat

TRIGGERS_PAGE_SIZE = 25


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Выбрать группу", callback_data="ui:chats")],
            [InlineKeyboardButton(text="Сообщение за звезды", callback_data="paid:chats")],
            [
                InlineKeyboardButton(text="Проверка групп", callback_data="ui:status"),
                InlineKeyboardButton(text="Кто я", callback_data="ui:whoami"),
            ],
            [InlineKeyboardButton(text="Перезагрузка", callback_data="ui:restart")],
            [InlineKeyboardButton(text="Звезды", callback_data="stars:menu")],
            [InlineKeyboardButton(text="Обратная связь", callback_data="feedback:start")],
            [InlineKeyboardButton(text="Очистить чат", callback_data="ui:clear_chat")],
            [InlineKeyboardButton(text="Помощь", callback_data="ui:help")],
        ]
    )


def chat_select_menu(chats: list[RegisteredChat]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for chat in chats[:45]:
        title = chat.title
        if len(title) > 38:
            title = title[:35] + "..."
        rows.append([InlineKeyboardButton(text=title, callback_data=f"chat:{chat.chat_id}")])

    rows.append([InlineKeyboardButton(text="Обновить", callback_data="ui:chats")])
    rows.append([InlineKeyboardButton(text="Назад", callback_data="ui:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def paid_chat_select_menu(chats: list[RegisteredChat]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for chat in chats[:45]:
        title = chat.title
        if len(title) > 38:
            title = title[:35] + "..."
        rows.append([InlineKeyboardButton(text=title, callback_data=f"paid:chat:{chat.chat_id}")])

    rows.append([InlineKeyboardButton(text="Назад", callback_data="ui:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def chat_admin_menu(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Добавить @ответ", callback_data=f"act:set_reply:{chat_id}"),
                InlineKeyboardButton(text="Удалить @ответ", callback_data=f"act:del_reply:{chat_id}"),
            ],
            [
                InlineKeyboardButton(text="Список тригеров", callback_data=f"act:list:{chat_id}"),
                InlineKeyboardButton(text="Участники", callback_data=f"act:participants:{chat_id}"),
            ],
            [
                InlineKeyboardButton(text="Настроить розыгрыш", callback_data=f"act:giveaway:{chat_id}"),
                InlineKeyboardButton(text="Режим тревоги", callback_data=f"act:alarm:{chat_id}"),
            ],
            [
                InlineKeyboardButton(text="Roll mute", callback_data=f"act:roll_mute:{chat_id}"),
                InlineKeyboardButton(text="Затихни", callback_data=f"act:quiet:{chat_id}"),
            ],
            [InlineKeyboardButton(text="Написать в чат", callback_data=f"act:send_message:{chat_id}")],
            [
                InlineKeyboardButton(text="Проверить доступ", callback_data=f"act:check:{chat_id}"),
                InlineKeyboardButton(text="Назад к группам", callback_data="ui:chats"),
            ],
            [InlineKeyboardButton(text="Выйти из группы", callback_data=f"act:leave:{chat_id}")],
        ]
    )


def back_to_chat_menu(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Назад к настройкам", callback_data=f"chat:{chat_id}")],
            [InlineKeyboardButton(text="Выбрать другую группу", callback_data="ui:chats")],
        ]
    )


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
    rows.append([InlineKeyboardButton(text="Выбрать другую группу", callback_data="ui:chats")])
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
            [InlineKeyboardButton(text="Отмена", callback_data="ui:home")],
        ]
    )


def stars_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Баланс звезд", callback_data="stars:balance")],
            [InlineKeyboardButton(text="Кто платил", callback_data="stars:payers")],
            [InlineKeyboardButton(text="Назад", callback_data="ui:home")],
        ]
    )


def feedback_reply_menu(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Ответить", callback_data=f"feedback:reply:{user_id}")],
            [InlineKeyboardButton(text="В меню", callback_data="ui:home")],
        ]
    )


def dig_register_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Зарегистрироваться в игре", callback_data="dig:register")],
        ]
    )


def dig_bag_menu(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Магазин", callback_data=f"dig:shop:{user_id}")],
            [InlineKeyboardButton(text="Достижения", callback_data=f"dig:achievements:{user_id}")],
        ]
    )


def dig_shop_menu(user_id: int, items: list[tuple[str, str, int]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for key, name, price in items:
        rows.append([InlineKeyboardButton(text=f"{name} - {price}", callback_data=f"dig:buy:{user_id}:{key}")])
    rows.append([InlineKeyboardButton(text="Назад к сумке", callback_data=f"dig:bag:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def dig_buy_confirm_menu(user_id: int, item_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Купить", callback_data=f"dig:confirm:{user_id}:{item_key}")],
            [InlineKeyboardButton(text="Назад в магазин", callback_data=f"dig:shop:{user_id}")],
        ]
    )


def alarm_menu(chat_id: int, enabled: bool) -> InlineKeyboardMarkup:
    toggle_text = "Выключить режим" if enabled else "Включить режим"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=toggle_text, callback_data=f"alarm:toggle:{chat_id}")],
            [InlineKeyboardButton(text="Текст тревоги", callback_data=f"alarm:text_on:{chat_id}")],
            [InlineKeyboardButton(text="Текст отбоя", callback_data=f"alarm:text_off:{chat_id}")],
            [InlineKeyboardButton(text="Назад к настройкам", callback_data=f"chat:{chat_id}")],
        ]
    )


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
