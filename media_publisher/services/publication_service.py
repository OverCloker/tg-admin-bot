from __future__ import annotations

import hashlib
from pathlib import Path

from ..database.repository import PublisherDatabase
from ..models import MediaFileInfo, SeasonGroup, ShowGroup
from ..providers.base import Metadata
from ..telegram.base_transport import TelegramTransport
from .template_renderer import TemplateRenderer


class PublicationService:
    def __init__(self, transport: TelegramTransport, chat_id: str, thread_id: str = "", database: PublisherDatabase | None = None, operation_key: str = "", templates: TemplateRenderer | None = None):
        self.transport = transport
        self.chat_id = chat_id
        self.thread_id = thread_id
        self.database = database
        self.operation_key = operation_key
        self.templates = templates or TemplateRenderer()

    @staticmethod
    def make_operation_key(chat_id: str, thread_id: str, paths: list[Path], metadata: Metadata) -> str:
        source = "|".join((chat_id, thread_id, metadata.source_url, *(str(path.resolve()) for path in paths)))
        return hashlib.sha256(source.encode("utf-8")).hexdigest()

    def _state(self) -> dict:
        if not self.database or not self.operation_key:
            return {"card_sent": 0, "next_batch": 0, "completed": 0, "error_text": None}
        return self.database.publication_state(self.operation_key)

    def _save_state(self, card_sent: int, next_batch: int, completed: int, error_text: str | None = None) -> None:
        if self.database and self.operation_key:
            self.database.save_publication_state(self.operation_key, card_sent=card_sent, next_batch=next_batch, completed=completed, error_text=error_text)

    async def publish_card(self, metadata: Metadata, caption: str) -> dict:
        poster = metadata.poster_path or metadata.poster_url or metadata.season_poster_url
        if not poster:
            raise ValueError("Постер обязателен. Выберите изображение в предпросмотре.")
        return await self.transport.send_photo(poster, caption, self.chat_id, self.thread_id)

    async def publish_season(self, season: SeasonGroup, card_text: str = "", metadata: Metadata | None = None) -> list[dict]:
        if not metadata:
            results: list[dict] = []
            if card_text:
                results.append(await self.transport.send_message(card_text, self.chat_id, self.thread_id))
            for item in season.episodes:
                if item.path.is_file():
                    results.append(await self._send_file(item, f"{season.title} · серия {item.episode_number or '—'}"))
            return results
        episodes = [item for item in season.episodes if item.path.is_file()]
        if not episodes:
            raise ValueError("В сезоне нет доступных файлов для публикации.")
        state = self._state()
        if state["completed"]:
            return []
        results: list[dict] = []
        card_sent, next_batch = int(state["card_sent"]), int(state["next_batch"])
        try:
            if not card_sent:
                results.append(await self.publish_card(metadata, self.templates.season(metadata, season)))
                card_sent = 1
                self._save_state(card_sent, next_batch, 0)
            batches = [episodes[start : start + 10] for start in range(0, len(episodes), 10)]
            for batch_index in range(next_batch, len(batches)):
                batch_items = batches[batch_index]
                paths = [item.path for item in batch_items]
                first = batch_items[0].episode_number or batch_index * 10 + 1
                last = batch_items[-1].episode_number or first + len(paths) - 1
                caption = self.templates.media_group(season, first, last)
                if len(paths) >= 2 and all(path.suffix.lower() in {".mp4", ".mov", ".m4v"} for path in paths):
                    results.extend(await self.transport.send_media_group(paths, caption, self.chat_id, self.thread_id))
                else:
                    for index, item in enumerate(batch_items):
                        item_caption = caption if index == 0 else f"{season.title} · серия {item.episode_number or '—'}"
                        results.append(await self._send_file(item, item_caption))
                next_batch = batch_index + 1
                self._save_state(card_sent, next_batch, 0)
            self._save_state(card_sent, next_batch, 1)
            return results
        except Exception as exc:
            self._save_state(card_sent, next_batch, 0, str(exc))
            raise

    async def _send_file(self, media: MediaFileInfo, caption: str) -> dict:
        if media.path.suffix.lower() in {".mp4", ".mov", ".m4v"}:
            return await self.transport.send_video(media.path, caption, self.chat_id, self.thread_id)
        return await self.transport.send_document(media.path, caption, self.chat_id, self.thread_id)

    async def publish_media(self, media: MediaFileInfo, caption: str = "", metadata: Metadata | None = None) -> list[dict]:
        if not metadata:
            return [await self._send_file(media, caption or media.title)]
        state = self._state()
        if state["completed"]:
            return []
        results: list[dict] = []
        card_sent, next_batch = int(state["card_sent"]), int(state["next_batch"])
        try:
            if not card_sent:
                results.append(await self.publish_card(metadata, self.templates.movie(metadata, media.dub or "")))
                card_sent = 1
                self._save_state(card_sent, next_batch, 0)
            if next_batch == 0:
                results.append(await self._send_file(media, caption or media.title))
                next_batch = 1
            self._save_state(card_sent, next_batch, 1)
            return results
        except Exception as exc:
            self._save_state(card_sent, next_batch, 0, str(exc))
            raise

    async def publish_show(self, show: ShowGroup, metadata: Metadata | None = None) -> list[dict]:
        if len(show.seasons) == 1 and not show.movies:
            return await self.publish_season(show.seasons[0], metadata=metadata)
        if len(show.movies) == 1 and not show.seasons:
            return await self.publish_media(show.movies[0], metadata=metadata)
        raise ValueError("Выберите конкретный фильм или сезон, чтобы карточка и состояние публикации были однозначными.")
