from __future__ import annotations

from pathlib import Path

from ..models import MediaFileInfo, SeasonGroup, ShowGroup
from ..providers.base import Metadata
from ..telegram.base_transport import TelegramTransport


class PublicationService:
    def __init__(self, transport: TelegramTransport, chat_id: str, thread_id: str = ""):
        self.transport = transport
        self.chat_id = chat_id
        self.thread_id = thread_id

    @staticmethod
    def card_text(metadata: Metadata, fallback_title: str) -> str:
        title = metadata.title or fallback_title
        heading = f"{title} ({metadata.year})" if metadata.year else title
        lines = [heading]
        if metadata.original_title and metadata.original_title.casefold() != title.casefold():
            lines.append(metadata.original_title)
        ratings = []
        if metadata.imdb_rating:
            ratings.append(f"IMDb: {metadata.imdb_rating}")
        if metadata.kinopoisk_rating:
            ratings.append(f"Кинопоиск: {metadata.kinopoisk_rating}")
        if ratings:
            lines.append(" · ".join(ratings))
        if metadata.genres:
            lines.append("Жанры: " + ", ".join(metadata.genres))
        if metadata.country:
            lines.append("Страна: " + metadata.country)
        if metadata.director:
            lines.append("Режиссёр: " + metadata.director)
        if metadata.cast:
            lines.append("В ролях: " + ", ".join(metadata.cast[:10]))
        if metadata.overview:
            lines.extend(("", metadata.overview))
        text = "\n".join(lines)
        return text[:1024]

    async def publish_card(self, metadata: Metadata, fallback_title: str) -> dict:
        text = self.card_text(metadata, fallback_title)
        if metadata.poster_url:
            return await self.transport.send_photo(metadata.poster_url, text, self.chat_id, self.thread_id)
        return await self.transport.send_message(text, self.chat_id, self.thread_id)

    async def publish_season(self, season: SeasonGroup, card_text: str = "", metadata: Metadata | None = None) -> list[dict]:
        results: list[dict] = []
        if metadata:
            results.append(await self.publish_card(metadata, season.title))
        elif card_text:
            results.append(await self.transport.send_message(card_text, self.chat_id, self.thread_id))
        episodes = [item for item in season.episodes if item.path.is_file()]
        for start in range(0, len(episodes), 10):
            batch_items = episodes[start : start + 10]
            batch = [item.path for item in batch_items]
            first = batch_items[0].episode_number or start + 1
            last = batch_items[-1].episode_number or first + len(batch) - 1
            caption = f"{season.season_number} сезон\nСерии {first}-{last}"
            if season.dub:
                caption += f"\nДубляж: {season.dub}"
            if len(batch) >= 2 and all(path.suffix.lower() in {".mp4", ".mov", ".m4v"} for path in batch):
                results.extend(await self.transport.send_media_group(batch, caption, self.chat_id, self.thread_id))
            else:
                for index, item in enumerate(batch_items):
                    item_caption = caption if index == 0 else f"{season.title} · серия {item.episode_number or '—'}"
                    results.extend(await self.publish_media(item, item_caption))
        return results

    async def publish_media(self, media: MediaFileInfo, caption: str = "", metadata: Metadata | None = None) -> list[dict]:
        results: list[dict] = []
        if metadata:
            results.append(await self.publish_card(metadata, media.title))
        if not caption:
            caption = media.title
            if media.media_type == "series" and media.episode_number:
                caption = f"{media.title} · серия {media.episode_number}"
        if media.path.suffix.lower() in {".mp4", ".mov", ".m4v"}:
            result = await self.transport.send_video(media.path, caption, self.chat_id, self.thread_id)
        else:
            result = await self.transport.send_document(media.path, caption, self.chat_id, self.thread_id)
        results.append(result)
        return results

    async def publish_show(self, show: ShowGroup, metadata: Metadata | None = None) -> list[dict]:
        results: list[dict] = []
        if metadata:
            results.append(await self.publish_card(metadata, show.title))
        for movie in show.movies:
            results.extend(await self.publish_media(movie))
        for season in show.seasons:
            results.extend(await self.publish_season(season))
        return results
