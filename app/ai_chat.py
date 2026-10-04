"""Opt-in, text-only Gemini chat. No tools, Telegram IDs or credentials in prompts."""
import asyncio
import os
import re
import time
from collections import OrderedDict
from datetime import date, datetime, timezone

import aiohttp


class ChatError(Exception):
    """Safe user-facing error; never contains a provider response or credential."""


class GeminiChat:
    def __init__(self, key: str = "", chats: set[int] | None = None,
                 model: str = "gemini-3.5-flash-lite", daily_limit: int = 200):
        if not re.fullmatch(r"[a-zA-Z0-9._-]+", model):
            raise ValueError("Invalid GEMINI_MODEL")
        self.key = key
        self.chats = chats or set()
        self.model = model
        self.daily_limit = max(1, min(daily_limit, 10000))
        self.history = OrderedDict()
        self.last_user = OrderedDict()
        self.busy = set()
        self.day: date | None = None
        self.requests = 0

    @classmethod
    def from_env(cls):
        enabled = os.getenv("AI_CHAT_ENABLED", "").lower() in {"1", "true", "yes"}
        return cls(
            os.getenv("GEMINI_API_KEY", "").strip() if enabled else "",
            {int(x.strip()) for x in os.getenv("AI_CHAT_IDS", "").split(",") if x.strip()},
            os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip(),
            int(os.getenv("AI_CHAT_DAILY_LIMIT", "200")),
        )

    def allowed(self, chat_id: int) -> bool:
        return bool(self.key) and chat_id in self.chats

    def clear(self, scope: tuple) -> None:
        self.history.pop(scope, None)

    async def generate(self, contents: list) -> str:
        payload = {
            "systemInstruction": {"parts": [{"text":
                "Ты OtvetO4ka, дружелюбный собеседник в Telegram. Отвечай на языке пользователя, "
                "по умолчанию по-русски, кратко и естественно. Не выдавай догадки за факты. "
                "Ты только общаешься: у тебя нет доступа к серверу, ключам, базе, модерации "
                "или актуальному интернету. Не утверждай, что выполнил действия. "
                "Пиши обычный текст без HTML и Markdown."}]},
            "contents": contents,
            "generationConfig": {"maxOutputTokens": 700},
        }
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=35)) as session:
                async with session.post(url, json=payload, headers={"x-goog-api-key": self.key}) as response:
                    if response.status == 429:
                        raise ChatError("Лимит Gemini исчерпан. Попробуй позже.")
                    if response.status != 200:
                        raise ChatError("Gemini сейчас недоступен. Администратору нужно проверить настройки API.")
                    data = await response.json()
            candidate = (data.get("candidates") or [{}])[0]
            parts = candidate.get("content", {}).get("parts", [])
            answer = "\n".join(p["text"] for p in parts if isinstance(p.get("text"), str) and not p.get("thought")).strip()
            if not answer:
                raise ChatError("Gemini не смог ответить на этот запрос. Попробуй переформулировать.")
            return answer[:3500]
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, TypeError, KeyError):
            raise ChatError("Не удалось связаться с Gemini. Попробуй позже.") from None

    async def ask(self, scope: tuple, text: str) -> str:
        if not self.allowed(scope[0]):
            raise ChatError("ИИ-общение в этом чате не включено.")
        text = text.strip()
        if not text or len(text) > 2000:
            raise ChatError("Напиши вопрос длиной от 1 до 2000 символов.")
        now = time.monotonic()
        user_key = (scope[0], scope[2])
        if scope in self.busy or len(self.busy) >= 3:
            raise ChatError("Ещё отвечаю на предыдущий запрос. Подожди немного.")
        if now - self.last_user.get(user_key, -100) < 10:
            raise ChatError("Между вопросами нужно подождать 10 секунд.")
        today = datetime.now(timezone.utc).date()
        if today != self.day:
            self.day, self.requests = today, 0
        if self.requests >= self.daily_limit:
            raise ChatError("Дневной лимит ИИ-общения исчерпан.")
        self.requests += 1  # Failed requests count too; no automatic paid retries.
        self.last_user[user_key] = now
        self.last_user.move_to_end(user_key)
        if len(self.last_user) > 2000:
            self.last_user.popitem(last=False)
        stamp, previous = self.history.get(scope, (0, []))
        contents = (previous if now - stamp < 1800 else []) + [{"role": "user", "parts": [{"text": text}]}]
        self.busy.add(scope)
        try:
            answer = await self.generate(contents)
            self.history[scope] = (time.monotonic(), (contents + [{"role": "model", "parts": [{"text": answer}]}])[-12:])
            self.history.move_to_end(scope)
            if len(self.history) > 500:
                self.history.popitem(last=False)
            return answer
        finally:
            self.busy.discard(scope)
