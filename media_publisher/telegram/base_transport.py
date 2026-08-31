from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class TelegramTransport(ABC):
    @abstractmethod
    async def test_connection(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    async def send_message(self, text: str, chat_id: str, thread_id: str = "") -> dict:
        raise NotImplementedError

    @abstractmethod
    async def send_photo(self, photo: str | Path, caption: str, chat_id: str, thread_id: str = "") -> dict:
        raise NotImplementedError

    @abstractmethod
    async def send_media_group(self, files: list[Path], caption: str, chat_id: str, thread_id: str = "") -> list[dict]:
        raise NotImplementedError

