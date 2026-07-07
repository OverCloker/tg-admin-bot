import logging
import platform
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from aiogram import Bot, Router
from aiogram.enums import ChatMemberStatus
from aiogram.filters import Command
from aiogram.types import ErrorEvent, Message

from .staff import STAFF_TOPIC_KEYS, StaffService


staff_router = Router(name="staff")
service: StaffService | None = None
started_at = datetime.now(timezone.utc)


def configure_staff(value: StaffService) -> None:
    global service, started_at
    service = value
    started_at = datetime.now(timezone.utc)


def payload(message: Message) -> str:
    return (message.text or "").partition(" ")[2].strip()


def author(message: Message) -> str:
    if not message.from_user:
        return "unknown"
    return f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name


async def allowed(message: Message, bind: bool = False) -> bool:
    if service is None or not message.from_user:
        return False
    if bind:
        if service.owner_id is not None and message.from_user.id == service.owner_id:
            return True
        await message.reply("Команда доступна только владельцу бота.")
        return False
    if service.chat_id != message.chat.id:
        await message.reply("Эта команда доступна только в staff-группе.")
        return False
    if service.owner_id is not None and message.from_user.id == service.owner_id:
        return True
    member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    status = getattr(member.status, "value", member.status)
    if status in {ChatMemberStatus.ADMINISTRATOR.value, ChatMemberStatus.CREATOR.value}:
        return True
    await message.reply("Staff-команды доступны только владельцу и администраторам staff-группы.")
    return False


@staff_router.message(Command("bind_staff"))
async def bind_staff(message: Message) -> None:
    if not await allowed(message, bind=True) or service is None:
        return
    if message.chat.type != "supergroup":
        await message.reply("Staff-группой может быть только Telegram-супергруппа.")
        return
    requested_topic = payload(message).casefold()
    if requested_topic:
        if requested_topic not in STAFF_TOPIC_KEYS:
            await message.reply("Неизвестная тема. Используй: general, status, logs, bugs, tasks, ideas или releases.")
            return
        if service.chat_id != message.chat.id:
            await message.reply("Сначала привяжи эту staff-группу командой <code>/bind_staff</code>.")
            return
        if not message.message_thread_id:
            await message.reply("Эту команду нужно выполнить внутри нужной темы.")
            return
        service.bind_topic(requested_topic, message.message_thread_id)
        await message.reply(f"✅ Staff-тема <code>{requested_topic}</code> привязана.")
        return
    missing = service.bind(message)
    await message.reply("✅ Staff-группа успешно привязана.")
    if missing:
        await service.log(message.bot, "WARNING", "Не найдены темы: " + ", ".join(missing))


@staff_router.message(Command("status"))
async def status(message: Message) -> None:
    if not await allowed(message) or service is None:
        return
    uptime = datetime.now(timezone.utc) - started_at
    db_path = Path(service.db.path)
    db_size = db_path.stat().st_size if db_path.exists() else 0
    try:
        await message.bot.get_me()
        telegram = "подключён"
    except Exception:
        telegram = "ошибка"
    text = (
        "<b>Статус бота</b>\n"
        f"Uptime: <code>{str(uptime).split('.')[0]}</code>\n"
        f"Python: <code>{escape(sys.version.split()[0])}</code>\n"
        f"ОС: <code>{escape(platform.platform())}</code>\n"
        f"Автоответов: <b>{service.db.count_auto_replies()}</b>\n"
        f"Открытых багов: <b>{service.db.count_open_bugs()}</b>\n"
        f"Открытых задач: <b>{service.db.count_open_tasks()}</b>\n"
        f"База данных: <b>{db_size / 1024:.1f} KB</b>\n"
        f"Telegram API: <b>{telegram}</b>"
    )
    await service.send(message.bot, "status", text)


@staff_router.message(Command("logs"))
async def logs(message: Message) -> None:
    if not await allowed(message) or service is None:
        return
    rows = service.db.latest_logs()
    lines = ["<b>Последние записи логов</b>"]
    lines.extend(f"#{row['id']} [{escape(row['level'])}] {escape(row['text'][:500])}" for row in rows)
    await service.send(message.bot, "logs", "\n".join(lines) if rows else "Логи пока пусты.")


@staff_router.message(Command("bug"))
async def bug(message: Message) -> None:
    if not await allowed(message) or service is None or not message.from_user:
        return
    text = payload(message)
    if not text:
        await message.reply("Формат: <code>/bug описание</code>")
        return
    item_id = service.db.add_bug(message.from_user.id, message.from_user.username, text)
    await service.send(message.bot, "bugs", f"🐞 <b>Баг #{item_id}</b>\nАвтор: {escape(author(message))}\nОписание: {escape(text)}\nСтатус: <b>OPEN</b>")


@staff_router.message(Command("task"))
async def task(message: Message) -> None:
    if not await allowed(message) or service is None or not message.from_user:
        return
    text = payload(message)
    if not text:
        await message.reply("Формат: <code>/task описание</code>")
        return
    item_id = service.db.add_task(message.from_user.id, message.from_user.username, text)
    await service.send(message.bot, "tasks", f"📌 <b>Задача #{item_id}</b>\nАвтор: {escape(author(message))}\nОписание: {escape(text)}\nСтатус: <b>OPEN</b>")


@staff_router.message(Command("tasks"))
async def tasks(message: Message) -> None:
    if not await allowed(message) or service is None:
        return
    rows = service.db.open_tasks()
    lines = ["<b>Открытые задачи</b>"]
    lines.extend(f"#{row['id']} — {escape(row['text'][:500])}" for row in rows)
    await service.send(message.bot, "tasks", "\n".join(lines) if rows else "Открытых задач нет.")


@staff_router.message(Command("done"))
async def done(message: Message) -> None:
    if not await allowed(message) or service is None:
        return
    value = payload(message)
    if not value.isdigit():
        await message.reply("Формат: <code>/done ID</code>")
        return
    task_id = int(value)
    text = f"✅ Задача #{task_id} закрыта" if service.db.close_task(task_id) else f"Задача #{task_id} не найдена или уже закрыта."
    await service.send(message.bot, "tasks", text)


@staff_router.message(Command("idea"))
async def idea(message: Message) -> None:
    if not await allowed(message) or service is None or not message.from_user:
        return
    text = payload(message)
    if not text:
        await message.reply("Формат: <code>/idea текст</code>")
        return
    item_id = service.db.add_idea(message.from_user.id, message.from_user.username, text)
    await service.send(message.bot, "ideas", f"💡 <b>Идея #{item_id}</b>\nАвтор: {escape(author(message))}\nОписание: {escape(text)}")


@staff_router.message(Command("release"))
async def release(message: Message) -> None:
    if not await allowed(message) or service is None:
        return
    text = payload(message)
    if not text:
        await message.reply("Формат: <code>/release текст</code>")
        return
    await service.send(message.bot, "releases", f"🚀 <b>Новый релиз</b>\n{escape(text)}")


@staff_router.message(Command("note"))
async def note(message: Message) -> None:
    if not await allowed(message) or service is None or not message.from_user:
        return
    text = payload(message)
    if not text:
        await message.reply("Формат: <code>/note текст</code>")
        return
    service.db.add_note(message.from_user.id, message.from_user.username, text)
    await service.send(message.bot, "general", f"📝 <b>Заметка</b>\nАвтор: {escape(author(message))}\n{escape(text)}")


async def staff_error_handler(event: ErrorEvent, bot: Bot) -> bool:
    exc = event.exception
    logging.error("Unhandled dispatcher error", exc_info=(type(exc), exc, exc.__traceback__))
    if service:
        await service.log(bot, "CRITICAL", repr(exc), notify=True)
    return True
