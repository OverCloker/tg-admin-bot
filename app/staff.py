import logging
from html import escape

from aiogram import Bot
from aiogram.types import FSInputFile, Message

from .staff_db import StaffDatabase


STAFF_TOPICS = {
    "общее": "general",
    "статус": "status",
    "логи": "logs",
    "баги": "bugs",
    "задачи": "tasks",
    "идеи": "ideas",
    "релизы": "releases",
    "модерация": "moderation",
}
STAFF_TOPIC_KEYS = set(STAFF_TOPICS.values())


class StaffService:
    def __init__(self, db_path: str, owner_id: int | None) -> None:
        self.db = StaffDatabase(db_path)
        self.db.init()
        self.owner_id = owner_id

    def close(self) -> None:
        self.db.close()

    @property
    def chat_id(self) -> int | None:
        value = self.db.setting("staff_chat_id")
        return int(value) if value else None

    def topic_id(self, key: str) -> int | None:
        value = self.db.setting(f"staff_topic_{key}")
        return int(value) if value else None

    def bind_topic(self, key: str, thread_id: int) -> bool:
        if key not in STAFF_TOPIC_KEYS:
            return False
        self.db.set_setting(f"staff_topic_{key}", str(thread_id))
        return True

    def bind(self, message: Message) -> list[str]:
        self.db.set_setting("staff_chat_id", str(message.chat.id))
        self.db.set_setting("staff_chat_title", message.chat.title or "")
        return self.sync_known_topics()

    def sync_known_topics(self) -> list[str]:
        chat_id = self.chat_id
        if chat_id is None:
            return list(STAFF_TOPICS.values())
        for row in self.db.known_topics(chat_id):
            self.remember_topic(int(row["thread_id"]), str(row["title"]))
        return [key for key in STAFF_TOPICS.values() if self.topic_id(key) is None]

    def missing_topics(self) -> list[str]:
        return [key for key in STAFF_TOPICS.values() if self.topic_id(key) is None]

    def remember_topic(self, thread_id: int, title: str) -> bool:
        key = STAFF_TOPICS.get(title.strip().casefold())
        if not key:
            return False
        self.db.set_setting(f"staff_topic_{key}", str(thread_id))
        return True

    def observe_message(self, message: Message) -> None:
        if self.chat_id != message.chat.id or not message.message_thread_id:
            return
        # Topic routing is owner-controlled. Telegram administrators may manage
        # topics, but that must not implicitly grant permission to reroute logs.
        if self.owner_id is None or not message.from_user or message.from_user.id != self.owner_id:
            return
        title = None
        if message.forum_topic_created:
            title = message.forum_topic_created.name
        elif message.forum_topic_edited and message.forum_topic_edited.name:
            title = message.forum_topic_edited.name
        elif message.reply_to_message and message.reply_to_message.forum_topic_created:
            title = message.reply_to_message.forum_topic_created.name
        if title:
            self.remember_topic(message.message_thread_id, title)

    async def send(self, bot: Bot, topic: str, text: str) -> bool:
        chat_id = self.chat_id
        if chat_id is None:
            return False
        thread_id = self.topic_id(topic)
        if not thread_id:
            logging.warning("Staff topic %s is not bound; message was not sent to General", topic)
            self.db.add_log("WARNING", f"Staff-тема не привязана: {topic}. Сообщение не отправлено в Общее.")
            return False
        try:
            await bot.send_message(chat_id, text, message_thread_id=thread_id)
            return True
        except Exception as exc:
            logging.warning("Staff message failed for topic %s: %s", topic, exc)
            return False

    async def send_file(self, bot: Bot, topic: str, path: str, caption: str) -> bool:
        chat_id = self.chat_id
        thread_id = self.topic_id(topic)
        if chat_id is None or not thread_id:
            self.db.add_log("WARNING", f"Staff-тема не привязана: {topic}. Файл не отправлен.")
            return False
        try:
            await bot.send_document(chat_id, FSInputFile(path), caption=caption, message_thread_id=thread_id)
            return True
        except Exception as exc:
            logging.warning("Staff file send failed for topic %s: %s", topic, exc)
            return False

    async def log(self, bot: Bot | None, level: str, text: str, notify: bool = False) -> None:
        self.db.add_log(level, text)
        if level.upper() in {"WARNING", "ERROR", "CRITICAL"}:
            logging.warning("Staff %s: %s", level.upper(), text)
        if bot and notify:
            await self.send(bot, "logs", f"⚠️ <b>{escape(level.upper())}</b>\n{escape(text[:3500])}")

    async def auto_reply_changed(self, bot: Bot, description: str) -> None:
        await self.send(bot, "general", f"📝 <b>Автоответ изменён</b>\n{escape(description)}")
